from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .opportunity_utils import is_http_url
from .storage_service import StorageService
from .taxonomy_service import TaxonomyService, opportunity_content_hash


logger = logging.getLogger(__name__)
MISSING_TEXT = {"데이터 없음", "정보 없음", "N/A", "해당 없음", "-"}
LEGACY_SYNTHETIC_DESCRIPTION = re.compile(r"^.{1,80}에서 수집한 .+ 정보입니다\.?$")
OPTIONAL_TEXT_FIELDS = (
    "program_introduction",
    "activity_content",
    "eligibility",
    "required_documents",
    "benefits",
)


def clean_optional_text(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned or cleaned in MISSING_TEXT or LEGACY_SYNTHETIC_DESCRIPTION.match(cleaned):
        return None
    return cleaned


def import_legacy_crawl_cache_if_empty(
    storage: StorageService,
    taxonomy: TaxonomyService,
    cache_path: Path,
) -> int:
    if storage.get_existing_map() or not cache_path.is_file():
        return 0
    try:
        with cache_path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, json.JSONDecodeError):
        logger.exception("Legacy opportunity cache could not be imported.")
        return 0

    imported: list[dict[str, Any]] = []
    for raw in payload.get("items", []):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        detail_url = str(raw.get("detail_url") or "").strip()
        if not item_id or not title or not is_http_url(detail_url):
            continue
        item = {
            "id": item_id,
            "type": str(raw.get("type") or ""),
            "title": title,
            "organization": None,
            "start_date": str(raw.get("start_date") or "") or None,
            "end_date": str(raw.get("end_date") or "") or None,
            "program_introduction": clean_optional_text(raw.get("description")),
            "activity_content": None,
            "eligibility": None,
            "required_documents": None,
            "benefits": None,
            "contact": None,
            "targets": [],
            "detail_url": detail_url,
            "source": str(raw.get("source") or "legacy-crawl"),
            "source_active": True,
            "view_count": 0,
            "save_count": 0,
            "keyword_taxonomy_version": taxonomy.version,
            "classification_version": taxonomy.CLASSIFICATION_VERSION,
            "gemini_status": "local",
        }
        item.update(taxonomy.classify_local(item))
        item["content_hash"] = opportunity_content_hash(item)
        imported.append(item)
    if not imported:
        return 0
    storage.upsert_opportunities(imported)
    logger.info("Imported %s real records from the existing crawl cache.", len(imported))
    return len(imported)


def sanitize_legacy_placeholder_content(storage: StorageService) -> int:
    patches: dict[str, dict[str, Any]] = {}
    for item_id, item in storage.get_existing_map().items():
        updates: dict[str, Any] = {}
        for field in OPTIONAL_TEXT_FIELDS:
            value = item.get(field)
            cleaned = clean_optional_text(value)
            if cleaned != value:
                updates[field] = cleaned
        if updates:
            updates["content_hash"] = opportunity_content_hash({**item, **updates})
            patches[item_id] = updates
    changed = storage.patch_opportunity_payloads(patches)
    if changed:
        logger.info("Removed legacy placeholder content from %s opportunities.", changed)
    return changed
