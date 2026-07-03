"""Adapters that expose source-backed crawls as Notice results."""
from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from .source_models import CrawlResult, Notice, NoticeDeduplicator, Source
    from .url_list import UrlListCrawler
except ImportError:  # pragma: no cover
    from crawler.source_models import CrawlResult, Notice, NoticeDeduplicator, Source
    from crawler.url_list import UrlListCrawler


class TopologySourceAdapter:
    """Collect notices from a configured source topology."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.config["preserve_missing_publish_date"] = True

    def collect(self, source: Source, stop_event=None) -> CrawlResult:
        result = CrawlResult()
        if stop_event and stop_event.is_set():
            return result

        try:
            crawler = self._build_crawler(source)
            timestamp = datetime.now().isoformat(timespec="seconds")
            cookie_used = crawler._get_cookie_for_url(source.url) is not None
            request_count_before = self._request_call_count(crawler)

            rule = crawler._classify_url(source.url)
            crawler._respect_rate_limit(source.url)
            html, status_code, status_text = crawler._request_url(source.url)
            result.fetched_count = max(1, self._request_call_count(crawler) - request_count_before)

            if status_code >= 400:
                message = f"HTTP {status_code}: {status_text or 'source fetch failed'}"
                result.errors.append(message)
                result.error_count = 1
                result.diagnostics.append(
                    {"url": source.url, "status": "failed", "reason": message, "status_code": status_code}
                )
                return result

            if crawler._contains_blocked_sign(html, source.url):
                message = crawler._blocked_reason(html, source.url)
                result.errors.append(message)
                result.error_count = 1
                result.diagnostics.append(
                    {"url": source.url, "status": "failed", "reason": message, "status_code": status_code}
                )
                return result

            legacy_bids = crawler._crawl_topology_from_url(
                source.url,
                html,
                timestamp,
                rule,
                cookie_used=cookie_used,
            )
            request_delta = self._request_call_count(crawler) - request_count_before
            if request_delta > 0:
                result.fetched_count = request_delta
            result.candidate_count = max(len(legacy_bids), len(crawler._topology_seed_links(source.url)))

            deduplicator = NoticeDeduplicator()
            for bid in legacy_bids:
                notice = self._notice_from_bid(source, bid)
                if not notice.title or not notice.detail_url:
                    result.skipped_count += 1
                    continue
                if not deduplicator.add(notice):
                    result.skipped_count += 1
                    continue
                result.notices.append(notice)

            result.parsed_count = len(result.notices)
            result.diagnostics.append(
                {
                    "url": source.url,
                    "status": "success",
                    "candidate_count": result.candidate_count,
                    "parsed_count": result.parsed_count,
                }
            )
            return result
        except Exception as exc:
            result.errors.append(f"{exc.__class__.__name__}: {exc}")
            result.error_count = 1
            result.diagnostics.append({"url": source.url, "status": "failed", "reason": str(exc)})
            return result

    def _build_crawler(self, source: Source) -> UrlListCrawler:
        rate_limit = source.rate_limit or {}
        config = dict(self.config)
        domain_delay = rate_limit.get("domain_delay", rate_limit.get("delay_seconds", config.get("domain_delay", 0)))
        config["domain_delay"] = domain_delay
        source_config = {
            "name": source.name,
            "file_path": "",
            "auth_cookies": source.auth_cookies or config.get("auth_cookies", []),
            "domain_delay": domain_delay,
        }
        crawler = UrlListCrawler(config, source_config)
        if source.topology:
            crawler.site_topologies = [source.topology]
        return crawler

    def _notice_from_bid(self, source: Source, bid) -> Notice:
        content = getattr(bid, "content", "") or ""
        return Notice(
            source_id=source.id,
            source_name=source.name,
            title=(getattr(bid, "title", "") or "").strip(),
            detail_url=(getattr(bid, "url", "") or "").strip(),
            publish_date=getattr(bid, "publish_date", "") or "",
            purchaser=getattr(bid, "purchaser", "") or "",
            region=getattr(bid, "region", "") or "",
            content=content,
            raw={
                "legacy": {
                    "title": getattr(bid, "title", ""),
                    "url": getattr(bid, "url", ""),
                    "publish_date": getattr(bid, "publish_date", ""),
                    "source": getattr(bid, "source", ""),
                    "content": content,
                    "purchaser": getattr(bid, "purchaser", ""),
                    "region": getattr(bid, "region", ""),
                }
            },
        )

    def _request_call_count(self, crawler: UrlListCrawler) -> int:
        call_count = getattr(crawler._request_url, "call_count", None)
        return call_count if isinstance(call_count, int) else 0
