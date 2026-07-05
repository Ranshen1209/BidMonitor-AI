"""Adapters that expose source-backed crawls as Notice results."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

try:
    from .qianlima_vip import QIANLIMA_SOURCE_ID, QianlimaVipSearchClient, has_qianlima_cookie
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
        requests as url_list_requests,
    )
except ImportError:  # pragma: no cover
    from crawler.qianlima_vip import QIANLIMA_SOURCE_ID, QianlimaVipSearchClient, has_qianlima_cookie
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
        requests as url_list_requests,
    )


class TopologySourceAdapter:
    """Collect notices from a configured source topology."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.config["preserve_missing_publish_date"] = True

    def collect(self, source: Source, stop_event=None, notice_exists=None) -> CrawlResult:
        result = CrawlResult()
        if stop_event and stop_event.is_set():
            return result

        try:
            crawler = self._build_crawler(source)
            timestamp = datetime.now().isoformat(timespec="seconds")
            if self._should_use_qianlima_vip_search(source):
                keywords = self._qianlima_keywords()
                vip_result = QianlimaVipSearchClient(
                    crawler,
                    source,
                    self.config,
                    notice_exists=notice_exists,
                ).collect(keywords, stop_event=stop_event)
                if vip_result.notices:
                    return self._enrich_qianlima_vip_result(crawler, source, vip_result, timestamp, stop_event)
                if vip_result.error_count:
                    return vip_result
            cookie_used = crawler._get_cookie_for_url(source.url) is not None
            request_count_before = self._request_call_count(crawler)

            rule = crawler._classify_url(source.url)
            crawler._respect_rate_limit(source.url)
            try:
                html, status_code, status_text = crawler._request_url(source.url)
            except url_list_requests.RequestException as exc:
                message = f"{exc.__class__.__name__}: {exc}"
                result.errors.append(message)
                result.error_count += 1
                result.diagnostics.append(
                    {"url": source.url, "status": "failed", "reason": message, "status_code": 0}
                )
                html, status_code, status_text = "", 0, str(exc)
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
            followed_candidate_urls: set[str] = set()
            original_request_url = crawler._request_url
            original_request_http = crawler._request_http
            original_request_url_with_browser = crawler._request_url_with_browser
            original_should_follow_candidate = crawler._should_follow_candidate
            original_sort_candidate_links = crawler._sort_candidate_links
            had_topology_fetch_failure_callback = hasattr(crawler, "_topology_fetch_failure_callback")
            original_topology_fetch_failure_callback = getattr(
                crawler, "_topology_fetch_failure_callback", None
            )
            topology_seed_urls = {
                link.get("url", "").split("#", 1)[0] for link in crawler._topology_seed_links(source.url)
            }

            def record_candidate_failure(
                url: str,
                response_rule: dict[str, str],
                reason: str,
                status_code: int = 0,
            ) -> None:
                normalized_url = normalize_notice_url(url)
                failure_key = normalized_url or url.split("#", 1)[0]
                page_type = response_rule.get("page_type", "")
                if page_type != "detail" and failure_key not in followed_candidate_urls:
                    return
                if failure_key in detail_failure_urls:
                    return
                detail_failure_urls.add(failure_key)
                failure_kind = "detail"
                if page_type != "detail":
                    failure_kind = (
                        "traversal" if url.split("#", 1)[0] in topology_seed_urls else "candidate"
                    )
                detail_failures.append(
                    {
                        "url": url,
                        "status": "failed",
                        "reason": f"{failure_kind} fetch failed: {reason}",
                        "status_code": status_code,
                        "page_type": page_type,
                    }
                )

            def record_topology_fetch_failure(
                page_url: str,
                reason: str,
                status_code: int = 0,
                **_context: Any,
            ) -> None:
                record_candidate_failure(page_url, crawler._classify_url(page_url), reason, status_code)

            def request_url_and_collect_json(url: str):
                normalized_url = normalize_notice_url(url)
                if normalized_url and normalized_url in admitted_structured_urls:
                    return "", 204, "Skipped admitted structured URL"
                request_url_and_collect_json.call_count += 1
                response_rule = crawler._classify_url(url)
                current_request_http = crawler._request_http
                crawler._request_http = original_request_http
                try:
                    response_html, response_status, response_text = original_request_url(url)
                finally:
                    crawler._request_http = current_request_http
                return collect_json_response(url, response_rule, response_html, response_status, response_text)

            def request_http_and_collect_json(
                method: str,
                url: str,
                params: dict[str, Any] | None = None,
                data: dict[str, Any] | None = None,
            ):
                normalized_url = normalize_notice_url(url)
                if normalized_url and normalized_url in admitted_structured_urls:
                    return "", 204, "Skipped admitted structured URL"
                request_http_and_collect_json.call_count += 1
                response_rule = crawler._classify_url(url)
                response_html, response_status, response_text = original_request_http(
                    method,
                    url,
                    params=params,
                    data=data,
                )
                return collect_json_response(url, response_rule, response_html, response_status, response_text)

            def collect_json_response(
                url: str,
                response_rule: dict[str, str],
                response_html: str,
                response_status: int,
                response_text: str,
            ):
                response_blocked = response_status < 400 and crawler._contains_blocked_sign(response_html, url)
                if response_status >= 400 or response_blocked:
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

            def request_url_with_browser_and_count(url: str):
                request_url_with_browser_and_count.call_count += 1
                return original_request_url_with_browser(url)

            def should_follow_unadmitted_candidate(page_url: str, candidate_url: str, depth: int) -> bool:
                absolute_candidate = urljoin(page_url, candidate_url)
                normalized_candidate = normalize_notice_url(absolute_candidate)
                if normalized_candidate and normalized_candidate in admitted_structured_urls:
                    return False
                should_follow = original_should_follow_candidate(page_url, candidate_url, depth)
                if should_follow:
                    followed_candidate_urls.add(normalized_candidate or absolute_candidate.split("#", 1)[0])
                return should_follow

            def sort_with_topology_seed_priority(page_url: str, links: list[dict[str, str]]) -> list[dict[str, str]]:
                sorted_links = original_sort_candidate_links(page_url, links)
                seed_links = []
                other_links = []
                for link in sorted_links:
                    link_url = link.get("url", "").split("#", 1)[0]
                    if link_url in topology_seed_urls:
                        seed_links.append(link)
                    else:
                        other_links.append(link)
                return seed_links + other_links

            request_url_and_collect_json.call_count = request_count_before + initial_fetch_count
            request_http_and_collect_json.call_count = 0
            request_url_with_browser_and_count.call_count = 0
            crawler._request_url = request_url_and_collect_json
            crawler._request_http = request_http_and_collect_json
            crawler._request_url_with_browser = request_url_with_browser_and_count
            crawler._should_follow_candidate = should_follow_unadmitted_candidate
            crawler._sort_candidate_links = sort_with_topology_seed_priority
            crawler._topology_fetch_failure_callback = record_topology_fetch_failure
            try:
                legacy_bids = crawler._crawl_topology_from_url(
                    source.url,
                    "" if source_payload_is_json else topology_seed_html,
                    timestamp,
                    rule,
                    cookie_used=cookie_used,
                )
                request_delta = (
                    self._request_call_count(crawler)
                    - request_count_before
                    + request_http_and_collect_json.call_count
                )
                browser_request_delta = request_url_with_browser_and_count.call_count
            finally:
                crawler._request_url = original_request_url
                crawler._request_http = original_request_http
                crawler._request_url_with_browser = original_request_url_with_browser
                crawler._should_follow_candidate = original_should_follow_candidate
                crawler._sort_candidate_links = original_sort_candidate_links
                if had_topology_fetch_failure_callback:
                    crawler._topology_fetch_failure_callback = original_topology_fetch_failure_callback
                elif hasattr(crawler, "_topology_fetch_failure_callback"):
                    delattr(crawler, "_topology_fetch_failure_callback")
            total_fetch_delta = request_delta + browser_request_delta
            if total_fetch_delta > 0:
                result.fetched_count = total_fetch_delta
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
                if not notice.title or not _is_admissible_notice_detail_url(notice.detail_url):
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
            if not _is_fetchable_notice_url(explicit_url, page_url):
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
        def post_json(url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int, str]:
            headers = crawler._get_headers()
            headers["Content-Type"] = "application/json"
            cookie = crawler._get_cookie_for_url(url)
            if cookie:
                headers["Cookie"] = cookie
            crawler._emit_info(f"[URL请求] {crawler.name}: HTTP POST JSON {crawler._short_url(url)}")
            response = crawler.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=crawler.timeout,
                verify=False,
                allow_redirects=True,
            )
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
            try:
                return json.loads(response.text or "{}"), response.status_code, response.reason
            except (TypeError, ValueError):
                return {}, response.status_code, response.reason

        def get_json(url: str) -> tuple[dict[str, Any], int, str]:
            html, status_code, status_text = crawler._request_url(url)
            try:
                return json.loads(html or "{}"), status_code, status_text
            except (TypeError, ValueError):
                return {}, status_code, status_text

        crawler.post_json = post_json
        crawler.get_json = get_json
        if source.topology:
            crawler.site_topologies = [source.topology]
        return crawler

    def _should_use_qianlima_vip_search(self, source: Source) -> bool:
        if source.id != QIANLIMA_SOURCE_ID:
            return False
        if self.config.get("qianlima_vip_search_enabled", True) is False:
            return False
        return has_qianlima_cookie(source.auth_cookies or self.config.get("auth_cookies", []))

    def _qianlima_keywords(self) -> list[str]:
        raw_keywords = self.config.get("search_keywords") or self.config.get("keywords") or []
        if isinstance(raw_keywords, str):
            raw_keywords = [item.strip() for item in raw_keywords.split(",")]
        keywords = []
        seen = set()
        for item in raw_keywords:
            keyword = str(item).strip()
            if keyword and keyword not in seen:
                seen.add(keyword)
                keywords.append(keyword)
        return keywords

    def _enrich_qianlima_vip_result(
        self,
        crawler: UrlListCrawler,
        source: Source,
        vip_result: CrawlResult,
        timestamp: str,
        stop_event=None,
    ) -> CrawlResult:
        result = CrawlResult(
            fetched_count=vip_result.fetched_count,
            candidate_count=vip_result.candidate_count,
            skipped_count=vip_result.skipped_count,
            error_count=vip_result.error_count,
            errors=list(vip_result.errors),
            diagnostics=list(vip_result.diagnostics),
        )
        deduplicator = NoticeDeduplicator()
        for search_notice in vip_result.notices:
            if stop_event and stop_event.is_set():
                break
            detail_notice = self._fetch_qianlima_detail_notice(crawler, source, search_notice, timestamp)
            if detail_notice is not None:
                result.fetched_count += 1
                notice = self._merge_qianlima_detail_notice(search_notice, detail_notice)
            else:
                notice = search_notice
            if not deduplicator.add(notice):
                result.skipped_count += 1
                continue
            result.notices.append(notice)
        result.parsed_count = len(result.notices)
        result.diagnostics.append(
            {
                "url": source.url,
                "status": "success" if result.notices else "skipped",
                "candidate_count": result.candidate_count,
                "parsed_count": result.parsed_count,
                "mode": "qianlima_vip_search",
            }
        )
        return result

    def _fetch_qianlima_detail_notice(
        self,
        crawler: UrlListCrawler,
        source: Source,
        search_notice: Notice,
        timestamp: str,
    ) -> Notice | None:
        detail_url = search_notice.detail_url
        if not _is_admissible_notice_detail_url(detail_url):
            return None
        crawler._respect_rate_limit(detail_url)
        try:
            html, status_code, _status_text = crawler._request_url(detail_url)
        except url_list_requests.RequestException:
            return None
        if status_code >= 400 or crawler._contains_blocked_sign(html, detail_url):
            return None
        for bid in crawler._parse_page(html, detail_url, timestamp):
            bid_url = normalize_notice_url(getattr(bid, "url", ""))
            if bid_url and bid_url == normalize_notice_url(detail_url):
                detail_notice = self._notice_from_bid(source, bid)
                detail_notice.source_item_id = search_notice.source_item_id
                return detail_notice
        return None

    def _merge_qianlima_detail_notice(self, search_notice: Notice, detail_notice: Notice) -> Notice:
        merged_raw = dict(search_notice.raw or {})
        merged_raw["qianlima_search"] = dict((search_notice.raw or {}).get("qianlima", {}))
        legacy_raw = dict((detail_notice.raw or {}).get("legacy", {}))
        if legacy_raw:
            merged_raw["legacy"] = legacy_raw
        return Notice(
            source_id=search_notice.source_id,
            source_name=search_notice.source_name,
            source_item_id=search_notice.source_item_id or detail_notice.source_item_id,
            title=detail_notice.title or search_notice.title,
            detail_url=detail_notice.detail_url or search_notice.detail_url,
            publish_date=detail_notice.publish_date or search_notice.publish_date,
            notice_type=detail_notice.notice_type or search_notice.notice_type,
            purchaser=detail_notice.purchaser or search_notice.purchaser,
            region=detail_notice.region or search_notice.region,
            content=detail_notice.content or search_notice.content,
            content_hash=detail_notice.content_hash or search_notice.content_hash,
            raw=merged_raw,
            quality_flags=list(dict.fromkeys((search_notice.quality_flags or []) + (detail_notice.quality_flags or []))),
        )

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


def _is_fetchable_notice_url(value: str, page_url: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    if _has_notice_url_template_marker(stripped):
        return False
    if stripped.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
        return False
    normalized_url = normalize_notice_url(urljoin(page_url, stripped))
    return bool(normalized_url) and not _has_notice_url_template_marker(normalized_url)


def _is_admissible_notice_detail_url(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped or _has_notice_url_template_marker(stripped):
        return False
    normalized_url = normalize_notice_url(stripped)
    return bool(normalized_url) and not _has_notice_url_template_marker(normalized_url)


def _has_notice_url_template_marker(value: str) -> bool:
    return any(marker in str(value or "") for marker in ("{{", "}}", "${", "{", "}", "<", ">"))


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
