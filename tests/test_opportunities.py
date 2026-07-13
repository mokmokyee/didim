from __future__ import annotations

from collector.services.gemini_service import GeminiService
from collector.services.opportunity_service import OpportunityService

from conftest import opportunity


class DisabledClient:
    enabled = False


def service_for(storage, taxonomy):
    gemini = GeminiService(DisabledClient(), taxonomy, storage)
    return OpportunityService(storage, taxonomy, gemini)


def test_search_is_title_union_keyword_match_without_duplicates(storage, taxonomy):
    storage.upsert_opportunities(
        [
            opportunity("title", title="청소년 그림 대회", keywords=[]),
            opportunity("keyword", title="창작 공모전", keywords=["미술"]),
            opportunity("both", title="그림 전시 공모", keywords=["미술"]),
        ]
    )
    result = service_for(storage, taxonomy).search("그림", page_size=100)
    ids = [item["id"] for item in result["items"]]
    assert set(ids) == {"title", "keyword", "both"}
    assert len(ids) == len(set(ids))


def test_region_filter_includes_online_hybrid_and_selected_offline(storage, taxonomy):
    storage.upsert_opportunities(
        [
            opportunity("online", mode="online", regions=[]),
            opportunity("hybrid", mode="hybrid", regions=["부산"]),
            opportunity("seoul", mode="offline", regions=["서울"]),
            opportunity("busan", mode="offline", regions=["부산"]),
            opportunity("nationwide", mode="unknown", regions=["전국"]),
        ]
    )
    service = service_for(storage, taxonomy)
    selected = service.list_opportunities(regions=["서울"], page_size=100)["items"]
    assert {item["id"] for item in selected} == {"online", "hybrid", "seoul", "nationwide"}
    unselected = service.list_opportunities(page_size=100)["items"]
    assert {item["id"] for item in unselected} == {"online", "hybrid", "seoul", "busan", "nationwide"}


def test_ui_filter_uses_mapped_internal_keywords(storage, taxonomy):
    storage.upsert_opportunities(
        [
            opportunity("ai", keywords=["인공지능"]),
            opportunity("art", keywords=["미술"]),
        ]
    )
    result = service_for(storage, taxonomy).list_opportunities(categories=["IT·기술"], page_size=100)
    assert [item["id"] for item in result["items"]] == ["ai"]


def test_status_boundaries_and_saved_tabs(storage):
    items = [
        opportunity("d8", end_offset=8),
        opportunity("d7", end_offset=7),
        opportunity("d0", end_offset=0),
        opportunity("closed", end_offset=-1),
    ]
    storage.upsert_opportunities(items)
    for item in items:
        storage.save_opportunity("user", item["id"])

    active = storage.list_opportunities(status="active", page_size=100)["items"]
    states = {item["id"]: item["status"] for item in active}
    assert states == {"d8": "open", "d7": "urgent", "d0": "urgent"}
    assert [item["id"] for item in storage.list_saved("user", status="closed")["items"]] == ["closed"]
    assert {item["id"] for item in storage.list_saved("user", status="all")["items"]} == {"d8", "d7", "d0"}
    assert {item["id"] for item in storage.list_saved("user", status="urgent")["items"]} == {"d7", "d0"}


def test_missing_source_is_hidden_only_after_successful_source_crawl(storage):
    old = opportunity("old", source="source-a", end_offset=-1)
    storage.upsert_opportunities([old])
    storage.save_opportunity("user", "old")

    storage.upsert_opportunities([], successful_sources=set())
    assert storage.get_opportunity("old") is not None

    new = opportunity("new", source="source-a")
    result = storage.upsert_opportunities([new], successful_sources={"source-a"})
    assert result["deactivated"] == 1
    assert storage.get_opportunity("old") is None
    assert storage.list_saved("user", status="closed")["items"] == []


def test_saving_same_item_twice_does_not_double_count(storage):
    storage.upsert_opportunities([opportunity("one")])
    assert storage.save_opportunity("user", "one")
    assert storage.save_opportunity("user", "one")
    assert storage.get_opportunity("one")["save_count"] == 1
