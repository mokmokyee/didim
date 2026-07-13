from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from collector.data.source_urls import SOURCE_URLS

from .crawler_service import CrawlerService
from .gemini_service import GeminiService
from .storage_service import StorageService


logger = logging.getLogger(__name__)


class CrawlAlreadyRunning(RuntimeError):
    pass


class CrawlService:
    LOCK_NAME = "opportunities"

    def __init__(
        self,
        storage: StorageService,
        crawler: CrawlerService,
        gemini: GeminiService,
    ):
        self.storage = storage
        self.crawler = crawler
        self.gemini = gemini

    def run(self) -> dict[str, Any]:
        owner = self.storage.acquire_lock(self.LOCK_NAME, ttl_seconds=60 * 60 * 3)
        if not owner:
            raise CrawlAlreadyRunning("Another opportunity crawl is already running.")

        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "run_id": run_id,
            "status": "running",
            "started_at": started_at.isoformat(),
        }
        self.storage.save_crawl_run(run_id, payload)
        try:
            crawl_result = self.crawler.collect_run(SOURCE_URLS)
            existing = self.storage.get_existing_map()
            items = self.gemini.enrich_opportunities(crawl_result.items, existing)
            persistence = self.storage.upsert_opportunities(items, crawl_result.successful_sources)
            pending = sum(1 for item in items if item.get("gemini_status") == "pending")
            payload.update(
                {
                    "status": "completed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "collected_count": len(crawl_result.items),
                    "stored_count": len(items),
                    "gemini_pending_count": pending,
                    "successful_sources": sorted(crawl_result.successful_sources),
                    "failed_sources": crawl_result.failed_sources,
                    **persistence,
                }
            )
            self.storage.save_crawl_run(run_id, payload)
            return payload
        except Exception as exc:
            payload.update(
                {
                    "status": "failed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error_type": type(exc).__name__,
                }
            )
            self.storage.save_crawl_run(run_id, payload)
            logger.exception("Opportunity crawl failed run_id=%s", run_id)
            raise
        finally:
            self.storage.release_lock(self.LOCK_NAME, owner)
