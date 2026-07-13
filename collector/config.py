from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def _service_account_path() -> str:
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    candidates = (PROJECT_ROOT / path, PROJECT_ROOT / "backend" / path)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return str(candidates[0].resolve())


def _path_env(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


class Config:
    PROJECT_ROOT = PROJECT_ROOT
    DATA_DIR = PROJECT_ROOT / "collector" / "data"
    WORK_DIR = _path_env("COLLECTOR_WORK_DIR", PROJECT_ROOT / ".local")
    DATABASE_PATH = _path_env("DATABASE_PATH", WORK_DIR / "didim.sqlite3")
    GEMINI_QUOTA_DATABASE_PATH = _path_env(
        "GEMINI_QUOTA_DATABASE_PATH",
        WORK_DIR / "gemini_quota.sqlite3",
    )

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
    GEMINI_INTERNAL_RPM = int(os.getenv("GEMINI_INTERNAL_RPM", "14"))
    GEMINI_INTERNAL_RPD = int(os.getenv("GEMINI_INTERNAL_RPD", "480"))
    GEMINI_MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "2"))

    FIREBASE_SERVICE_ACCOUNT_PATH = _service_account_path()
    FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()
