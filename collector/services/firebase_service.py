from __future__ import annotations

import logging
import json
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import auth, credentials, firestore


logger = logging.getLogger(__name__)


PUBLIC_CATALOG_FIELDS = (
    "id",
    "type",
    "title",
    "organization",
    "program_introduction",
    "targets",
    "keywords",
    "participation_mode",
    "regions",
    "start_date",
    "end_date",
    "view_count",
    "save_count",
    "source_active",
    "first_seen_at",
    "status",
    "d_day",
    "source",
)


class FirebaseService:
    def __init__(
        self,
        service_account_path: str | None,
        storage_bucket: str | None = None,
        service_account_json: str | None = None,
    ):
        self._db = None
        self.enabled = False
        service_account_value = str(service_account_path or "").strip()
        service_account_json_value = str(service_account_json or "").strip()
        certificate = None
        if service_account_json_value:
            try:
                certificate = credentials.Certificate(json.loads(service_account_json_value))
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Firebase service account JSON is invalid; Firestore is disabled.")
                return
        elif service_account_value:
            service_account = Path(service_account_value).expanduser().resolve()
            if not service_account.is_file():
                logger.warning("Firebase service account file was not found; Firestore is disabled.")
                return
            certificate = credentials.Certificate(str(service_account))
        else:
            return

        try:
            firebase_admin.get_app()
        except ValueError:
            options = {"storageBucket": storage_bucket} if storage_bucket else None
            firebase_admin.initialize_app(certificate, options)

        self._db = firestore.client()
        self.enabled = True

    @property
    def db(self):
        return self._db

    def verify_id_token(self, token: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Firebase Authentication is not configured.")
        return dict(auth.verify_id_token(token, check_revoked=True))

    def save_opportunities(self, items: Iterable[dict[str, Any]]) -> None:
        if not self.enabled or self._db is None:
            return
        batch = self._db.batch()
        count = 0
        for item in items:
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                continue
            batch.set(self._db.collection("opportunities").document(item_id), item, merge=True)
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = self._db.batch()
        if count % 400:
            batch.commit()

    def mark_missing_inactive(self, source: str, active_ids: set[str]) -> None:
        if not self.enabled or self._db is None:
            return
        docs = self._db.collection("opportunities").where("source", "==", source).stream()
        batch = self._db.batch()
        count = 0
        for snapshot in docs:
            if snapshot.id in active_ids:
                continue
            batch.update(snapshot.reference, {"source_active": False})
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = self._db.batch()
        if count % 400:
            batch.commit()

    def get_engagement_counts(self) -> dict[str, dict[str, int]]:
        if not self.enabled or self._db is None:
            return {}
        counts: dict[str, dict[str, int]] = {}
        for snapshot in self._db.collection("opportunity_views").stream():
            opportunity_id = str((snapshot.to_dict() or {}).get("opportunity_id") or "")
            if opportunity_id:
                values = counts.setdefault(opportunity_id, {"view_count": 0, "save_count": 0})
                values["view_count"] += 1
        for snapshot in self._db.collection_group("saved_opportunities").stream():
            opportunity_id = str((snapshot.to_dict() or {}).get("opportunity_id") or snapshot.id)
            if opportunity_id:
                values = counts.setdefault(opportunity_id, {"view_count": 0, "save_count": 0})
                values["save_count"] += 1
        return counts

    def publish_catalog(self, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled or self._db is None:
            raise RuntimeError("Firestore is not configured.")

        compact_items: list[dict[str, Any]] = []
        for item in items:
            compact = {
                field: item.get(field)
                for field in PUBLIC_CATALOG_FIELDS
                if item.get(field) is not None
            }
            if compact.get("program_introduction"):
                compact["program_introduction"] = str(compact["program_introduction"])[:500]
            if compact.get("id") and compact.get("title"):
                compact_items.append(compact)

        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_size = 0
        for item in compact_items:
            item_size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if current and current_size + item_size > 650_000:
                chunks.append(current)
                current = []
                current_size = 0
            current.append(item)
            current_size += item_size
        if current:
            chunks.append(current)

        now = datetime.now(ZoneInfo("UTC")).isoformat()
        generation = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        meta_reference = self._db.collection("catalog").document("opportunities")
        previous = meta_reference.get()
        previous_chunk_ids = list((previous.to_dict() or {}).get("chunk_ids", [])) if previous.exists else []
        chunk_ids = [f"{generation}-{index:03d}" for index in range(len(chunks))]

        batch = self._db.batch()
        for chunk_id, values in zip(chunk_ids, chunks):
            batch.set(
                self._db.collection("catalog_chunks").document(chunk_id),
                {"generation": generation, "items": values, "updated_at": now},
            )
        batch.commit()

        meta_reference.set(
            {
                "generation": generation,
                "chunk_ids": chunk_ids,
                "total": len(compact_items),
                "updated_at": now,
            }
        )

        for start in range(0, len(previous_chunk_ids), 400):
            delete_batch = self._db.batch()
            for chunk_id in previous_chunk_ids[start : start + 400]:
                if chunk_id not in chunk_ids:
                    delete_batch.delete(self._db.collection("catalog_chunks").document(str(chunk_id)))
            delete_batch.commit()
        return {"total": len(compact_items), "chunks": len(chunks), "updated_at": now}

    def get_user(self, uid: str) -> dict[str, Any] | None:
        if not self.enabled or self._db is None:
            return None
        snapshot = self._db.collection("users").document(uid).get()
        return dict(snapshot.to_dict() or {}) if snapshot.exists else None

    def set_user(self, uid: str, payload: dict[str, Any]) -> None:
        if self.enabled and self._db is not None:
            self._db.collection("users").document(uid).set(payload, merge=True)

    def delete_user(self, uid: str) -> None:
        if not self.enabled or self._db is None:
            return
        user_reference = self._db.collection("users").document(uid)
        saved = list(user_reference.collection("saved_opportunities").stream())
        for start in range(0, len(saved), 400):
            batch = self._db.batch()
            for snapshot in saved[start : start + 400]:
                batch.delete(snapshot.reference)
            batch.commit()
        user_reference.delete()
        auth.delete_user(uid)

    def get_saved_ids(self, uid: str) -> list[str]:
        if not self.enabled or self._db is None:
            return []
        docs = (
            self._db.collection("users")
            .document(uid)
            .collection("saved_opportunities")
            .order_by("saved_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [snapshot.id for snapshot in docs]

    def save_opportunity(self, uid: str, opportunity_id: str, saved_at: str) -> None:
        if self.enabled and self._db is not None:
            self._db.collection("users").document(uid).collection("saved_opportunities").document(
                opportunity_id
            ).set({"opportunity_id": opportunity_id, "saved_at": saved_at})

    def delete_saved_opportunity(self, uid: str, opportunity_id: str) -> None:
        if self.enabled and self._db is not None:
            self._db.collection("users").document(uid).collection("saved_opportunities").document(
                opportunity_id
            ).delete()

    def cache_get(self, collection: str, key: str) -> dict[str, Any] | None:
        if not self.enabled or self._db is None:
            return None
        snapshot = self._db.collection(collection).document(key).get()
        return dict(snapshot.to_dict() or {}) if snapshot.exists else None

    def cache_set(self, collection: str, key: str, payload: dict[str, Any]) -> None:
        if self.enabled and self._db is not None:
            self._db.collection(collection).document(key).set(payload, merge=True)

    def save_crawl_run(self, run_id: str, payload: dict[str, Any]) -> None:
        if self.enabled and self._db is not None:
            self._db.collection("crawl_runs").document(run_id).set(payload)

    def reserve_gemini_quota(
        self,
        *,
        purpose: str,
        now: datetime,
        rpm_limit: int,
        rpd_limit: int,
    ) -> tuple[bool, str, int, int]:
        if not self.enabled or self._db is None:
            raise RuntimeError("Firestore is not configured.")
        kst_date = now.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        epoch = now.timestamp()
        reference = self._db.collection("gemini_usage").document(kst_date)
        transaction = self._db.transaction()

        @firestore.transactional
        def reserve(transaction):
            snapshot = reference.get(transaction=transaction)
            data = dict(snapshot.to_dict() or {})
            recent_calls = [
                float(value)
                for value in data.get("recent_calls", [])
                if isinstance(value, (int, float)) and float(value) > epoch - 60.0
            ]
            day_count = int(data.get("day_count", 0))
            if len(recent_calls) >= rpm_limit:
                return False, "rpm_limit", len(recent_calls), day_count
            if day_count >= rpd_limit:
                return False, "rpd_limit", len(recent_calls), day_count
            recent_calls.append(epoch)
            purposes = dict(data.get("purposes", {}))
            purposes[purpose] = int(purposes.get(purpose, 0)) + 1
            transaction.set(
                reference,
                {
                    "date": kst_date,
                    "day_count": day_count + 1,
                    "recent_calls": recent_calls,
                    "purposes": purposes,
                    "updated_at": now.isoformat(),
                },
                merge=True,
            )
            return True, "reserved", len(recent_calls), day_count + 1

        return reserve(transaction)

    def acquire_crawl_lock(self, name: str, now_epoch: float, ttl_seconds: int) -> str | None:
        if not self.enabled or self._db is None:
            return None
        owner = uuid.uuid4().hex
        reference = self._db.collection("crawl_locks").document(name)
        transaction = self._db.transaction()

        @firestore.transactional
        def acquire(transaction):
            snapshot = reference.get(transaction=transaction)
            data = dict(snapshot.to_dict() or {})
            if snapshot.exists and float(data.get("expires_at", 0)) > now_epoch:
                return None
            transaction.set(
                reference,
                {"owner": owner, "acquired_at": now_epoch, "expires_at": now_epoch + ttl_seconds},
            )
            return owner

        return acquire(transaction)

    def release_crawl_lock(self, name: str, owner: str) -> None:
        if not self.enabled or self._db is None:
            return
        reference = self._db.collection("crawl_locks").document(name)
        snapshot = reference.get()
        data = dict(snapshot.to_dict() or {})
        if snapshot.exists and data.get("owner") == owner:
            reference.delete()
