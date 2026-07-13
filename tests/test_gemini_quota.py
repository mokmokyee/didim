from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from collector.services.gemini_client import GeminiClient, GeminiConfigurationError, GeminiError
from collector.services.gemini_quota_service import GeminiRateLimiter


def test_internal_rpm_blocks_after_one(tmp_path):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3", rpm_limit=1, rpd_limit=80)
    decisions = [limiter.reserve("test") for _ in range(2)]
    assert sum(decision.allowed for decision in decisions) == 1
    assert decisions[-1].reason == "rpm_limit"


def test_internal_rpd_blocks_after_eighty_collector_calls(tmp_path):
    current = [datetime(2026, 7, 13, 0, 0, tzinfo=timezone.utc)]
    limiter = GeminiRateLimiter(
        tmp_path / "quota.sqlite3",
        rpm_limit=1,
        rpd_limit=80,
        now_func=lambda: current[0],
    )
    for _ in range(80):
        assert limiter.reserve("daily").allowed
        current[0] += timedelta(seconds=61)
    decision = limiter.reserve("daily")
    assert not decision.allowed
    assert decision.reason == "rpd_limit"
    assert limiter.stats()["day_count"] == 80


def test_concurrent_reservations_are_atomic(tmp_path):
    path = tmp_path / "quota.sqlite3"
    limiter = GeminiRateLimiter(path, rpm_limit=1, rpd_limit=80)
    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(lambda _: limiter.reserve("parallel"), range(40)))
    assert sum(decision.allowed for decision in decisions) == 1
    assert limiter.stats()["minute_count"] == 1


def test_retry_reserves_quota_for_each_attempt(tmp_path, monkeypatch):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3", rpm_limit=1, rpd_limit=80)
    client = GeminiClient("test-key", "test-model", limiter, max_attempts=2)

    class FailingModels:
        def generate_content(self, **_kwargs):
            raise ConnectionError("temporary")

    client._client = SimpleNamespace(models=FailingModels())
    monkeypatch.setattr("collector.services.gemini_client.time.sleep", lambda _seconds: None)
    with pytest.raises(GeminiError):
        client.generate_json(purpose="retry-test", prompt="{}")
    assert limiter.stats()["day_count"] == 1
    assert limiter.stats()["purposes"]["retry-test"] == 1


def test_model_is_never_silently_substituted(tmp_path):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3")
    with pytest.raises(GeminiConfigurationError):
        GeminiClient("configured-key", "", limiter)


def test_limits_above_free_tier_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        GeminiRateLimiter(tmp_path / "rpm.sqlite3", rpm_limit=2, rpd_limit=80)
    with pytest.raises(ValueError):
        GeminiRateLimiter(tmp_path / "rpd.sqlite3", rpm_limit=1, rpd_limit=501)


def test_project_rpm_keeps_one_request_of_headroom():
    assert GeminiRateLimiter.OFFICIAL_RPM == 15
    assert 13 + GeminiRateLimiter.COLLECTOR_RPM_BUDGET == 14
    assert 14 < GeminiRateLimiter.OFFICIAL_RPM


def test_prompt_and_output_are_bounded_below_tpm_limit(tmp_path):
    limiter = GeminiRateLimiter(tmp_path / "quota.sqlite3", rpm_limit=1, rpd_limit=80)
    client = GeminiClient("test-key", "test-model", limiter, max_attempts=1)
    captured = {}

    class CapturingModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="{}")

    client._client = SimpleNamespace(models=CapturingModels())
    client.generate_json(purpose="token-bound", prompt="가" * 100_000)
    prompt_bytes = len(captured["contents"].encode("utf-8"))
    output_tokens = captured["config"].max_output_tokens
    assert prompt_bytes <= GeminiClient.MAX_PROMPT_BYTES
    assert output_tokens == GeminiClient.MAX_OUTPUT_TOKENS
    assert prompt_bytes + output_tokens < GeminiRateLimiter.OFFICIAL_TPM
