from __future__ import annotations

from types import SimpleNamespace

import pytest

from collector.services.crawler_service import CrawlerService
from collector.services.opportunity_utils import stable_id
from collector.services.opportunity_utils import is_safe_crawl_url


def test_stable_id_uses_source_and_canonical_url_not_mutable_title():
    first = stable_id("이전 제목", "https://example.org/post/7?utm_source=test", "source")
    renamed = stable_id("변경된 제목", "https://example.org/post/7", "source")
    other_source = stable_id("변경된 제목", "https://example.org/post/7", "other")
    assert first == renamed
    assert first != other_source


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://127.0.0.1/private",
        "http://localhost/private",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_unsafe_crawl_urls_are_blocked(url):
    assert not is_safe_crawl_url(url)


def test_detail_crawl_collects_real_optional_fields(monkeypatch):
    html = """
    <html><head><meta name="description" content="실제 소개"></head><body>
      <dl>
        <dt>주최기관</dt><dd>테스트 재단</dd>
        <dt>활동 내용</dt><dd>멘토링 활동</dd>
        <dt>지원 자격</dt><dd>대학생</dd>
        <dt>제출 서류</dt><dd>지원서</dd>
        <dt>혜택</dt><dd>장학금 100만원</dd>
        <dt>문의처</dt><dd>help@example.org</dd>
      </dl>
    </body></html>
    """
    crawler = CrawlerService()
    monkeypatch.setattr(crawler, "_get", lambda _url: SimpleNamespace(text=html, url=_url))
    item = crawler._build_item(
        "scholarship",
        "테스트 장학금",
        "테스트 장학금 2026-07-01 ~ 2026-08-01",
        "source",
        "https://example.org/list",
        "/detail/1",
    )
    enriched = crawler._enrich_from_detail(item)
    assert enriched["organization"] == "테스트 재단"
    assert enriched["activity_content"] == "멘토링 활동"
    assert enriched["eligibility"] == "대학생"
    assert enriched["required_documents"] == "지원서"
    assert enriched["benefits"] == "장학금 100만원"
    assert enriched["contact"] == "help@example.org"
    assert enriched["targets"] == ["대학생"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("참가 자격 정보 없음", ["전 연령"]),
        ("전국 고등학생 참가 가능", ["고등학생"]),
        ("대학생 서포터즈 모집", ["대학생"]),
        ("고등학생 및 대학생 대상", ["고등학생", "대학생"]),
        ("청소년 프로그램", ["전 연령"]),
        ("대학원생 연구 지원", ["전 연령"]),
        ("누구나 참여 가능", ["전 연령"]),
    ],
)
def test_target_inference_requires_explicit_student_type(text, expected):
    assert CrawlerService._infer_targets(text) == expected


@pytest.mark.parametrize("placeholder", ["데이터 없음", "정보 없음", "N/A", "해당 없음", "-"])
def test_missing_placeholder_text_is_not_stored(monkeypatch, placeholder):
    crawler = CrawlerService()
    html = f"<html><body><dl><dt>혜택</dt><dd>{placeholder}</dd></dl></body></html>"
    monkeypatch.setattr(crawler, "_get", lambda _url: SimpleNamespace(text=html, url=_url))
    item = crawler._build_item(
        "contest",
        "테스트 공모전",
        "테스트 공모전",
        "source",
        "https://example.org/list",
        "/detail/2",
    )
    assert crawler._enrich_from_detail(item)["benefits"] is None


def test_failed_or_empty_source_is_not_marked_successful(monkeypatch):
    crawler = CrawlerService()

    def fail(_type, _url):
        raise TimeoutError("timeout")

    monkeypatch.setattr(crawler, "_collect_from_list", fail)
    result = crawler.collect_run({"contest": ["https://example.org/list"]})
    assert result.successful_sources == set()
    assert result.failed_sources


def test_local_crawl_lock_prevents_duplicate_run(storage):
    owner = storage.acquire_lock("opportunities", ttl_seconds=60)
    assert owner
    assert storage.acquire_lock("opportunities", ttl_seconds=60) is None
    storage.release_lock("opportunities", owner)
    assert storage.acquire_lock("opportunities", ttl_seconds=60)
