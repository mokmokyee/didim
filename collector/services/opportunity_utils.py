from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}

ALL_AGES_TARGET = "전 연령"
HIGH_SCHOOL_TARGET = "고등학생"
COLLEGE_TARGET = "대학생"

TARGET_TEXT_FIELDS = (
    "title",
    "raw_title",
    "category",
    "program_introduction",
    "summary",
    "description",
    "activity_content",
    "eligibility",
    "requirements",
    "age_requirement",
    "raw_text",
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def infer_targets(text: Any) -> list[str]:
    normalized = clean_text(text)
    if re.search(r"누구나|전\s*연령|연령\s*(?:무관|제한\s*없음)|나이\s*무관", normalized):
        return [ALL_AGES_TARGET]

    targets: list[str] = []
    if re.search(r"고등학생|고교생|고등학교\s*(?:학생|재학생)", normalized):
        targets.append(HIGH_SCHOOL_TARGET)
    if re.search(r"대학생|학부생|전문대생|대학(?:교)?\s*재학생", normalized):
        targets.append(COLLEGE_TARGET)
    return targets or [ALL_AGES_TARGET]


def normalize_targets(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    aliases = {
        "전연령": ALL_AGES_TARGET,
        "누구나": ALL_AGES_TARGET,
        "연령무관": ALL_AGES_TARGET,
        "나이무관": ALL_AGES_TARGET,
        "연령제한없음": ALL_AGES_TARGET,
        "고등학생": HIGH_SCHOOL_TARGET,
        "고교생": HIGH_SCHOOL_TARGET,
        "대학생": COLLEGE_TARGET,
        "학부생": COLLEGE_TARGET,
        "전문대생": COLLEGE_TARGET,
    }
    result: list[str] = []
    for raw in values or []:
        lookup = re.sub(r"[\s·._\-/]+", "", clean_text(raw)).casefold()
        target = aliases.get(lookup)
        if target and target not in result:
            result.append(target)
    return [ALL_AGES_TARGET] if ALL_AGES_TARGET in result else result


def resolve_opportunity_targets(item: dict[str, Any]) -> list[str]:
    explicit = normalize_targets(item.get("targets") or item.get("target") or [])
    if explicit:
        return explicit
    text = " ".join(clean_text(item.get(field)) for field in TARGET_TEXT_FIELDS)
    return infer_targets(text)


def targets_match(item: dict[str, Any], selected_targets: Any) -> bool:
    selected = [target for target in normalize_targets(selected_targets) if target != ALL_AGES_TARGET]
    if not selected:
        return True
    available = resolve_opportunity_targets(item)
    return ALL_AGES_TARGET in available or bool(set(selected).intersection(available))


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_safe_crawl_url(value: str) -> bool:
    if not is_http_url(value):
        return False
    hostname = (urlparse(value).hostname or "").strip().lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def canonical_url(value: str) -> str:
    parsed = urlparse(clean_text(value))
    if parsed.scheme not in {"http", "https"}:
        return ""

    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/") or parsed.path
    query_pairs = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]

    # 사이트별 상세 식별자만 남겨 같은 상세 페이지가 다른 목록 파라미터로 중복되는 것을 줄인다.
    key_params = {
        "wevity.com": {"ix"},
        "contestkorea.com": {"str_no", "Txt_bcode", "int_gbn"},
        "sotong.go.kr": {"bbs_id"},
        "dreamspon.com": {"idx"},
        "kosaf.go.kr": {"pg"},
        "seoulfuture.or.kr": {"idx", "idx3"},
    }
    for domain, keys in key_params.items():
        if domain in host:
            query_pairs = [(key, val) for key, val in query_pairs if key in keys]
            break

    if "linkareer.com" in host:
        path_match = re.search(r"/activity/\d+", path)
        if path_match:
            path = path_match.group(0)
            query_pairs = []

    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


def stable_id(title: str, detail_url: str, source: str = "") -> str:
    canonical = canonical_url(detail_url)
    identity = f"{clean_text(source).lower()}|{canonical or clean_text(detail_url)}"
    if not canonical:
        identity += f"|{clean_text(title).lower()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return digest[:16]


def normalize_title(value: str) -> str:
    title = clean_text(value).lower()
    title = re.sub(r"^\s*(추천\s*)?(\[추천공모전\]|\[추천\]|추천)\s*", "", title)
    title = re.sub(r"^d-?\d+\s*", "", title)
    title = re.sub(r"\(~?\s*\d{1,2}/\d{1,2}\s*(까지)?\)", "", title)
    title = re.sub(r"\[[^\]]{1,30}\]", "", title)
    title = re.sub(r"【[^】]{1,30}】", "", title)
    return re.sub(r"[\W_]+", "", title, flags=re.UNICODE)


def extract_dates(text: str) -> tuple[str, str]:
    source = clean_text(text)
    if not source:
        return "", ""

    range_match = re.search(
        r"(?P<sy>\d{2,4})[.\-/](?P<sm>\d{1,2})[.\-/](?P<sd>\d{1,2})"
        r"\s*(?:~|부터|[-–—])\s*"
        r"(?:(?P<ey>\d{2,4})[.\-/])?(?P<em>\d{1,2})[.\-/](?P<ed>\d{1,2})",
        source,
    )
    if range_match:
        start_year = _normalize_year(range_match.group("sy"))
        end_year = _normalize_year(range_match.group("ey") or range_match.group("sy"))
        return (
            _format_date(start_year, range_match.group("sm"), range_match.group("sd")),
            _format_date(end_year, range_match.group("em"), range_match.group("ed")),
        )

    tilde_short = re.search(r"~\s*(?P<m>\d{1,2})[./](?P<d>\d{1,2})", source)
    if tilde_short:
        return "", _format_date(date.today().year, tilde_short.group("m"), tilde_short.group("d"))

    full_dates = re.findall(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", source)
    short_dates = re.findall(r"(?<!\d)(\d{2})[.](\d{1,2})[.](\d{1,2})(?!\d)", source)
    dates = [_format_date(year, month, day) for year, month, day in full_dates]
    dates.extend(_format_date(_normalize_year(year), month, day) for year, month, day in short_dates)
    dates = [value for value in dates if value]
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return "", dates[0]

    dday = re.search(r"D-?\s*(\d+)", source, flags=re.I)
    if dday:
        return "", (date.today() + timedelta(days=int(dday.group(1)))).isoformat()

    return "", ""


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for item in items:
        url_key = canonical_url(str(item.get("detail_url", "")))
        if not url_key:
            continue
        item["canonical_detail_url"] = url_key
        current = by_url.get(url_key)
        by_url[url_key] = _choose_better(current, item) if current else item

    by_title_date: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in by_url.values():
        title_key = normalize_title(str(item.get("title") or item.get("raw_title", "")))
        end_date = clean_text(item.get("end_date", ""))
        if not title_key:
            continue
        key = (str(item.get("type", "")), title_key, end_date if end_date else "__no_date__")
        if not end_date and len(title_key) < 12:
            key = (str(item.get("type", "")), title_key, item.get("canonical_detail_url", ""))
        current = by_title_date.get(key)
        by_title_date[key] = _choose_better(current, item) if current else item

    return list(by_title_date.values())


def _choose_better(left: dict[str, Any] | None, right: dict[str, Any]) -> dict[str, Any]:
    if left is None:
        return right

    def score(item: dict[str, Any]) -> tuple[int, int, int, int]:
        detail_length = sum(
            len(clean_text(item.get(field)))
            for field in (
                "program_introduction",
                "activity_content",
                "eligibility",
                "required_documents",
                "benefits",
            )
        )
        return (
            1 if is_http_url(str(item.get("detail_url", ""))) else 0,
            1 if item.get("end_date") else 0,
            detail_length,
            len(item.get("keywords", [])),
        )

    return right if score(right) > score(left) else left


def _normalize_year(value: str | int) -> int:
    year = int(value)
    return 2000 + year if year < 100 else year


def _format_date(year: str | int, month: str | int, day: str | int) -> str:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""
