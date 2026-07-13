from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable


CONTENT_HASH_FIELDS = (
    "title",
    "program_introduction",
    "activity_content",
    "eligibility",
    "required_documents",
    "benefits",
    "organization",
    "start_date",
    "end_date",
)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_lookup(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", normalize_text(value).lower())


def opportunity_content_hash(item: dict[str, Any]) -> str:
    payload = {
        field: normalize_text(item.get(field))
        for field in CONTENT_HASH_FIELDS
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TaxonomyService:
    MAX_KEYWORDS = 4
    PARTICIPATION_MODES = {"online", "offline", "hybrid", "unknown"}

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent / "data"
        taxonomy = self._load_json("keyword_taxonomy.json")
        filter_map = self._load_json("filter_keyword_map.json")
        regions = self._load_json("regions.json")

        self.version = int(taxonomy["version"])
        self.keywords = list(taxonomy["keywords"])
        self.labels = [str(item["label"]) for item in self.keywords]
        self.label_set = set(self.labels)
        self.by_label = {str(item["label"]): item for item in self.keywords}
        self.filter_version = int(filter_map["version"])
        self.filter_map = {
            str(label): self.validate_keywords(values, max_count=100)
            for label, values in filter_map["filters"].items()
        }
        self.regions_version = int(regions["version"])
        self.regions = [str(value) for value in regions["regions"]]
        self.region_set = set(self.regions)

        self._terms: list[tuple[str, str, int]] = []
        self._exact_terms: dict[str, list[str]] = {}
        for keyword in self.keywords:
            label = str(keyword["label"])
            for term in [label, *keyword.get("aliases", [])]:
                normalized = normalize_lookup(term)
                if normalized:
                    self._terms.append((normalized, label, len(normalized)))
                    labels = self._exact_terms.setdefault(normalized, [])
                    if label not in labels:
                        labels.append(label)
        self._terms.sort(key=lambda row: row[2], reverse=True)

    def _load_json(self, filename: str) -> dict[str, Any]:
        with (self.data_dir / filename).open("r", encoding="utf-8") as source:
            payload = json.load(source)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid taxonomy file: {filename}")
        return payload

    def validate_keywords(self, values: Iterable[Any], max_count: int | None = None) -> list[str]:
        limit = self.MAX_KEYWORDS if max_count is None else max(0, int(max_count))
        result: list[str] = []
        for value in values or []:
            label = normalize_text(value)
            if label in self.label_set and label not in result:
                result.append(label)
            if len(result) >= limit:
                break
        return result

    def validate_regions(self, values: Iterable[Any]) -> list[str]:
        result: list[str] = []
        for value in values or []:
            region = normalize_text(value)
            if region in self.region_set and region not in result:
                result.append(region)
        return result

    def filter_keywords(self, ui_filters: Iterable[str]) -> list[str]:
        result: list[str] = []
        for ui_filter in ui_filters or []:
            for keyword in self.filter_map.get(normalize_text(ui_filter), []):
                if keyword not in result:
                    result.append(keyword)
        return result

    def exact_match(self, value: Any, max_count: int = MAX_KEYWORDS) -> list[str]:
        """Return canonical labels only when the full normalized term is registered."""
        normalized = normalize_lookup(value)
        return list(self._exact_terms.get(normalized, []))[:max_count]

    def local_match(self, values: Iterable[Any], max_count: int = MAX_KEYWORDS) -> list[str]:
        result: list[str] = []
        for value in values or []:
            normalized = normalize_lookup(value)
            if not normalized:
                continue
            for term, label, _length in self._terms:
                if term == normalized or term in normalized or normalized in term:
                    if label not in result:
                        result.append(label)
                    if len(result) >= max_count:
                        return result
        return result

    def classify_local(self, item: dict[str, Any]) -> dict[str, Any]:
        blob = " ".join(
            normalize_text(item.get(field))
            for field in (
                "title",
                "type",
                "program_introduction",
                "activity_content",
                "eligibility",
                "required_documents",
                "benefits",
                "organization",
                "raw_text",
            )
        )
        keywords = self.local_match([blob], self.MAX_KEYWORDS)
        participation_mode = self._local_participation_mode(blob)
        regions = self._local_regions(blob) if participation_mode in {"offline", "hybrid"} else []
        return {
            "keywords": keywords,
            "participation_mode": participation_mode,
            "regions": regions,
        }

    def _local_participation_mode(self, text: str) -> str:
        normalized = normalize_lookup(text)
        hybrid_terms = ("온오프라인", "온라인오프라인", "하이브리드", "병행")
        has_online = "온라인" in normalized or "비대면" in normalized
        has_offline = "오프라인" in normalized or "대면" in normalized or "현장" in normalized
        if any(term in normalized for term in hybrid_terms) or (has_online and has_offline):
            return "hybrid"
        if has_online:
            return "online"
        if has_offline:
            return "offline"
        return "unknown"

    def _local_regions(self, text: str) -> list[str]:
        normalized = normalize_lookup(text)
        aliases = {
            "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
            "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
            "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
            "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
            "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
            "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
        }
        found: list[str] = []
        for alias, region in aliases.items():
            if normalize_lookup(alias) in normalized and region not in found:
                found.append(region)
        for region in self.regions:
            if region != "전국" and normalize_lookup(region) in normalized and region not in found:
                found.append(region)
        return found
