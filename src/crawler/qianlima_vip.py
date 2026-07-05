"""Qianlima VIP authenticated search helpers."""
from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

try:
    from .source_models import Notice, Source, normalize_notice_url
except ImportError:  # pragma: no cover
    from crawler.source_models import Notice, Source, normalize_notice_url


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
