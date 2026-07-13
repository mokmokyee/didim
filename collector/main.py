from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from .config import Config
from .services.crawl_service import CrawlAlreadyRunning, CrawlService
from .services.crawler_service import CrawlerService
from .services.firebase_service import FirebaseService
from .services.gemini_client import GeminiClient
from .services.gemini_quota_service import GeminiRateLimiter
from .services.gemini_service import GeminiService
from .services.migration_service import (
    import_legacy_crawl_cache_if_empty,
    sanitize_legacy_placeholder_content,
)
from .services.storage_service import StorageService
from .services.taxonomy_service import TaxonomyService


logger = logging.getLogger(__name__)


def build_services() -> dict[str, Any]:
    firebase = FirebaseService(
        Config.FIREBASE_SERVICE_ACCOUNT_PATH,
        Config.FIREBASE_STORAGE_BUCKET,
        Config.FIREBASE_SERVICE_ACCOUNT_JSON,
    )
    if not firebase.enabled:
        raise RuntimeError("Firebase Admin credentials are required for the scheduled collector.")

    taxonomy = TaxonomyService(Config.DATA_DIR)
    storage = StorageService(Config.DATABASE_PATH, firebase)
    quota = GeminiRateLimiter(
        Config.GEMINI_QUOTA_DATABASE_PATH,
        rpm_limit=Config.GEMINI_INTERNAL_RPM,
        rpd_limit=Config.GEMINI_INTERNAL_RPD,
        central_backend=firebase,
    )
    gemini_client = GeminiClient(
        Config.GEMINI_API_KEY,
        Config.GEMINI_MODEL,
        quota,
        max_attempts=Config.GEMINI_MAX_ATTEMPTS,
    )
    gemini = GeminiService(gemini_client, taxonomy, storage)
    crawl = CrawlService(storage, CrawlerService(), gemini)
    return {
        "firebase": firebase,
        "taxonomy": taxonomy,
        "storage": storage,
        "crawl": crawl,
    }


def sync_engagement(storage: StorageService, firebase: FirebaseService) -> int:
    counts = firebase.get_engagement_counts()
    patches: dict[str, dict[str, int]] = {}
    for item_id, item in storage.get_existing_map().items():
        values = counts.get(item_id, {})
        view_count = int(values.get("view_count", 0))
        save_count = int(values.get("save_count", 0))
        if int(item.get("view_count", 0)) != view_count or int(item.get("save_count", 0)) != save_count:
            patches[item_id] = {"view_count": view_count, "save_count": save_count}
    return storage.patch_opportunity_payloads(patches)


def run(*, seed_only: bool = False) -> dict[str, Any]:
    services = build_services()
    firebase: FirebaseService = services["firebase"]
    taxonomy: TaxonomyService = services["taxonomy"]
    storage: StorageService = services["storage"]
    imported = import_legacy_crawl_cache_if_empty(
        storage,
        taxonomy,
        Config.DATA_DIR / "opportunities_cache.json",
    )
    sanitized = sanitize_legacy_placeholder_content(storage)

    result: dict[str, Any] = {
        "mode": "seed" if seed_only else "crawl",
        "legacy_imported": imported,
        "sanitized": sanitized,
    }
    if not seed_only:
        try:
            result["crawl"] = services["crawl"].run()
        except CrawlAlreadyRunning:
            result["crawl"] = {"status": "skipped", "reason": "already_running"}

    result["engagement_updated"] = sync_engagement(storage, firebase)
    catalog_items = storage.all_opportunities()
    result["catalog"] = firebase.publish_catalog(catalog_items)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect DiDim opportunities and publish Firestore data.")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Publish the bundled opportunity cache without crawling external sites.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run(seed_only=args.seed_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
