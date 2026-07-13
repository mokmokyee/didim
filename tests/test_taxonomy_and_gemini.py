from __future__ import annotations

import json

from collector.services.gemini_service import GeminiService
from collector.services.taxonomy_service import opportunity_content_hash


class MemoryCache:
    def __init__(self):
        self.values = {}

    def cache_get(self, collection, key):
        return self.values.get((collection, key))

    def cache_set(self, collection, key, payload):
        self.values[(collection, key)] = payload


class BatchClient:
    enabled = True

    def __init__(self):
        self.calls = []

    def generate_json(self, *, purpose, prompt):
        self.calls.append(purpose)
        if purpose == "opportunity_classification":
            raw_items = json.loads(prompt.rsplit("items=", 1)[1])
            return {
                "items": [
                    {
                        "id": item["id"],
                        "keywords": ["미술", "영상", "허용되지않음", "미술", "광고", "공연"],
                        "participation_mode": "offline",
                        "regions": ["서울", "가상지역"],
                    }
                    for item in raw_items
                ]
            }
        if purpose == "user_interest_mapping":
            return {"keywords": ["인공지능", "소프트웨어", "새키워드"]}
        return {"keywords": ["미술", "그래픽디자인", "새키워드"]}


class DisabledClient:
    enabled = False


def raw_item(item_id: str) -> dict:
    return {
        "id": item_id,
        "type": "contest",
        "title": f"미술 영상 공모전 {item_id}",
        "program_introduction": "서울 현장에서 진행",
        "activity_content": None,
        "eligibility": None,
        "required_documents": None,
        "benefits": None,
        "organization": "테스트",
        "start_date": "2026-07-01",
        "end_date": "2026-08-01",
        "detail_url": f"https://example.org/{item_id}",
        "source": "test",
        "source_active": True,
    }


def test_taxonomy_has_versioned_40_to_60_keywords(taxonomy):
    assert 40 <= len(taxonomy.labels) <= 60
    assert taxonomy.version >= 1
    assert len(taxonomy.labels) == len(set(taxonomy.labels))


def test_filter_maps_to_multiple_internal_keywords(taxonomy):
    mapped = taxonomy.filter_keywords(["IT·기술"])
    assert {"소프트웨어", "인공지능", "데이터"}.issubset(set(mapped))


def test_invalid_keywords_regions_and_duplicates_are_removed(taxonomy):
    client = BatchClient()
    service = GeminiService(client, taxonomy, MemoryCache())
    item = service.enrich_opportunities([raw_item("one")])[0]
    assert item["keywords"] == ["미술", "영상", "광고", "공연"]
    assert len(item["keywords"]) == 4
    assert item["regions"] == ["서울"]


def test_exact_batch_size_thirty_means_31_items_use_two_calls(taxonomy):
    client = BatchClient()
    service = GeminiService(client, taxonomy, MemoryCache())
    result = service.enrich_opportunities([raw_item(str(index)) for index in range(31)])
    assert len(result) == 31
    assert client.calls.count("opportunity_classification") == 2


def test_unchanged_hash_is_not_sent_again(taxonomy):
    client = BatchClient()
    service = GeminiService(client, taxonomy, MemoryCache())
    raw = raw_item("same")
    existing = {
        "same": {
            **raw,
            "content_hash": opportunity_content_hash(raw),
            "keywords": ["미술"],
            "participation_mode": "online",
            "regions": [],
            "gemini_status": "complete",
        }
    }
    result = service.enrich_opportunities([raw], existing)
    assert result[0]["keywords"] == ["미술"]
    assert client.calls == []


def test_user_display_values_and_normalized_keywords_are_separate_and_cached(taxonomy):
    client = BatchClient()
    cache = MemoryCache()
    service = GeminiService(client, taxonomy, cache)
    first = service.normalize_user_interests(["AI 개발", "그림 그리기"])
    second = service.normalize_user_interests(["AI 개발", "그림 그리기"])
    assert first["interest_display_values"] == ["AI 개발", "그림 그리기"]
    assert first["interest_keywords"] == ["인공지능", "소프트웨어"]
    assert second["interest_display_values"] == first["interest_display_values"]
    assert client.calls.count("user_interest_mapping") == 1


def test_interest_edit_recalculates_mapping(taxonomy):
    client = BatchClient()
    service = GeminiService(client, taxonomy, MemoryCache())
    service.normalize_user_interests(["AI 개발"])
    service.normalize_user_interests(["영상 제작"])
    assert client.calls.count("user_interest_mapping") == 2


def test_local_alias_search_fallback(taxonomy):
    service = GeminiService(DisabledClient(), taxonomy, MemoryCache())
    mapping = service.map_search_query("그림")
    assert "미술" in mapping["keywords"]
    assert mapping["source"] == "local"
