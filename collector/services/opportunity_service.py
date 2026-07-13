from __future__ import annotations

from typing import Any, Iterable

from .gemini_service import GeminiService
from .storage_service import StorageService
from .taxonomy_service import TaxonomyService, normalize_text


TYPE_ALIASES = {
    "공모전": "contest",
    "contest": "contest",
    "장학금": "scholarship",
    "scholarship": "scholarship",
}


class OpportunityService:
    def __init__(
        self,
        storage: StorageService,
        taxonomy: TaxonomyService,
        gemini: GeminiService,
    ):
        self.storage = storage
        self.taxonomy = taxonomy
        self.gemini = gemini

    def list_opportunities(
        self,
        *,
        types: Iterable[str] = (),
        targets: Iterable[str] = (),
        categories: Iterable[str] = (),
        regions: Iterable[str] = (),
        status: str = "active",
        sort: str = "recommend",
        page: int = 1,
        page_size: int = 24,
    ) -> dict[str, Any]:
        normalized_types = [TYPE_ALIASES[value] for value in types if value in TYPE_ALIASES]
        keywords = self.taxonomy.filter_keywords(categories)
        return self.storage.list_opportunities(
            types=normalized_types,
            targets=targets,
            keywords=keywords,
            regions=regions,
            status=status,
            sort=sort,
            page=page,
            page_size=page_size,
        )

    def search(
        self,
        query: str,
        *,
        types: Iterable[str] = (),
        targets: Iterable[str] = (),
        categories: Iterable[str] = (),
        regions: Iterable[str] = (),
        sort: str = "recommend",
        page: int = 1,
        page_size: int = 24,
    ) -> dict[str, Any]:
        query = normalize_text(query)[:100]
        mapping = self.gemini.map_search_query(query)
        normalized_types = [TYPE_ALIASES[value] for value in types if value in TYPE_ALIASES]
        category_keywords = self.taxonomy.filter_keywords(categories)
        result = self.storage.list_opportunities(
            types=normalized_types,
            targets=targets,
            keywords=category_keywords,
            regions=regions,
            status="active",
            title_query=query,
            keyword_query=mapping["keywords"],
            sort=sort,
            page=page,
            page_size=page_size,
        )
        result["query"] = query
        result["matched_keywords"] = mapping["keywords"]
        result["mapping_source"] = mapping["source"]
        return result

    def get_detail(self, opportunity_id: str, *, increment_view: bool = True) -> dict[str, Any] | None:
        item = self.storage.get_opportunity(opportunity_id)
        if not item:
            return None
        if increment_view:
            self.storage.increment_view(opportunity_id)
            item["view_count"] = int(item.get("view_count", 0)) + 1
        return item

    def recommendations(self, user: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
        candidates = self.storage.list_opportunities(page=1, page_size=100, status="active")["items"]
        interests = set(user.get("interest_keywords", []))
        preferred_regions = set(user.get("preferred_regions", []))
        preferred_types = {
            TYPE_ALIASES[value]
            for value in user.get("preferred_types", [])
            if value in TYPE_ALIASES
        }
        saved_keywords: set[str] = set()
        saved_type_counts: dict[str, int] = {}
        uid = str(user.get("uid") or "")
        if uid:
            for saved_id in self.storage.get_saved_ids(uid):
                saved_item = self.storage.get_opportunity(saved_id)
                if not saved_item:
                    continue
                saved_keywords.update(str(value) for value in saved_item.get("keywords", []))
                saved_type = str(saved_item.get("type") or "")
                if saved_type:
                    saved_type_counts[saved_type] = saved_type_counts.get(saved_type, 0) + 1
        if not preferred_types and saved_type_counts:
            highest = max(saved_type_counts.values())
            preferred_types = {
                value for value, count in saved_type_counts.items() if count == highest
            }
        user_type = str(user.get("user_type") or user.get("userType") or "")

        scored: list[tuple[int, dict[str, Any], list[str]]] = []
        for item in candidates:
            score = 0
            reasons: list[str] = []
            overlap = interests.intersection(item.get("keywords", []))
            if overlap:
                score += len(overlap) * 20
                reasons.append("관심 분야 " + ", ".join(sorted(overlap)))
            saved_overlap = saved_keywords.intersection(item.get("keywords", []))
            if saved_overlap:
                score += len(saved_overlap) * 6
                reasons.append("저장한 프로그램과 비슷한 분야")
            targets = item.get("targets") or item.get("target") or []
            if isinstance(targets, str):
                targets = [targets]
            if user_type and user_type in targets:
                score += 15
                reasons.append("모집 대상")
            if preferred_types and item.get("type") in preferred_types:
                score += 8
                reasons.append("선호 유형")
            mode = item.get("participation_mode")
            regions = set(item.get("regions", []))
            if preferred_regions and (mode in {"online", "hybrid"} or preferred_regions.intersection(regions)):
                score += 10
                reasons.append("선호 지역")
            score += min(int(item.get("view_count", 0)) // 500, 5)
            scored.append((score, item, reasons))

        scored.sort(key=lambda row: (row[0], -int(row[1].get("d_day") or 999999)), reverse=True)
        recommendations: list[dict[str, Any]] = []
        for score, item, reasons in scored[: max(1, min(int(limit), 50))]:
            reason = (
                " · ".join(reasons) + " 조건과 잘 맞는 프로그램이에요."
                if reasons
                else "현재 모집 중인 프로그램 중 인기도가 높은 프로그램이에요."
            )
            recommendations.append({**item, "recommendation_score": score, "recommendation_reason": reason})
        return recommendations
