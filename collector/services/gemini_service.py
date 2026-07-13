from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

from .gemini_client import GeminiClient, GeminiError, GeminiQuotaExceeded
from .taxonomy_service import TaxonomyService, normalize_lookup, normalize_text, opportunity_content_hash


logger = logging.getLogger(__name__)


class CacheStore(Protocol):
    def cache_get(self, collection: str, key: str) -> dict[str, Any] | None: ...

    def cache_set(self, collection: str, key: str, payload: dict[str, Any]) -> None: ...


class GeminiService:
    BATCH_SIZE = 30

    def __init__(self, client: GeminiClient, taxonomy: TaxonomyService, storage: CacheStore):
        self.client = client
        self.taxonomy = taxonomy
        self.storage = storage

    def enrich_opportunities(
        self,
        raw_items: list[dict[str, Any]],
        existing_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        existing_by_id = existing_by_id or {}
        finalized: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []

        for raw in raw_items:
            item = self._prepare_opportunity(raw)
            item_id = str(item.get("id", ""))
            existing = existing_by_id.get(item_id, {})
            if existing and existing.get("content_hash") == item["content_hash"]:
                item["keywords"] = self.taxonomy.validate_keywords(existing.get("keywords", []))
                item["participation_mode"] = self._validate_mode(existing.get("participation_mode"))
                item["regions"] = self.taxonomy.validate_regions(existing.get("regions", []))
                item["gemini_status"] = existing.get("gemini_status", "complete")
                finalized.append(item)
            else:
                local = self.taxonomy.classify_local(item)
                item.update(local)
                item["gemini_status"] = "pending" if self.client.enabled else "local"
                changed.append(item)

        if changed and self.client.enabled:
            quota_exhausted = False
            for start in range(0, len(changed), self.BATCH_SIZE):
                batch = changed[start : start + self.BATCH_SIZE]
                if quota_exhausted:
                    continue
                try:
                    parsed = self.client.generate_json(
                        purpose="opportunity_classification",
                        prompt=self._classification_prompt(batch),
                    )
                    classified = self._validate_classification_response(parsed, batch)
                    for item in batch:
                        result = classified.get(str(item["id"]))
                        if result:
                            item.update(result)
                            item["gemini_status"] = "complete"
                except GeminiQuotaExceeded:
                    quota_exhausted = True
                    logger.warning("Gemini quota exhausted; remaining opportunity batches stay pending.")
                except GeminiError:
                    logger.exception("Opportunity classification failed; local classification is retained.")

        finalized.extend(changed)
        return finalized

    def normalize_user_interests(self, display_values: list[str]) -> dict[str, Any]:
        cleaned = self._clean_display_values(display_values)
        cache_key = self._mapping_cache_key(cleaned)
        cached = self.storage.cache_get("keyword_mappings", cache_key)
        if cached:
            return {
                "interest_display_values": cleaned,
                "interest_keywords": self.taxonomy.validate_keywords(
                    cached.get("interest_keywords", []), max_count=12
                ),
                "source": cached.get("source", "cache"),
            }

        keywords = self.taxonomy.local_match(cleaned, max_count=12)
        source = "local"
        if cleaned and self.client.enabled:
            try:
                parsed = self.client.generate_json(
                    purpose="user_interest_mapping",
                    prompt=self._interest_prompt(cleaned),
                )
                candidate = parsed.get("keywords", []) if isinstance(parsed, dict) else []
                validated = self.taxonomy.validate_keywords(candidate, max_count=12)
                if validated:
                    keywords = validated
                    source = "gemini"
            except GeminiError:
                logger.info("User interest mapping used local fallback.")

        payload = {
            "interest_display_values": cleaned,
            "interest_keywords": keywords,
            "source": source,
            "taxonomy_version": self.taxonomy.version,
        }
        self.storage.cache_set("keyword_mappings", cache_key, payload)
        return payload

    def map_search_query(self, query: str) -> dict[str, Any]:
        original = normalize_text(query)[:100]
        normalized = normalize_lookup(original)
        cache_key = hashlib.sha256(
            f"{self.taxonomy.version}|{normalized}".encode("utf-8")
        ).hexdigest()
        cached = self.storage.cache_get("search_keyword_cache", cache_key)
        if cached:
            return {
                "query": original,
                "keywords": self.taxonomy.validate_keywords(cached.get("keywords", []), max_count=12),
                "source": "cache",
            }

        keywords = self.taxonomy.local_match([original], max_count=12)
        source = "local"
        if original and self.client.enabled:
            try:
                parsed = self.client.generate_json(
                    purpose="search_keyword_mapping",
                    prompt=self._search_prompt(original),
                )
                candidate = parsed.get("keywords", []) if isinstance(parsed, dict) else []
                validated = self.taxonomy.validate_keywords(candidate, max_count=12)
                if validated:
                    keywords = validated
                    source = "gemini"
            except GeminiError:
                logger.info("Search keyword mapping used local fallback.")

        payload = {
            "query": original,
            "normalized_query": normalized,
            "keywords": keywords,
            "source": source,
            "taxonomy_version": self.taxonomy.version,
        }
        self.storage.cache_set("search_keyword_cache", cache_key, payload)
        return payload

    def _prepare_opportunity(self, raw: dict[str, Any]) -> dict[str, Any]:
        item = dict(raw)
        for field in (
            "title",
            "type",
            "organization",
            "start_date",
            "end_date",
            "program_introduction",
            "activity_content",
            "eligibility",
            "required_documents",
            "benefits",
            "detail_url",
            "source",
            "raw_text",
        ):
            value = normalize_text(item.get(field))
            item[field] = value or None
        item["id"] = normalize_text(item.get("id"))
        item["content_hash"] = opportunity_content_hash(item)
        item["keyword_taxonomy_version"] = self.taxonomy.version
        item["source_active"] = bool(item.get("source_active", True))
        return item

    def _validate_classification_response(
        self,
        parsed: Any,
        batch: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        parsed_items = parsed.get("items", []) if isinstance(parsed, dict) else []
        if not isinstance(parsed_items, list):
            return {}
        allowed_ids = {str(item["id"]) for item in batch}
        result: dict[str, dict[str, Any]] = {}
        for raw in parsed_items:
            if not isinstance(raw, dict):
                continue
            item_id = normalize_text(raw.get("id"))
            if item_id not in allowed_ids or item_id in result:
                continue
            mode = self._validate_mode(raw.get("participation_mode"))
            regions = self.taxonomy.validate_regions(raw.get("regions", []))
            if mode == "online":
                regions = []
            result[item_id] = {
                "keywords": self.taxonomy.validate_keywords(raw.get("keywords", [])),
                "participation_mode": mode,
                "regions": regions if mode in {"offline", "hybrid"} else [],
            }
        return result

    def _classification_prompt(self, items: list[dict[str, Any]]) -> str:
        compact = []
        for item in items:
            compact.append(
                {
                    "id": item.get("id"),
                    "title": normalize_text(item.get("title"))[:180],
                    "type": normalize_text(item.get("type"))[:40],
                    "program_introduction": normalize_text(item.get("program_introduction"))[:180],
                    "activity_content": normalize_text(item.get("activity_content"))[:180],
                    "eligibility": normalize_text(item.get("eligibility"))[:180],
                    "required_documents": normalize_text(item.get("required_documents"))[:180],
                    "benefits": normalize_text(item.get("benefits"))[:180],
                    "organization": normalize_text(item.get("organization"))[:180],
                    "existing_description": normalize_text(item.get("raw_text"))[:180],
                }
            )
        return (
            "한국 공모전·장학금 분류기다. 입력 사실만 사용하고 누락 정보를 만들지 마라. "
            "keywords는 allowed_keywords 안의 값만 항목당 최대 4개 반환한다. "
            "participation_mode는 online, offline, hybrid, unknown 중 하나다. "
            "regions는 allowed_regions 안의 값만 사용하고 online이면 빈 배열이다. "
            "입력에 있는 id만 한 번씩 반환한다. 설명과 Markdown 없이 JSON 객체만 반환한다.\n"
            "출력: {\"items\":[{\"id\":\"...\",\"keywords\":[\"...\"],"
            "\"participation_mode\":\"unknown\",\"regions\":[]}]}\n"
            f"allowed_keywords={json.dumps(self.taxonomy.labels, ensure_ascii=False)}\n"
            f"allowed_regions={json.dumps(self.taxonomy.regions, ensure_ascii=False)}\n"
            f"items={json.dumps(compact, ensure_ascii=False)}"
        )

    def _interest_prompt(self, display_values: list[str]) -> str:
        return (
            "사용자가 입력한 관심 분야 원문을 변경하지 말고, 의미상 관련된 allowed_keywords만 고른다. "
            "새 키워드를 만들지 말고 JSON 객체만 반환한다.\n"
            "출력: {\"keywords\":[\"키워드\"]}\n"
            f"allowed_keywords={json.dumps(self.taxonomy.labels, ensure_ascii=False)}\n"
            f"interest_display_values={json.dumps(display_values, ensure_ascii=False)}"
        )

    def _search_prompt(self, query: str) -> str:
        return (
            "검색어와 의미상 관련된 allowed_keywords를 고른다. 새 키워드를 만들지 말고 "
            "JSON 객체만 반환한다. 관련 키워드가 없으면 빈 배열이다.\n"
            "출력: {\"keywords\":[\"키워드\"]}\n"
            f"allowed_keywords={json.dumps(self.taxonomy.labels, ensure_ascii=False)}\n"
            f"query={json.dumps(query, ensure_ascii=False)}"
        )

    def _mapping_cache_key(self, display_values: list[str]) -> str:
        normalized = sorted(normalize_lookup(value) for value in display_values)
        return hashlib.sha256(
            f"{self.taxonomy.version}|{json.dumps(normalized, ensure_ascii=False)}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _clean_display_values(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values or []:
            cleaned = normalize_text(value)[:80]
            if cleaned and cleaned not in result:
                result.append(cleaned)
            if len(result) >= 20:
                break
        return result

    def _validate_mode(self, value: Any) -> str:
        mode = normalize_text(value).lower()
        return mode if mode in self.taxonomy.PARTICIPATION_MODES else "unknown"
