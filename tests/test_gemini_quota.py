from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from collector.services.gemini_client import GeminiClient, GeminiConfigurationError, GeminiError
from collector.services.gemini_quota_service import GeminiRateLimiter


def test_internal_rpm_blocks_after_fourteen(tmp_path):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3", rpm_limit=14, rpd_limit=480)
    decisions = [limiter.reserve("test") for _ in range(15)]
    assert sum(decision.allowed for decision in decisions) == 14
    assert decisions[-1].reason == "rpm_limit"


def test_internal_rpd_blocks_after_480(tmp_path):
    current = [datetime(2026, 7, 13, 0, 0, tzinfo=timezone.utc)]
    limiter = GeminiRateLimiter(
        tmp_path / "quota.sqlite3",
        rpm_limit=14,
        rpd_limit=480,
        now_func=lambda: current[0],
    )
    for _ in range(480):
        assert limiter.reserve("daily").allowed
        current[0] += timedelta(seconds=61)
    decision = limiter.reserve("daily")
    assert not decision.allowed
    assert decision.reason == "rpd_limit"
    assert limiter.stats()["day_count"] == 480


def test_concurrent_reservations_are_atomic(tmp_path):
    path = tmp_path / "quota.sqlite3"
    limiter = GeminiRateLimiter(path, rpm_limit=14, rpd_limit=480)
    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(lambda _: limiter.reserve("parallel"), range(40)))
    assert sum(decision.allowed for decision in decisions) == 14
    assert limiter.stats()["minute_count"] == 14


def test_retry_reserves_quota_for_each_attempt(tmp_path, monkeypatch):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3", rpm_limit=14, rpd_limit=480)
    client = GeminiClient("test-key", "test-model", limiter, max_attempts=2)

    class FailingModels:
        def generate_content(self, **_kwargs):
            raise ConnectionError("temporary")

    client._client = SimpleNamespace(models=FailingModels())
    monkeypatch.setattr("collector.services.gemini_client.time.sleep", lambda _seconds: None)
    with pytest.raises(GeminiError):
        client.generate_json(purpose="retry-test", prompt="{}")
    assert limiter.stats()["day_count"] == 2
    assert limiter.stats()["purposes"]["retry-test"] == 2


def test_model_is_never_silently_substituted(tmp_path):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3")
    with pytest.raises(GeminiConfigurationError):
        GeminiClient("configured-key", "", limiter)
