"""Adapters that expose source-backed crawls as Notice results."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

try:
    from .source_models import (
        CrawlResult,
        Notice,
        NoticeDeduplicator,
        Source,
        normalize_notice_url,
    )
    from .url_list import (
        CONTENT_FIELDS,
        DATE_FIELDS,
        PURCHASER_FIELDS,
        SOURCE_FIELDS,
        TITLE_FIELDS,
        TYPE_FIELDS,
        URL_FIELDS,
        UrlListCrawler,
    )
except ImportError:  # pragma: no cover
    from crawler.source_models import (
        CrawlResult,
        Notice,
        NoticeDeduplicator,
        Source,
        normalize_notice_url,
    )
    from crawler.url_list import (
        CONTENT_FIELDS,
        DATE_FIELDS,
        PURCHASER_FIELDS,
        SOURCE_FIELDS,
        TITLE_FIELDS,
        TYPE_FIELDS,
        URL_FIELDS,
        UrlListCrawler,
    )


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
            initial_fetch_count = max(1, self._request_call_count(crawler) - request_count_before)
            result.fetched_count = initial_fetch_count

            source_payload_is_json = False
            topology_seed_html = html
            structured_bids: list[Any] = []
            if status_code >= 400:
                message = f"HTTP {status_code}: {status_text or 'source fetch failed'}"
                result.errors.append(message)
                result.error_count += 1
                result.diagnostics.append(
                    {"url": source.url, "status": "failed", "reason": message, "status_code": status_code}
                )
                topology_seed_html = ""
            elif crawler._contains_blocked_sign(html, source.url):
                message = crawler._blocked_reason(html, source.url)
                result.errors.append(message)
                result.error_count += 1
                result.diagnostics.append(
                    {"url": source.url, "status": "failed", "reason": message, "status_code": status_code}
                )
                topology_seed_html = ""
            else:
                source_payload_is_json = self._is_json_payload(html)
                structured_bids = self._structured_bids_from_payload(crawler, html, source.url, timestamp, rule)
                if source_payload_is_json:
                    topology_seed_html = ""

            admitted_structured_urls = self._normalized_bid_urls(structured_bids)
            topology_structured_bids: list[Any] = []
            detail_failures: list[dict[str, Any]] = []
            detail_failure_urls: set[str] = set()
            original_request_url = crawler._request_url
            original_should_follow_candidate = crawler._should_follow_candidate

            def request_url_and_collect_json(url: str):
                normalized_url = normalize_notice_url(url)
                if normalized_url and normalized_url in admitted_structured_urls:
                    return "", 204, "Skipped admitted structured URL"
                request_url_and_collect_json.call_count += 1
                response_html, response_status, response_text = original_request_url(url)
                response_rule = crawler._classify_url(url)
                response_blocked = response_status < 400 and crawler._contains_blocked_sign(response_html, url)
                if response_status >= 400 or response_blocked:
                    if response_rule.get("page_type") == "detail":
                        failure_key = normalized_url or url.split("#", 1)[0]
                        if failure_key not in detail_failure_urls:
                            detail_failure_urls.add(failure_key)
                            if response_status >= 400:
                                reason = f"HTTP {response_status}: {response_text or 'detail fetch failed'}"
                            else:
                                reason = crawler._blocked_reason(response_html, url)
                            detail_failures.append(
                                {
                                    "url": url,
                                    "status": "failed",
                                    "reason": f"detail fetch failed: {reason}",
                                    "status_code": response_status,
                                    "page_type": "detail",
                                }
                            )
                    return response_html, response_status, response_text
                if response_status < 400:
                    response_structured_bids = self._structured_bids_from_payload(
                        crawler, response_html, url, timestamp, response_rule
                    )
                    topology_structured_bids.extend(response_structured_bids)
                    admitted_structured_urls.update(self._normalized_bid_urls(response_structured_bids))
                    if self._is_json_payload(response_html):
                        return "", response_status, response_text
                return response_html, response_status, response_text

            def should_follow_unadmitted_candidate(page_url: str, candidate_url: str, depth: int) -> bool:
                normalized_candidate = normalize_notice_url(urljoin(page_url, candidate_url))
                if normalized_candidate and normalized_candidate in admitted_structured_urls:
                    return False
                return original_should_follow_candidate(page_url, candidate_url, depth)

            request_url_and_collect_json.call_count = request_count_before + initial_fetch_count
            crawler._request_url = request_url_and_collect_json
            crawler._should_follow_candidate = should_follow_unadmitted_candidate
            legacy_bids = crawler._crawl_topology_from_url(
                source.url,
                "" if source_payload_is_json else topology_seed_html,
                timestamp,
                rule,
                cookie_used=cookie_used,
            )
            request_delta = self._request_call_count(crawler) - request_count_before
            if request_delta > 0:
                result.fetched_count = request_delta
            result.diagnostics.extend(detail_failures)
            for failure in detail_failures:
                result.errors.append(failure["reason"])
            result.skipped_count += len(detail_failures)
            result.error_count += len(detail_failures)

            total_candidates = (
                len(structured_bids)
                + len(topology_structured_bids)
                + len(legacy_bids)
                + len(detail_failures)
            )
            result.candidate_count = max(
                total_candidates,
                len(crawler._topology_seed_links(source.url)),
            )

            deduplicator = NoticeDeduplicator()
            for bid in structured_bids + topology_structured_bids + legacy_bids:
                notice = self._notice_from_bid(source, bid)
                if not notice.title or not notice.detail_url:
                    result.skipped_count += 1
                    continue
                if not deduplicator.add(notice):
                    result.skipped_count += 1
                    continue
                result.notices.append(notice)

            result.parsed_count = len(result.notices)
            summary_status = "success"
            if result.errors and result.notices:
                summary_status = "partial"
            elif result.errors:
                summary_status = "failed"
            elif not result.notices:
                summary_status = "skipped"
            result.diagnostics.append(
                {
                    "url": source.url,
                    "status": summary_status,
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

    def _structured_bids_from_payload(
        self,
        crawler: UrlListCrawler,
        payload: str,
        page_url: str,
        timestamp: str,
        rule: dict[str, str],
    ) -> list[Any]:
        stripped = (payload or "").lstrip()
        if not stripped or stripped[0] not in "[{":
            return []
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            return []

        bids: list[Any] = []
        for record in crawler._find_json_records(parsed):
            if not isinstance(record, dict):
                continue
            title = _first_meaningful_scalar_json_value(record, TITLE_FIELDS).strip()
            if not title:
                continue
            explicit_url = _first_meaningful_scalar_json_value(record, URL_FIELDS).strip()
            if not explicit_url:
                continue
            if not self._has_raw_structured_evidence(record):
                continue
            sanitized_record = _sanitized_record_for_parse(record, title, explicit_url)
            parsed_bids = crawler._parse_json_records(
                json.dumps([sanitized_record], ensure_ascii=False),
                page_url,
                timestamp,
                rule,
            )
            bids.extend(parsed_bids)
        return bids

    def _is_json_payload(self, payload: str) -> bool:
        stripped = (payload or "").lstrip()
        if not stripped or stripped[0] not in "[{":
            return False
        try:
            json.loads(stripped)
        except (TypeError, ValueError):
            return False
        return True

    def _has_raw_structured_evidence(self, record: dict[str, Any]) -> bool:
        evidence_fields = DATE_FIELDS + PURCHASER_FIELDS + CONTENT_FIELDS + TYPE_FIELDS + SOURCE_FIELDS
        lowered = {str(key).lower(): value for key, value in record.items()}
        for field in evidence_fields:
            if field in record and _raw_value_has_evidence(record[field]):
                return True
            if _raw_value_has_evidence(lowered.get(field.lower())):
                return True
        return False

    def _normalized_bid_urls(self, bids: list[Any]) -> set[str]:
        urls: set[str] = set()
        for bid in bids:
            normalized_url = normalize_notice_url(getattr(bid, "url", ""))
            if normalized_url:
                urls.add(normalized_url)
        return urls

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


def _raw_value_has_evidence(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_raw_value_has_evidence(item) for item in value)
    if isinstance(value, dict):
        return any(_raw_value_has_evidence(item) for item in value.values())
    return True


def _first_meaningful_scalar_json_value(record: dict[str, Any], fields: list[str]) -> str:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for field in fields:
        if field in record:
            value = _meaningful_json_scalar(record[field])
            if value:
                return value
        value = _meaningful_json_scalar(lowered.get(field.lower()))
        if value:
            return value
    return ""


def _sanitized_record_for_parse(record: dict[str, Any], title: str, detail_url: str) -> dict[str, Any]:
    title_fields = {field.lower() for field in TITLE_FIELDS}
    url_fields = {field.lower() for field in URL_FIELDS}
    sanitized = {
        key: value
        for key, value in record.items()
        if str(key).lower() not in title_fields and str(key).lower() not in url_fields
    }
    sanitized["title"] = title
    sanitized["url"] = detail_url
    return sanitized


def _meaningful_json_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ""
    if isinstance(value, dict):
        return ""
    return str(value).strip()
