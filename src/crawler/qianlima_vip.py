"""Qianlima VIP authenticated search helpers."""
from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, Mapping, Optional

try:
    from .source_models import CrawlResult, Notice, Source, normalize_notice_url
except ImportError:  # pragma: no cover
    from crawler.source_models import CrawlResult, Notice, Source, normalize_notice_url


QIANLIMA_SOURCE_ID = "qianlima"
QIANLIMA_SEARCH_ENDPOINT = "https://search.vip.qianlima.com/rest/service/website/search/solr"
QIANLIMA_MEMBER_INFO_ENDPOINT = "https://vip.qianlima.com/rest/u/company/getCompanyInfo"

DEFAULT_SEARCH_TEMPLATE: dict[str, Any] = {
    "allType": -1,
    "beginAmount": "",
    "currentPage": 1,
    "endAmount": "",
    "filtermode": "8",
    "fourLevelCategoryIdListStr": "",
    "hasChooseSortType": 1,
    "hasTenderTransferProject": 1,
    "keywords": "",
    "levelId": "",
    "newAreas": "",
    "noticeSegmentTypeStr": "",
    "numPerPage": 20,
    "purchasingUnitIdList": "",
    "searchDataType": 0,
    "searchMode": 0,
    "showContent": 1,
    "sortType": 6,
    "summaryType": 0,
    "tab": 0,
    "threeClassifyTagStr": "",
    "threeLevelCategoryIdListStr": "",
    "timeType": 8,
    "types": "-1",
}


def build_search_payload(keyword: str, page: int, config: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(DEFAULT_SEARCH_TEMPLATE)
    payload["keywords"] = str(keyword or "").strip()
    payload["currentPage"] = max(1, int(page))
    payload["numPerPage"] = int(config.get("qianlima_num_per_page", payload["numPerPage"]))
    payload["timeType"] = config.get("qianlima_time_type", payload["timeType"])
    payload["sortType"] = config.get("qianlima_sort_type", payload["sortType"])
    return payload


def has_qianlima_cookie(auth_cookies: Iterable[Mapping[str, Any]]) -> bool:
    for item in auth_cookies or []:
        if not item.get("enabled", True):
            continue
        domain = str(item.get("domain", "")).lower().lstrip(".")
        cookie = str(item.get("cookie", ""))
        if cookie and (domain == "qianlima.com" or domain.endswith(".qianlima.com")):
            return True
    return False


def _first_text(record: Mapping[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return ""


def _metadata_lines(items: Mapping[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in items.items() if value)


def map_search_record_to_notice(source: Source, record: Mapping[str, Any]) -> Notice | None:
    title = _first_text(record, ("progName", "showTitle", "popTitle", "title"))
    detail_url = _first_text(record, ("url", "pcUrl", "detailUrl"))
    if not title or not detail_url:
        return None

    normalized_url = normalize_notice_url(detail_url)
    if not normalized_url:
        return None

    source_item_id = _first_text(record, ("contentid", "contentId", "id"))
    publish_date = _first_text(record, ("updateTime", "publishDate", "publishTime"))
    stage = _first_text(record, ("progressStageName", "noticeSegmentTypeName", "projectType"))
    purchaser = _first_text(record, ("tenderees", "purchaser", "bidder", "agent"))
    region = _first_text(record, ("areaName", "region"))
    content = _metadata_lines(
        {
            "project_stage": stage,
            "notice_type": _first_text(record, ("noticeSegmentTypeName",)),
            "region": region,
            "purchaser": purchaser,
            "agent": _first_text(record, ("agent",)),
            "budget_amount": _first_text(record, ("budgetAmountNumber",)),
            "tender_amount": _first_text(record, ("tenderAmountNumber",)),
            "bidding_amount": _first_text(record, ("biddingAmountNumber",)),
            "target_tag": _first_text(record, ("targetTag",)),
        }
    )
    raw = {
        "qianlima": {
            key: record.get(key)
            for key in [
                "contentid",
                "progName",
                "showTitle",
                "updateTime",
                "url",
                "areaName",
                "progressStageName",
                "noticeSegmentTypeName",
                "tenderees",
                "agent",
                "bidder",
                "budgetAmountNumber",
                "tenderAmountNumber",
                "biddingAmountNumber",
                "targetTag",
            ]
            if key in record
        }
    }
    return Notice(
        source_id=source.id,
        source_name=source.name,
        source_item_id=str(source_item_id) if source_item_id else "",
        title=title,
        detail_url=detail_url,
        publish_date=publish_date,
        notice_type=stage,
        purchaser=purchaser,
        region=region,
        content=content,
        raw=raw,
    )


def parse_membership_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, Mapping) else {}
    if not isinstance(data, Mapping):
        return {"status": "failed", "reason": "membership payload missing data"}
    member_level = str(data.get("memberLevelName") or "").strip()
    expire_date = str(data.get("expireDate") or "").strip()
    return {
        "status": "success" if member_level or expire_date else "unknown",
        "member_level": member_level,
        "expire_date": expire_date,
        "show_expire_date": bool(data.get("showExpireDate")),
        "is_expired": data.get("isExpired"),
    }


def _extract_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, Mapping):
        records = data.get("data")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, Mapping)]
    return []


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sync_result_counts(result: CrawlResult) -> CrawlResult:
    result.parsed_count = len(result.notices)
    return result


class QianlimaVipSearchClient:
    def __init__(
        self,
        crawler: Any,
        source: Source,
        config: Mapping[str, Any],
        notice_exists: Optional[Callable[[Notice], bool]] = None,
    ):
        self.crawler = crawler
        self.source = source
        self.config = dict(config or {})
        self.notice_exists = notice_exists or (lambda notice: False)
        self.search_endpoint = self.config.get("qianlima_search_endpoint") or QIANLIMA_SEARCH_ENDPOINT
        self.member_info_endpoint = self.config.get("qianlima_member_info_endpoint") or QIANLIMA_MEMBER_INFO_ENDPOINT
        self.max_pages = _safe_int(self.config.get("qianlima_max_pages_per_keyword"), 30)
        self.duplicate_page_limit = _safe_int(self.config.get("qianlima_stop_after_duplicate_pages"), 3)
        self.max_results = _safe_int(self.config.get("qianlima_max_results_per_run"), 1000)

    def collect(self, keywords: Iterable[str], stop_event: Any | None = None) -> CrawlResult:
        result = CrawlResult()
        seen_keys: set[str] = set()
        for keyword in [str(item).strip() for item in keywords if str(item).strip()]:
            duplicate_pages = 0
            for page in range(1, self.max_pages + 1):
                if stop_event and stop_event.is_set():
                    return _sync_result_counts(result)
                if len(result.notices) >= self.max_results:
                    result.diagnostics.append({"status": "stopped", "reason": "max-results", "keyword": keyword})
                    return _sync_result_counts(result)
                payload = build_search_payload(keyword, page, self.config)
                self.crawler._respect_rate_limit(self.search_endpoint)
                response_payload, status_code, status_text = self.crawler.post_json(self.search_endpoint, payload)
                result.fetched_count += 1
                if status_code in (401, 403):
                    result.error_count += 1
                    result.errors.append("qianlima_cookie_invalid_or_expired")
                    result.diagnostics.append(
                        {"status": "failed", "reason": "qianlima_cookie_invalid_or_expired", "status_code": status_code}
                    )
                    return _sync_result_counts(result)
                if status_code == 429 or status_code >= 500:
                    result.error_count += 1
                    result.errors.append(f"qianlima search HTTP {status_code}: {status_text}")
                    result.diagnostics.append(
                        {"status": "failed", "reason": f"qianlima search HTTP {status_code}", "status_code": status_code}
                    )
                    return _sync_result_counts(result)
                records = _extract_records(response_payload)
                if not records:
                    result.diagnostics.append({"status": "stopped", "reason": "empty-page", "keyword": keyword, "page": page})
                    break
                page_had_mapped_candidates = False
                page_all_mapped_candidates_duplicate = True
                for record in records:
                    notice = map_search_record_to_notice(self.source, record)
                    if notice is None:
                        result.skipped_count += 1
                        continue
                    page_had_mapped_candidates = True
                    result.candidate_count += 1
                    key = notice.source_item_id or normalize_notice_url(notice.detail_url)
                    normalized_url = normalize_notice_url(notice.detail_url)
                    duplicate = bool(key and key in seen_keys)
                    duplicate = duplicate or bool(normalized_url and normalized_url in seen_keys)
                    duplicate = duplicate or self.notice_exists(notice)
                    if duplicate:
                        result.skipped_count += 1
                        continue
                    if key:
                        seen_keys.add(key)
                    if normalized_url:
                        seen_keys.add(normalized_url)
                    result.notices.append(notice)
                    page_all_mapped_candidates_duplicate = False
                    if len(result.notices) >= self.max_results:
                        result.diagnostics.append(
                            {"status": "stopped", "reason": "max-results", "keyword": keyword, "page": page}
                        )
                        return _sync_result_counts(result)
                if page_had_mapped_candidates and page_all_mapped_candidates_duplicate:
                    duplicate_pages += 1
                    if duplicate_pages >= self.duplicate_page_limit:
                        result.diagnostics.append(
                            {"status": "stopped", "reason": "duplicate-only-pages", "keyword": keyword, "page": page}
                        )
                        break
                else:
                    duplicate_pages = 0
        return _sync_result_counts(result)

    def fetch_membership_status(self) -> dict[str, Any]:
        self.crawler._respect_rate_limit(self.member_info_endpoint)
        payload, status_code, status_text = self.crawler.get_json(self.member_info_endpoint)
        if status_code in (401, 403):
            return {"status": "failed", "reason": "qianlima_cookie_invalid_or_expired", "status_code": status_code}
        if status_code >= 400:
            return {"status": "failed", "reason": f"HTTP {status_code}: {status_text}", "status_code": status_code}
        return parse_membership_payload(payload)
