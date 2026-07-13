from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class CentralQuotaBackend(Protocol):
    enabled: bool

    def reserve_gemini_quota(
        self,
        *,
        purpose: str,
        now: datetime,
        rpm_limit: int,
        rpd_limit: int,
    ) -> tuple[bool, str, int, int]: ...


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    minute_count: int
    day_count: int


class GeminiRateLimiter:
    OFFICIAL_RPM = 15
    OFFICIAL_RPD = 500
    DEFAULT_INTERNAL_RPM = 14
    DEFAULT_INTERNAL_RPD = 480

    def __init__(
        self,
        database_path: Path,
        *,
        rpm_limit: int = DEFAULT_INTERNAL_RPM,
        rpd_limit: int = DEFAULT_INTERNAL_RPD,
        now_func: Callable[[], datetime] | None = None,
        central_backend: CentralQuotaBackend | None = None,
    ):
        if rpm_limit >= self.OFFICIAL_RPM or rpm_limit <= 0:
            raise ValueError("Internal Gemini RPM limit must be between 1 and 14.")
        if rpd_limit >= self.OFFICIAL_RPD or rpd_limit <= 0:
            raise ValueError("Internal Gemini RPD limit must be between 1 and 499.")
        self.database_path = Path(database_path)
        self.rpm_limit = int(rpm_limit)
        self.rpd_limit = int(rpd_limit)
        self.now_func = now_func or (lambda: datetime.now(timezone.utc))
        self.central_backend = central_backend
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gemini_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reserved_at_utc REAL NOT NULL,
                    kst_date TEXT NOT NULL,
                    purpose TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_gemini_calls_time ON gemini_calls(reserved_at_utc)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_gemini_calls_date ON gemini_calls(kst_date)"
            )

    def reserve(self, purpose: str) -> QuotaDecision:
        purpose = str(purpose or "unknown")[:80]
        now = self._aware_now()
        if self.central_backend is not None and getattr(self.central_backend, "enabled", False):
            try:
                allowed, reason, minute_count, day_count = self.central_backend.reserve_gemini_quota(
                    purpose=purpose,
                    now=now,
                    rpm_limit=self.rpm_limit,
                    rpd_limit=self.rpd_limit,
                )
                decision = QuotaDecision(allowed, reason, minute_count, day_count)
                self._log_decision(purpose, decision)
                return decision
            except Exception:
                logger.exception("Firestore Gemini quota reservation failed; denying the call safely.")
                return QuotaDecision(False, "quota_backend_error", 0, 0)

        decision = self._reserve_sqlite(purpose, now)
        self._log_decision(purpose, decision)
        return decision

    def _reserve_sqlite(self, purpose: str, now: datetime) -> QuotaDecision:
        epoch = now.timestamp()
        minute_start = epoch - 60.0
        kst_date = now.astimezone(KST).date().isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            minute_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM gemini_calls WHERE reserved_at_utc > ?",
                    (minute_start,),
                ).fetchone()[0]
            )
            day_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM gemini_calls WHERE kst_date = ?",
                    (kst_date,),
                ).fetchone()[0]
            )
            if minute_count >= self.rpm_limit:
                connection.execute("ROLLBACK")
                return QuotaDecision(False, "rpm_limit", minute_count, day_count)
            if day_count >= self.rpd_limit:
                connection.execute("ROLLBACK")
                return QuotaDecision(False, "rpd_limit", minute_count, day_count)

            connection.execute(
                "INSERT INTO gemini_calls(reserved_at_utc, kst_date, purpose) VALUES (?, ?, ?)",
                (epoch, kst_date, purpose),
            )
            connection.execute(
                "DELETE FROM gemini_calls WHERE reserved_at_utc < ?",
                ((now - timedelta(days=3)).timestamp(),),
            )
            connection.execute("COMMIT")
            return QuotaDecision(True, "reserved", minute_count + 1, day_count + 1)
        except sqlite3.Error:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            logger.exception("SQLite Gemini quota reservation failed; denying the call safely.")
            return QuotaDecision(False, "quota_backend_error", 0, 0)
        finally:
            connection.close()

    def stats(self, now: datetime | None = None) -> dict[str, object]:
        current = self._ensure_aware(now or self._aware_now())
        epoch = current.timestamp()
        kst_date = current.astimezone(KST).date().isoformat()
        with self._connect() as connection:
            minute_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM gemini_calls WHERE reserved_at_utc > ?",
                    (epoch - 60.0,),
                ).fetchone()[0]
            )
            day_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM gemini_calls WHERE kst_date = ?",
                    (kst_date,),
                ).fetchone()[0]
            )
            purposes = {
                row[0]: int(row[1])
                for row in connection.execute(
                    "SELECT purpose, COUNT(*) FROM gemini_calls WHERE kst_date = ? GROUP BY purpose",
                    (kst_date,),
                ).fetchall()
            }
        return {
            "kst_date": kst_date,
            "minute_count": minute_count,
            "day_count": day_count,
            "rpm_limit": self.rpm_limit,
            "rpd_limit": self.rpd_limit,
            "purposes": purposes,
        }

    def _aware_now(self) -> datetime:
        return self._ensure_aware(self.now_func())

    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _log_decision(purpose: str, decision: QuotaDecision) -> None:
        if decision.allowed:
            logger.info(
                "Gemini quota reserved purpose=%s minute_count=%s day_count=%s",
                purpose,
                decision.minute_count,
                decision.day_count,
            )
        else:
            logger.warning(
                "Gemini call blocked purpose=%s reason=%s minute_count=%s day_count=%s",
                purpose,
                decision.reason,
                decision.minute_count,
                decision.day_count,
            )

