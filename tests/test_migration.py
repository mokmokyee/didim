from __future__ import annotations

from collector.services.migration_service import sanitize_legacy_placeholder_content

from conftest import opportunity


def test_legacy_synthetic_description_is_removed_without_reactivating_item(storage):
    item = opportunity("legacy", source="legacy")
    item["program_introduction"] = "Contest Korea에서 수집한 테스트 공모전 정보입니다."
    storage.upsert_opportunities([item])
    storage.upsert_opportunities(
        [opportunity("replacement", source="legacy")],
        successful_sources={"legacy"},
    )
    assert storage.get_opportunity("legacy") is None
    assert sanitize_legacy_placeholder_content(storage) == 1
    stored = storage.get_opportunity("legacy", include_inactive=True)
    assert stored["program_introduction"] is None
    assert stored["source_active"] is False
