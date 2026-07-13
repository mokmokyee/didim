from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .firebase_service import FirebaseService


logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def kst_today() -> date:
    return datetime.now(KST).date()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def opportunity_status(item: dict[str, Any], today: date | None = None) -> tuple[str, int | None]:
    current = today or kst_today()
    end_value = str(item.get("end_date") or "").strip()
    if not end_value:
        return "open", None
    try:
        end_date = date.fromisoformat(end_value)
    except ValueError:
        return "open", None
    d_day = (end_date - current).days
    if d_day < 0:
        return "closed", d_day
    if d_day <= 7:
        return "urgent", d_day
    return "open", d_day


class StorageService:
    def __init__(self, database_path: Path, firebase: FirebaseService | None = None):
        self.database_path = Path(database_path)
        self.firebase = firebase or FirebaseService(None)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    source_active INTEGER NOT NULL DEFAULT 1,
                    content_hash TEXT,
                    payload TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opportunities_active ON opportunities(source_active);
                CREATE INDEX IF NOT EXISTS idx_opportunities_type ON opportunities(type);
                CREATE INDEX IF NOT EXISTS idx_opportunities_end_date ON opportunities(end_date);
                CREATE INDEX IF NOT EXISTS idx_opportunities_source ON opportunities(source);

                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saved_opportunities (
                    uid TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    PRIMARY KEY(uid, opportunity_id)
                );
                CREATE INDEX IF NOT EXISTS idx_saved_uid_time ON saved_opportunities(uid, saved_at DESC);

                CREATE TABLE IF NOT EXISTS mapping_cache (
                    collection_name TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(collection_name, cache_key)
                );

                CREATE TABLE IF NOT EXISTS crawl_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS distributed_locks (
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )

    def upsert_opportunities(
        self,
        items: Iterable[dict[str, Any]],
        successful_sources: Iterable[str] = (),
    ) -> dict[str, int]:
        now = iso_now()
        prepared = [dict(item) for item in items if str(item.get("id", "")).strip()]
        seen_by_source: dict[str, set[str]] = {}
        inserted = 0
        updated = 0

        with self._connect() as connection:
            for item in prepared:
                item_id = str(item["id"])
                source = str(item.get("source") or "unknown")
                seen_by_source.setdefault(source, set()).add(item_id)
                existing = connection.execute(
                    "SELECT first_seen_at FROM opportunities WHERE id = ?", (item_id,)
                ).fetchone()
                first_seen = str(item.get("first_seen_at") or (existing[0] if existing else now))
                item.update(
                    {
                        "id": item_id,
                        "source": source,
                        "source_active": True,
                        "first_seen_at": first_seen,
                        "last_seen_at": now,
                        "updated_at": now,
                    }
                )
                connection.execute(
                    """
                    INSERT INTO opportunities(
                        id, type, title, source, start_date, end_date, source_active,
                        content_hash, payload, first_seen_at, last_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type=excluded.type,
                        title=excluded.title,
                        source=excluded.source,
                        start_date=excluded.start_date,
                        end_date=excluded.end_date,
                        source_active=1,
                        content_hash=excluded.content_hash,
                        payload=excluded.payload,
                        last_seen_at=excluded.last_seen_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item_id,
                        str(item.get("type") or ""),
                        str(item.get("title") or ""),
                        source,
                        item.get("start_date"),
                        item.get("end_date"),
                        str(item.get("content_hash") or ""),
                        json.dumps(item, ensure_ascii=False, separators=(",", ":")),
                        first_seen,
                        now,
                        now,
                    ),
                )
                if existing:
                    updated += 1
                else:
                    inserted += 1

            deactivated = 0
            for source in set(successful_sources):
                active_ids = seen_by_source.get(source, set())
                rows = connection.execute(
                    "SELECT id, payload FROM opportunities WHERE source = ? AND source_active = 1",
                    (source,),
                ).fetchall()
                for row in rows:
                    if row["id"] in active_ids:
                        continue
                    payload = json.loads(row["payload"])
                    payload["source_active"] = False
                    payload["updated_at"] = now
                    connection.execute(
                        "UPDATE opportunities SET source_active = 0, payload = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now, row["id"]),
                    )
                    deactivated += 1
            connection.commit()

        if self.firebase.enabled:
            try:
                self.firebase.save_opportunities(prepared)
                for source in set(successful_sources):
                    self.firebase.mark_missing_inactive(source, seen_by_source.get(source, set()))
            except Exception:
                logger.exception("Firestore opportunity mirror failed.")
        return {"inserted": inserted, "updated": updated, "deactivated": deactivated}

    def get_existing_map(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload, source_active FROM opportunities").fetchall()
        return {item["id"]: item for item in (self._row_item(row) for row in rows)}

    def all_opportunities(self) -> list[dict[str, Any]]:
        """Return every currently sourced item, including closed opportunities."""
        return [
            self._with_status(item)
            for item in self.get_existing_map().values()
            if item.get("source_active", True)
        ]

    def patch_opportunity_payloads(self, patches: dict[str, dict[str, Any]]) -> int:
        if not patches:
            return 0
        now = iso_now()
        changed_items: list[dict[str, Any]] = []
        with self._connect() as connection:
            for item_id, values in patches.items():
                row = connection.execute(
                    "SELECT payload, source_active FROM opportunities WHERE id = ?",
                    (str(item_id),),
                ).fetchone()
                if not row:
                    continue
                payload = json.loads(row["payload"])
                payload.update(values)
                payload["updated_at"] = now
                connection.execute(
                    "UPDATE opportunities SET payload = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now, str(item_id)),
                )
                changed_items.append({**payload, "source_active": bool(row["source_active"])})
            connection.commit()
        if changed_items:
            try:
                self.firebase.save_opportunities(changed_items)
            except Exception:
                logger.exception("Firestore opportunity patch mirror failed.")
        return len(changed_items)

    def get_opportunity(self, opportunity_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload, source_active FROM opportunities WHERE id = ?", (str(opportunity_id),)
            ).fetchone()
        if not row:
            return None
        item = self._row_item(row)
        if not include_inactive and not item.get("source_active", True):
            return None
        return self._with_status(item)

    def list_opportunities(
        self,
        *,
        types: Iterable[str] = (),
        targets: Iterable[str] = (),
        keywords: Iterable[str] = (),
        regions: Iterable[str] = (),
        status: str = "active",
        title_query: str = "",
        keyword_query: Iterable[str] = (),
        sort: str = "recommend",
        page: int = 1,
        page_size: int = 24,
        ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload, source_active FROM opportunities WHERE source_active = 1"
            ).fetchall()
        items = [self._with_status(self._row_item(row)) for row in rows]

        id_filter = {str(value) for value in ids} if ids is not None else None
        type_filter = {str(value) for value in types if str(value)}
        target_filter = {str(value) for value in targets if str(value)}
        keyword_filter = {str(value) for value in keywords if str(value)}
        query_keywords = {str(value) for value in keyword_query if str(value)}
        query = str(title_query or "").strip().casefold()
        selected_regions = {str(value).strip() for value in regions if str(value).strip()}

        filtered: list[dict[str, Any]] = []
        for item in items:
            if id_filter is not None and str(item.get("id")) not in id_filter:
                continue
            if type_filter and str(item.get("type")) not in type_filter:
                continue
            target_values = item.get("targets") or item.get("target") or []
            if isinstance(target_values, str):
                target_values = [target_values]
            if target_filter and not target_filter.intersection(str(value) for value in target_values):
                continue
            item_keywords = {str(value) for value in item.get("keywords", [])}
            if keyword_filter and not keyword_filter.intersection(item_keywords):
                continue
            if selected_regions and not self._matches_region(item, selected_regions):
                continue
            if not self._matches_status(item, status):
                continue
            if query or query_keywords:
                title_match = bool(query and query in str(item.get("title", "")).casefold())
                keyword_match = bool(query_keywords.intersection(item_keywords))
                if not (title_match or keyword_match):
                    continue
            filtered.append(item)

        self._sort(filtered, sort)
        total = len(filtered)
        safe_page_size = min(max(int(page_size), 1), 100)
        safe_page = max(int(page), 1)
        start = (safe_page - 1) * safe_page_size
        page_items = filtered[start : start + safe_page_size]
        return {
            "items": page_items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "pages": (total + safe_page_size - 1) // safe_page_size,
        }

    def _matches_status(self, item: dict[str, Any], requested: str) -> bool:
        state = str(item.get("status"))
        requested = str(requested or "active")
        if requested in {"active", "all"}:
            return state in {"open", "urgent"}
        if requested in {"open", "recruiting"}:
            return state in {"open", "urgent"}
        if requested in {"urgent", "closing"}:
            return state == "urgent"
        if requested == "closed":
            return state == "closed"
        if requested == "any":
            return True
        return state in {"open", "urgent"}

    @staticmethod
    def _matches_region(item: dict[str, Any], selected_regions: set[str]) -> bool:
        mode = str(item.get("participation_mode") or "unknown")
        regions = {str(value) for value in item.get("regions", [])}
        if mode in {"online", "hybrid"}:
            return True
        if mode == "offline":
            return bool(selected_regions.intersection(regions)) or "전국" in regions
        return False

    @staticmethod
    def _sort(items: list[dict[str, Any]], sort: str) -> None:
        if sort == "views":
            items.sort(key=lambda item: int(item.get("view_count", 0)), reverse=True)
        elif sort == "deadline":
            items.sort(key=lambda item: item.get("d_day") if item.get("d_day") is not None else 999999)
        elif sort == "saved_at":
            items.sort(key=lambda item: str(item.get("saved_at", "")), reverse=True)
        else:
            items.sort(
                key=lambda item: int(item.get("view_count", 0)) + int(item.get("save_count", 0)) * 2,
                reverse=True,
            )

    def increment_view(self, opportunity_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM opportunities WHERE id = ?", (str(opportunity_id),)
            ).fetchone()
            if not row:
                return
            payload = json.loads(row["payload"])
            payload["view_count"] = int(payload.get("view_count", 0)) + 1
            connection.execute(
                "UPDATE opportunities SET payload = ?, updated_at = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), iso_now(), str(opportunity_id)),
            )
            connection.commit()

    def get_user(self, uid: str) -> dict[str, Any] | None:
        if self.firebase.enabled:
            try:
                remote = self.firebase.get_user(uid)
                if remote is not None:
                    return remote
            except Exception:
                logger.exception("Firestore user read failed; using the local mirror.")
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM users WHERE uid = ?", (uid,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def set_user(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = iso_now()
        clean_payload = {**payload, "uid": uid, "updated_at": now}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users(uid, payload, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (uid, json.dumps(clean_payload, ensure_ascii=False, separators=(",", ":")), now),
            )
            connection.commit()
        try:
            self.firebase.set_user(uid, clean_payload)
        except Exception:
            logger.exception("Firestore user write failed; the local mirror was retained.")
        return clean_payload

    def delete_user(self, uid: str) -> None:
        with self._connect() as connection:
            saved_rows = connection.execute(
                "SELECT opportunity_id FROM saved_opportunities WHERE uid = ?",
                (uid,),
            ).fetchall()
            for row in saved_rows:
                item = connection.execute(
                    "SELECT payload FROM opportunities WHERE id = ?",
                    (str(row["opportunity_id"]),),
                ).fetchone()
                if item:
                    payload = json.loads(item["payload"])
                    payload["save_count"] = max(0, int(payload.get("save_count", 0)) - 1)
                    connection.execute(
                        "UPDATE opportunities SET payload = ?, updated_at = ? WHERE id = ?",
                        (
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            iso_now(),
                            str(row["opportunity_id"]),
                        ),
                    )
            connection.execute("DELETE FROM saved_opportunities WHERE uid = ?", (uid,))
            connection.execute("DELETE FROM users WHERE uid = ?", (uid,))
            connection.commit()
        try:
            self.firebase.delete_user(uid)
        except Exception:
            logger.exception("Firebase user deletion failed after local deletion.")
            raise

    def get_saved_ids(self, uid: str) -> list[str]:
        if self.firebase.enabled:
            try:
                return self.firebase.get_saved_ids(uid)
            except Exception:
                logger.exception("Firestore saved list read failed; using the local mirror.")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT opportunity_id FROM saved_opportunities WHERE uid = ? ORDER BY saved_at DESC",
                (uid,),
            ).fetchall()
        return [str(row["opportunity_id"]) for row in rows]

    def save_opportunity(self, uid: str, opportunity_id: str) -> bool:
        item = self.get_opportunity(opportunity_id)
        if not item:
            return False
        now = iso_now()
        with self._connect() as connection:
            already_saved = connection.execute(
                "SELECT 1 FROM saved_opportunities WHERE uid = ? AND opportunity_id = ?",
                (uid, str(opportunity_id)),
            ).fetchone()
            if already_saved:
                try:
                    self.firebase.save_opportunity(uid, str(opportunity_id), now)
                except Exception:
                    logger.exception("Firestore save retry failed.")
                return True
            connection.execute(
                "INSERT INTO saved_opportunities(uid, opportunity_id, saved_at) VALUES (?, ?, ?)",
                (uid, str(opportunity_id), now),
            )
            row = connection.execute(
                "SELECT payload FROM opportunities WHERE id = ?", (str(opportunity_id),)
            ).fetchone()
            payload = json.loads(row["payload"])
            payload["save_count"] = int(payload.get("save_count", 0)) + 1
            connection.execute(
                "UPDATE opportunities SET payload = ?, updated_at = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now, str(opportunity_id)),
            )
            connection.commit()
        try:
            self.firebase.save_opportunity(uid, str(opportunity_id), now)
        except Exception:
            logger.exception("Firestore save mirror failed.")
        return True

    def delete_saved_opportunity(self, uid: str, opportunity_id: str) -> None:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM saved_opportunities WHERE uid = ? AND opportunity_id = ?",
                (uid, str(opportunity_id)),
            ).rowcount
            if deleted:
                row = connection.execute(
                    "SELECT payload FROM opportunities WHERE id = ?", (str(opportunity_id),)
                ).fetchone()
                if row:
                    payload = json.loads(row["payload"])
                    payload["save_count"] = max(0, int(payload.get("save_count", 0)) - 1)
                    connection.execute(
                        "UPDATE opportunities SET payload = ?, updated_at = ? WHERE id = ?",
                        (
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            iso_now(),
                            str(opportunity_id),
                        ),
                    )
            connection.commit()
        try:
            self.firebase.delete_saved_opportunity(uid, str(opportunity_id))
        except Exception:
            logger.exception("Firestore unsave mirror failed.")

    def list_saved(self, uid: str, status: str = "all", sort: str = "saved_at") -> dict[str, Any]:
        saved_ids = self.get_saved_ids(uid)
        if not saved_ids:
            return {"items": [], "total": 0, "page": 1, "page_size": 100, "pages": 0}
        result = self.list_opportunities(
            ids=saved_ids,
            status=status,
            sort="deadline" if sort.startswith("deadline") else "recommend",
            page=1,
            page_size=100,
        )
        order = {item_id: index for index, item_id in enumerate(saved_ids)}
        if sort == "saved_at":
            result["items"].sort(key=lambda item: order.get(str(item["id"]), 999999))
        elif sort == "deadline-desc":
            result["items"].sort(
                key=lambda item: item.get("d_day") if item.get("d_day") is not None else -999999,
                reverse=True,
            )
        elif sort == "name":
            result["items"].sort(key=lambda item: str(item.get("title") or ""))
        return result

    def cache_get(self, collection: str, key: str) -> dict[str, Any] | None:
        try:
            remote = self.firebase.cache_get(collection, key)
            if remote is not None:
                return remote
        except Exception:
            logger.exception("Firestore mapping cache read failed; using the local cache.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mapping_cache WHERE collection_name = ? AND cache_key = ?",
                (collection, key),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def cache_set(self, collection: str, key: str, payload: dict[str, Any]) -> None:
        now = iso_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mapping_cache(collection_name, cache_key, payload, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(collection_name, cache_key) DO UPDATE SET
                    payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (collection, key, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
            )
            connection.commit()
        try:
            self.firebase.cache_set(collection, key, payload)
        except Exception:
            logger.exception("Firestore mapping cache write failed.")

    def save_crawl_run(self, run_id: str, payload: dict[str, Any]) -> None:
        now = iso_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO crawl_runs(run_id, payload, created_at) VALUES (?, ?, ?)",
                (run_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
            )
            connection.commit()
        try:
            self.firebase.save_crawl_run(run_id, payload)
        except Exception:
            logger.exception("Firestore crawl run mirror failed.")

    def acquire_lock(self, name: str, ttl_seconds: int = 3600) -> str | None:
        now_epoch = time.time()
        if self.firebase.enabled:
            try:
                return self.firebase.acquire_crawl_lock(name, now_epoch, ttl_seconds)
            except Exception:
                logger.exception("Firestore crawl lock failed; denying the crawl safely.")
                return None
        owner = uuid.uuid4().hex
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM distributed_locks WHERE expires_at <= ?", (now_epoch,))
            try:
                connection.execute(
                    "INSERT INTO distributed_locks(name, owner, expires_at) VALUES (?, ?, ?)",
                    (name, owner, now_epoch + ttl_seconds),
                )
            except sqlite3.IntegrityError:
                connection.rollback()
                return None
            connection.commit()
            return owner
        finally:
            connection.close()

    def release_lock(self, name: str, owner: str) -> None:
        if self.firebase.enabled:
            try:
                self.firebase.release_crawl_lock(name, owner)
            except Exception:
                logger.exception("Firestore crawl lock release failed.")
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM distributed_locks WHERE name = ? AND owner = ?", (name, owner))
            connection.commit()

    @staticmethod
    def _row_item(row: sqlite3.Row) -> dict[str, Any]:
        item = json.loads(row["payload"])
        item["source_active"] = bool(row["source_active"])
        return item

    @staticmethod
    def _with_status(item: dict[str, Any]) -> dict[str, Any]:
        state, d_day = opportunity_status(item)
        return {**item, "status": state, "d_day": d_day}
