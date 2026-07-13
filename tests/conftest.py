from __future__ import annotations

from datetime import date, timedelta

import pytest

from collector.services.firebase_service import FirebaseService
from collector.services.storage_service import StorageService
from collector.services.taxonomy_service import TaxonomyService, opportunity_content_hash


@pytest.fixture
def taxonomy() -> TaxonomyService:
    return TaxonomyService()


@pytest.fixture
def storage(tmp_path) -> StorageService:
    return StorageService(tmp_path / "didim.sqlite3", FirebaseService(""))


def opportunity(
    item_id: str,
    *,
    title: str | None = None,
    source: str = "test-source",
    end_offset: int | None = 30,
    keywords: list[str] | None = None,
    mode: str = "unknown",
    regions: list[str] | None = None,
    targets: list[str] | None = None,
) -> dict:
    end_date = (date.today() + timedelta(days=end_offset)).isoformat() if end_offset is not None else None
    item = {
        "id": item_id,
        "type": "contest",
        "title": title or f"프로그램 {item_id}",
        "organization": None,
        "start_date": None,
        "end_date": end_date,
        "program_introduction": None,
        "activity_content": None,
        "eligibility": None,
        "required_documents": None,
        "benefits": None,
        "contact": None,
        "detail_url": f"https://example.org/programs/{item_id}",
        "source": source,
        "keywords": keywords or [],
        "participation_mode": mode,
        "regions": regions or [],
        "targets": targets or [],
        "source_active": True,
        "view_count": 0,
        "save_count": 0,
        "gemini_status": "local",
    }
    item["content_hash"] = opportunity_content_hash(item)
    return item
