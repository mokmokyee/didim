from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup, Tag

from .opportunity_utils import (
    canonical_url,
    clean_text,
    dedupe_items,
    extract_dates,
    is_http_url,
    is_safe_crawl_url,
    stable_id,
)


logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class CrawlResult:
    items: list[dict[str, Any]]
    successful_sources: set[str]
    failed_sources: dict[str, list[str]]


class CrawlerService:
    def __init__(self):
        self.timeout = (5, 12)
        self.sotong_timeout = (4, 8)
        self.session = requests.Session()
        self.session.max_redirects = 5
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def collect_opportunities(self, source_urls: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
        return self.collect_run(source_urls).items

    def collect_run(self, source_urls: Mapping[str, Sequence[str]]) -> CrawlResult:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        attempted: dict[str, int] = {}
        source_item_counts: dict[str, int] = {}
        failed_sources: dict[str, list[str]] = {}

        for opportunity_type, urls in source_urls.items():
            for list_url in urls:
                source = self._source_name(list_url)
                attempted[source] = attempted.get(source, 0) + 1
                try:
                    page_items = self._collect_from_list(opportunity_type, list_url)
                except Exception as exc:
                    logger.warning("Skipped source URL after crawl failure: %s (%s)", list_url, exc)
                    failed_sources.setdefault(source, []).append(list_url)
                    continue

                source_item_counts[source] = source_item_counts.get(source, 0) + len(page_items)

                for item in page_items:
                    dedupe_key = canonical_url(str(item.get("detail_url", "")))
                    if not dedupe_key or dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    items.append(item)

        deduped = dedupe_items(items)
        enriched: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="didim-detail") as executor:
            futures = {executor.submit(self._enrich_from_detail, item): item for item in deduped}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    enriched.append(future.result())
                except Exception as exc:
                    logger.warning(
                        "Detail crawl failed; keeping list data id=%s source=%s error=%s",
                        item.get("id"),
                        item.get("source"),
                        type(exc).__name__,
                    )
                    enriched.append(item)

        successful_sources = {
            source
            for source in attempted
            if source not in failed_sources and source_item_counts.get(source, 0) > 0
        }
        for source in attempted:
            if source_item_counts.get(source, 0) == 0:
                failed_sources.setdefault(source, []).append("no_items_parsed")
        return CrawlResult(enriched, successful_sources, failed_sources)

    def _collect_from_list(self, opportunity_type: str, list_url: str) -> list[dict[str, Any]]:
        if "sotong.go.kr" in list_url:
            html = self._fetch_sotong_list(list_url)
        else:
            html = self._get(list_url).text

        soup = BeautifulSoup(html, "html.parser")
        source = self._source_name(list_url)

        if "wevity.com" in list_url:
            return self._parse_wevity(soup, opportunity_type, source, list_url)
        if "linkareer.com" in list_url:
            return self._parse_linkareer(soup, opportunity_type, source, list_url)
        if "contestkorea.com" in list_url:
            return self._parse_contest_korea(soup, opportunity_type, source, list_url)
        if "sotong.go.kr" in list_url:
            return self._parse_sotong(soup, opportunity_type, source, list_url)
        if "dreamspon.com" in list_url:
            return self._parse_dreamspon(soup, opportunity_type, source, list_url)
        if "seoulfuture.or.kr" in list_url:
            return self._parse_seoul_future(soup, opportunity_type, source, list_url)
        if "kosaf.go.kr" in list_url:
            return self._parse_kosaf(soup, opportunity_type, source, list_url)

        return self._parse_generic(soup, opportunity_type, source, list_url)

    def _get(self, url: str) -> requests.Response:
        if not is_safe_crawl_url(url):
            raise ValueError("Only public HTTP(S) crawl URLs are allowed.")
        last_error: requests.RequestException | None = None
        for attempt in range(2):
            session = requests.Session()
            session.max_redirects = 5
            try:
                current_url = url
                response = None
                for _redirect in range(6):
                    if not is_safe_crawl_url(current_url):
                        raise requests.RequestException("Unsafe crawl redirect URL.")
                    response = session.get(
                        current_url,
                        timeout=self.timeout,
                        headers=self.headers,
                        verify=("sotong.go.kr" not in current_url),
                        allow_redirects=False,
                    )
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location", "")
                        current_url = urljoin(current_url, location)
                        continue
                    break
                if response is None or response.is_redirect or response.is_permanent_redirect:
                    raise requests.TooManyRedirects("Crawl redirect limit exceeded.")
                response.raise_for_status()
                if not is_safe_crawl_url(response.url):
                    raise requests.RequestException("Crawl redirect left public HTTP(S).")
                if not response.encoding or response.encoding.lower() == "iso-8859-1":
                    response.encoding = response.apparent_encoding
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.2)
            finally:
                session.close()
        if last_error:
            raise last_error
        raise requests.RequestException("Crawl request failed.")

    def _fetch_sotong_list(self, list_url: str) -> str:
        parsed = urlparse(list_url)
        query = parse_qs(parsed.query)
        data = {key: values[0] if values else "" for key, values in query.items()}
        data.setdefault("pagetype", "bbs")
        data.setdefault("date_range", "all")
        data.setdefault("date_range_cnddt", "all")

        endpoint = "https://sotong.go.kr/front/epilogue/epilogueNewList.do"
        last_error: requests.RequestException | None = None
        for attempt in range(2):
            session = self.session if attempt == 0 else requests.Session()
            session.max_redirects = 5
            try:
                response = session.post(
                    endpoint,
                    data=data,
                    timeout=self.sotong_timeout,
                    headers={**self.headers, "Referer": list_url, "Connection": "close"},
                    verify=False,
                    allow_redirects=False,
                )
                response.raise_for_status()
                if response.is_redirect or response.is_permanent_redirect:
                    raise requests.RequestException("Unexpected crawl redirect.")
                if not is_safe_crawl_url(response.url):
                    raise requests.RequestException("Crawl redirect left public HTTP(S).")
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except requests.RequestException as exc:
                last_error = exc
        if last_error:
            raise last_error
        return ""

    def _parse_wevity(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select('a[href*="gbn=view"][href*="ix="]'):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not self._is_useful_title(title):
                continue
            raw_text = self._ancestor_text(anchor, ["li", "tr", "div"]) or title
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, anchor.get("href", ""))
            if item:
                items.append(item)
        return items

    def _parse_linkareer(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select('a[href^="/activity/"], a[href*="linkareer.com/activity/"]'):
            title = self._clean_text(re.sub(r"^추천\s*", "", anchor.get_text(" ", strip=True)))
            if not self._is_useful_title(title):
                continue
            raw_text = self._ancestor_text(anchor, ["article", "li", "div"]) or title
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, anchor.get("href", ""))
            if item:
                items.append(item)
        return items

    def _parse_contest_korea(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select('a[href*="/sub/view.php"]'):
            title_node = anchor.select_one(".title") or anchor.select_one(".contest_title")
            title = self._clean_text(title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True))
            title = re.sub(r"^D-\d+\s*", "", title)
            if not self._is_useful_title(title):
                continue
            raw_text = self._ancestor_text(anchor, ["li", "article", "div"]) or title
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, anchor.get("href", ""))
            if item:
                items.append(item)
        return items

    def _parse_sotong(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select("a.contest-con[href]"):
            title_node = anchor.select_one(".con-title .title")
            title = self._clean_text(title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True))
            if not self._is_useful_title(title):
                continue
            raw_text = self._clean_text(anchor.get_text(" ", strip=True))
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, anchor.get("href", ""))
            if item:
                items.append(item)
        return items

    def _parse_dreamspon(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for row in soup.select("tbody tr"):
            anchor = row.select_one('a[href*="scholarship/view.html"]')
            if not anchor:
                continue
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not self._is_useful_title(title):
                continue
            raw_text = self._clean_text(row.get_text(" ", strip=True))
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, anchor.get("href", ""))
            if item:
                items.append(item)
        return items

    def _parse_seoul_future(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select('a.box[onclick*="fn_edit"]'):
            title_node = anchor.select_one(".title")
            title = self._clean_text(title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True))
            if not self._is_useful_title(title):
                continue

            onclick = anchor.get("onclick", "")
            match = re.search(r"fn_edit\('([^']+)'", onclick)
            if not match:
                continue
            idx = match.group(1)
            view_url = list_url.split("?", 1)[0].replace("/index.do", "/view.do")
            # 서울미래인재재단 목록 카드는 JS form submit 구조라 GET query로 동일 상세 화면을 열도록 만든다.
            detail_url = f"{view_url}?{urlencode({'idx': idx, 'idx3': idx})}"

            raw_text = self._clean_text(anchor.get_text(" ", strip=True))
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, detail_url)
            if item:
                items.append(item)
        return items

    def _parse_kosaf(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        for anchor in soup.select('a[href*="scholar.do?pg=scholarship"]'):
            href = anchor.get("href", "")
            if "scholarship_main" in href:
                continue
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not self._is_useful_title(title) or title in {"장학금 한눈에 보기", "국가장학금 알리미"}:
                continue
            raw_text = self._ancestor_text(anchor, ["li", "div"]) or title
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, href)
            if item:
                items.append(item)
        return items

    def _parse_generic(
        self,
        soup: BeautifulSoup,
        opportunity_type: str,
        source: str,
        list_url: str,
    ) -> list[dict[str, Any]]:
        items = []
        detail_hint = re.compile(r"(view|detail|read|activity|contest|scholar|idx|seq|bbs_id)", re.I)
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not detail_hint.search(href) or not self._is_useful_title(title):
                continue
            raw_text = self._ancestor_text(anchor, ["li", "tr", "article", "div"]) or title
            item = self._build_item(opportunity_type, title, raw_text, source, list_url, href)
            if item:
                items.append(item)
        return items

    def _build_item(
        self,
        opportunity_type: str,
        raw_title: str,
        raw_text: str,
        source: str,
        list_url: str,
        detail_href: str,
    ) -> dict[str, Any] | None:
        detail_url = detail_href if detail_href.startswith("http") else urljoin(list_url, detail_href)
        if not is_http_url(detail_url) or detail_url == list_url:
            return None

        title = clean_text(raw_title)
        context = clean_text(raw_text)
        start_date, end_date = extract_dates(context)
        list_introduction = clean_text(context.replace(title, "", 1))[:500] or None

        return {
            "id": stable_id(title, detail_url, source),
            "type": opportunity_type,
            "title": title,
            "raw_title": title,
            "organization": None,
            "start_date": start_date,
            "end_date": end_date,
            "date_text": context[:240],
            "program_introduction": list_introduction,
            "activity_content": None,
            "eligibility": None,
            "required_documents": None,
            "benefits": None,
            "contact": None,
            "targets": self._infer_targets(context),
            "source": source,
            "list_url": list_url,
            "detail_url": detail_url,
            "canonical_detail_url": canonical_url(detail_url),
            "raw_text": context[:500],
            "source_active": True,
            "view_count": 0,
            "save_count": 0,
        }

    def _enrich_from_detail(self, item: dict[str, Any]) -> dict[str, Any]:
        response = self._get(str(item["detail_url"]))
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script, style, noscript, nav, footer"):
            node.decompose()

        values = {
            "organization": self._extract_labeled_value(
                soup, ("주최", "주관", "주최기관", "운영기관", "기관명")
            ),
            "program_introduction": self._extract_labeled_value(
                soup, ("프로그램 소개", "사업 소개", "공모 소개", "공모내용", "사업내용", "개요")
            ),
            "activity_content": self._extract_labeled_value(
                soup, ("활동 내용", "활동내용", "주요 활동", "주요활동", "교육내용")
            ),
            "eligibility": self._extract_labeled_value(
                soup, ("지원 자격", "지원자격", "응모 자격", "응모자격", "참가 자격", "참가대상", "모집대상")
            ),
            "required_documents": self._extract_labeled_value(
                soup, ("제출 서류", "제출서류", "제출물", "접수서류", "구비서류")
            ),
            "benefits": self._extract_labeled_value(
                soup, ("혜택", "시상 내역", "시상내역", "지원 내용", "지원내용", "장학금액", "시상금")
            ),
            "contact": self._extract_labeled_value(
                soup, ("문의처", "문의", "연락처", "담당자")
            ),
        }

        if not values["program_introduction"]:
            description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
            if description_tag:
                values["program_introduction"] = self._meaningful_value(
                    description_tag.get("content", "")
                )

        page_text = clean_text(soup.get_text(" ", strip=True))[:20_000]
        start_date, end_date = extract_dates(page_text)
        enriched = dict(item)
        for field, value in values.items():
            if value:
                enriched[field] = value
        if start_date:
            enriched["start_date"] = start_date
        if end_date:
            enriched["end_date"] = end_date
        targets = self._infer_targets(" ".join([page_text, str(values.get("eligibility") or "")]))
        if targets:
            enriched["targets"] = targets
        enriched["detail_url"] = response.url
        enriched["canonical_detail_url"] = canonical_url(response.url)
        return enriched

    def _extract_labeled_value(self, soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
        normalized_labels = {self._normalize_label(label) for label in labels}

        for row in soup.select("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue
            label = self._normalize_label(cells[0].get_text(" ", strip=True))
            if label in normalized_labels:
                value = self._meaningful_value(" ".join(cell.get_text(" ", strip=True) for cell in cells[1:]))
                if value:
                    return value

        for term in soup.find_all("dt"):
            label = self._normalize_label(term.get_text(" ", strip=True))
            if label not in normalized_labels:
                continue
            definition = term.find_next_sibling("dd")
            if definition:
                value = self._meaningful_value(definition.get_text(" ", strip=True))
                if value:
                    return value

        for label_node in soup.find_all(["strong", "b", "span", "div", "p"]):
            label = self._normalize_label(label_node.get_text(" ", strip=True))
            if label not in normalized_labels:
                continue
            sibling = label_node.find_next_sibling()
            if sibling:
                value = self._meaningful_value(sibling.get_text(" ", strip=True))
                if value:
                    return value
        return None

    @staticmethod
    def _normalize_label(value: str) -> str:
        return re.sub(r"[\s:·/\-]+", "", clean_text(value))

    @staticmethod
    def _meaningful_value(value: str) -> str | None:
        cleaned = clean_text(value)[:2000]
        if not cleaned:
            return None
        blocked = {"데이터 없음", "정보 없음", "N/A", "해당 없음", "-"}
        return None if cleaned.upper() in {item.upper() for item in blocked} else cleaned

    @staticmethod
    def _infer_targets(text: str) -> list[str]:
        normalized = clean_text(text)
        targets: list[str] = []
        if re.search(r"고등학생|고교생|고등학교|청소년", normalized):
            targets.append("고등학생")
        if re.search(r"대학생|대학교|대학원생|재학생", normalized):
            targets.append("대학생")
        return targets

    def _ancestor_text(self, anchor: Tag, names: list[str]) -> str:
        for name in names:
            ancestor = anchor.find_parent(name)
            if ancestor:
                text = self._clean_text(ancestor.get_text(" ", strip=True))
                if len(text) > 10:
                    return text
        return ""

    def _source_name(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        if "wevity" in host:
            return "Wevity"
        if "linkareer" in host:
            return "Linkareer"
        if "contestkorea" in host:
            return "Contest Korea"
        if "sotong" in host:
            return "소통24"
        if "dreamspon" in host:
            return "드림스폰"
        if "seoulfuture" in host:
            return "서울미래인재재단"
        if "kosaf" in host:
            return "한국장학재단"
        return host or "web"

    def _clean_text(self, value: str) -> str:
        return clean_text(value)

    def _is_useful_title(self, title: str) -> bool:
        if len(title) < 4:
            return False
        if re.fullmatch(r"(D-?\d+|\d+|다음|마지막|자세히보기)", title, re.I):
            return False
        blocked = {"로그인", "회원가입", "개인정보처리방침", "공지사항", "전체 공모전", "장학금 신청하기"}
        return title not in blocked

    def _is_http_url(self, url: str) -> bool:
        return is_http_url(url)
