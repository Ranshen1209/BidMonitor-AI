"""Source-backed crawl models used by the phase-1 crawl pipeline."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    from database.storage import BidInfo
except ImportError:  # pragma: no cover
    from ..database.storage import BidInfo


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"spm", "from", "source", "src", "ref", "referer", "callback"}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    enabled: bool = True
    topology: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    rate_limit: dict[str, Any] = field(default_factory=dict)
    auth_cookies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Notice:
    source_id: str
    source_name: str
    title: str
    detail_url: str
    publish_date: str = ""
    source_item_id: str = ""
    notice_type: str = ""
    purchaser: str = ""
    region: str = ""
    content: str = ""
    content_hash: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)

    def to_bid_info(self) -> BidInfo:
        content = self.content or ""
        if self.raw:
            raw_text = json.dumps(self.raw, ensure_ascii=False, sort_keys=True)
            content = f"{content}\nraw: {raw_text}".strip()
        return BidInfo(
            title=self.title,
            url=self.detail_url,
            publish_date=self.publish_date or "",
            source=self.source_name,
            content=content,
            purchaser=self.purchaser,
        )


@dataclass
class CrawlResult:
    notices: list[Notice] = field(default_factory=list)
    fetched_count: int = 0
    candidate_count: int = 0
    parsed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


class NoticeDeduplicator:
    def __init__(self):
        self._seen: set[str] = set()

    def add(self, notice: Notice) -> bool:
        key = self.key_for(notice)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def key_for(self, notice: Notice) -> str:
        if notice.source_item_id:
            return f"item:{notice.source_id}:{notice.source_item_id}"
        normalized_url = normalize_notice_url(notice.detail_url)
        if normalized_url:
            return f"url:{notice.source_id}:{normalized_url}"
        weak = "|".join(
            [
                normalize_text(notice.title),
                normalize_text(notice.purchaser),
                notice.publish_date or "",
                normalize_text(notice.region),
            ]
        )
        return "weak:" + hashlib.sha256(weak.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).lower()


def normalize_notice_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in TRACKING_QUERY_KEYS or lower_key.startswith(TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    normalized = parsed._replace(fragment="", query=query)
    return urlunparse(normalized)
