# Qianlima VIP Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Qianlima VIP HTTP API-first crawler path that uses authorized Cookie state for search discovery, deduplicates daily results, enriches candidates through existing detail parsing, and shows membership expiration in the Web UI.

**Architecture:** Create a focused `src/crawler/qianlima_vip.py` module for Qianlima-only request payloads, result mapping, pagination, duplicate-page stopping, and membership parsing. Keep `TopologySourceAdapter` as the orchestration point: it detects `source.id == "qianlima"`, invokes the VIP search path when a matching Cookie exists, then merges those notices with existing topology fallback behavior. Expose membership status through an explicit backend API and render it in the built-in sites list without making `/api/sites` block on external network.

**Tech Stack:** Python 3.9+, `unittest`, existing `requests` session through `UrlListCrawler`, FastAPI backend in `server/app.py`, vanilla JS/CSS frontend in `server/static`, no new production dependencies.

## Global Constraints

- Use HTTP API first with Cookie-authenticated requests.
- Search API endpoint: `POST https://search.vip.qianlima.com/rest/service/website/search/solr`.
- Membership info endpoint: `GET https://vip.qianlima.com/rest/u/company/getCompanyInfo`.
- Default daily limit: `qianlima_max_pages_per_keyword = 30`.
- Default backfill limit: `qianlima_backfill_max_pages_per_keyword = 100`.
- Default duplicate-page stop: `qianlima_stop_after_duplicate_pages = 3`.
- Default max run candidates: `qianlima_max_results_per_run = 1000`.
- Default page size: `qianlima_num_per_page = 20`.
- Default search payload values include `timeType = 8` and `sortType = 6`.
- Do not automate login, CAPTCHA, QR-code scanning, or password submission.
- Do not store account passwords, phone numbers, full HAR files, or Cookie values.
- Do not use Playwright as the normal daily crawler.
- Do not bypass member-only access controls; authorized Cookie usage is allowed.
- Do not log Cookie values, username, phone, password, authorization token, or full request bodies.
- Browser rendering is only a fallback for diagnostics or manually triggered verification.

---

## File Structure

- Create `src/crawler/qianlima_vip.py`
  - Owns Qianlima VIP search defaults, request payload construction, response mapping, duplicate tracking, membership parsing, and the `QianlimaVipSearchClient`.
- Modify `src/crawler/source_adapter.py`
  - Detects Qianlima sources, calls the VIP client before generic topology fallback, passes optional persistent duplicate checking, and merges/deduplicates notices.
- Modify `src/crawler/source_crawler.py`
  - Passes a `notice_exists` callback from `CrawlRunner` into the adapter so Qianlima pagination can stop on duplicate-only pages across daily runs.
- Modify `server/site_topologies.json`
  - Adds VIP/search membership hosts and a search URL regex for the confirmed Qianlima endpoint.
- Modify `server/app.py`
  - Backfills Qianlima defaults, exposes `GET /api/sites/qianlima/membership`, and keeps sensitive Cookie values masked in `/api/config`.
- Modify `server/static/app.js`
  - Loads Qianlima membership status on the sites page and renders a compact status line on the Qianlima site row.
- Modify `server/static/styles.css`
  - Adds small site membership status styling consistent with the existing site-management layout.
- Tests:
  - Add `tests/test_qianlima_vip.py`.
  - Extend `tests/test_source_adapter.py`.
  - Extend `tests/test_server_config_defaults.py`.
  - Extend `tests/test_static_frontend_assets.py`.

---

### Task 1: Qianlima VIP Payloads, Mapping, and Membership Parsing

**Files:**
- Create: `src/crawler/qianlima_vip.py`
- Test: `tests/test_qianlima_vip.py`

**Interfaces:**
- Produces: `build_search_payload(keyword: str, page: int, config: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `map_search_record_to_notice(source: Source, record: Mapping[str, Any]) -> Notice | None`
- Produces: `parse_membership_payload(payload: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `has_qianlima_cookie(auth_cookies: Iterable[Mapping[str, Any]]) -> bool`

- [ ] **Step 1: Write failing tests for payload defaults and overrides**

Add this to `tests/test_qianlima_vip.py`:

```python
import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.qianlima_vip import (
    build_search_payload,
    has_qianlima_cookie,
    map_search_record_to_notice,
    parse_membership_payload,
)
from crawler.source_models import Source, normalize_notice_url


class QianlimaVipTests(unittest.TestCase):
    def test_build_search_payload_uses_observed_defaults_and_overrides(self):
        payload = build_search_payload(
            "音视频会议",
            4,
            {
                "qianlima_num_per_page": 50,
                "qianlima_time_type": 7,
                "qianlima_sort_type": "5",
            },
        )

        self.assertEqual(payload["keywords"], "音视频会议")
        self.assertEqual(payload["currentPage"], 4)
        self.assertEqual(payload["numPerPage"], 50)
        self.assertEqual(payload["timeType"], 7)
        self.assertEqual(payload["sortType"], "5")
        self.assertEqual(payload["filtermode"], "8")
        self.assertEqual(payload["types"], "-1")
        self.assertEqual(payload["showContent"], 1)

    def test_has_qianlima_cookie_matches_parent_domain(self):
        self.assertTrue(
            has_qianlima_cookie(
                [
                    {"domain": "example.com", "cookie": "A=1", "enabled": True},
                    {"domain": ".qianlima.com", "cookie": "SESSION=secret", "enabled": True},
                ]
            )
        )
        self.assertFalse(has_qianlima_cookie([{"domain": "qianlima.com", "cookie": "", "enabled": True}]))
        self.assertFalse(has_qianlima_cookie([{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": False}]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_build_search_payload_uses_observed_defaults_and_overrides tests/test_qianlima_vip.py::QianlimaVipTests::test_has_qianlima_cookie_matches_parent_domain -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.qianlima_vip'`.

- [ ] **Step 3: Implement payload and Cookie helpers**

Create `src/crawler/qianlima_vip.py`:

```python
"""Qianlima VIP authenticated search helpers."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import urljoin, urlparse

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
```

- [ ] **Step 4: Run payload tests to verify they pass**

Run: `python3 -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_build_search_payload_uses_observed_defaults_and_overrides tests/test_qianlima_vip.py::QianlimaVipTests::test_has_qianlima_cookie_matches_parent_domain -q`

Expected: PASS.

- [ ] **Step 5: Write failing tests for result mapping and membership sanitization**

Append to `QianlimaVipTests` in `tests/test_qianlima_vip.py`:

```python
    def test_map_search_record_to_notice_uses_qianlima_fields(self):
        source = Source(id="qianlima", name="千里马", url="https://www.qianlima.com/")
        notice = map_search_record_to_notice(
            source,
            {
                "contentid": 610713231,
                "progName": "上海音视频会议系统公开招标公告",
                "showTitle": "备用标题",
                "updateTime": "2026-07-05",
                "url": "http://www.qianlima.com/zb/detail/20260705_610713231.html",
                "areaName": "上海",
                "progressStageName": "招标公告",
                "noticeSegmentTypeName": "公开招标",
                "tenderees": "上海采购单位",
                "agent": "上海代理机构",
                "budgetAmountNumber": "120",
            },
        )

        self.assertIsNotNone(notice)
        self.assertEqual(notice.source_id, "qianlima")
        self.assertEqual(notice.source_item_id, "610713231")
        self.assertEqual(notice.title, "上海音视频会议系统公开招标公告")
        self.assertEqual(notice.detail_url, "http://www.qianlima.com/zb/detail/20260705_610713231.html")
        self.assertEqual(notice.publish_date, "2026-07-05")
        self.assertEqual(notice.region, "上海")
        self.assertEqual(notice.notice_type, "招标公告")
        self.assertEqual(notice.purchaser, "上海采购单位")
        self.assertIn("project_stage: 招标公告", notice.content)
        self.assertIn("budget_amount: 120", notice.content)
        self.assertEqual(notice.raw["qianlima"]["contentid"], 610713231)

    def test_map_search_record_to_notice_skips_missing_title_or_url(self):
        source = Source(id="qianlima", name="千里马", url="https://www.qianlima.com/")
        self.assertIsNone(map_search_record_to_notice(source, {"contentid": 1, "progName": "标题"}))
        self.assertIsNone(map_search_record_to_notice(source, {"url": "https://www.qianlima.com/bid-1.html"}))

    def test_parse_membership_payload_keeps_only_safe_fields(self):
        status = parse_membership_payload(
            {
                "code": 200,
                "data": {
                    "memberLevelName": "VIP会员",
                    "expireDate": "2026-12-31",
                    "showExpireDate": True,
                    "isExpired": False,
                    "username": "secret-user",
                    "shouji": "13800000000",
                    "email": "secret@example.com",
                },
                "msg": "OK",
            }
        )

        self.assertEqual(status["status"], "success")
        self.assertEqual(status["member_level"], "VIP会员")
        self.assertEqual(status["expire_date"], "2026-12-31")
        self.assertTrue(status["show_expire_date"])
        self.assertFalse(status["is_expired"])
        self.assertNotIn("username", json.dumps(status, ensure_ascii=False))
        self.assertNotIn("13800000000", json.dumps(status, ensure_ascii=False))
```

- [ ] **Step 6: Run mapping tests to verify they fail**

Run: `python3 -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_map_search_record_to_notice_uses_qianlima_fields tests/test_qianlima_vip.py::QianlimaVipTests::test_map_search_record_to_notice_skips_missing_title_or_url tests/test_qianlima_vip.py::QianlimaVipTests::test_parse_membership_payload_keeps_only_safe_fields -q`

Expected: FAIL with import errors for `map_search_record_to_notice` and `parse_membership_payload`.

- [ ] **Step 7: Implement mapping and membership parsing**

Append this to `src/crawler/qianlima_vip.py`:

```python
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
```

- [ ] **Step 8: Run all Task 1 tests**

Run: `python3 -m pytest tests/test_qianlima_vip.py -q`

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/crawler/qianlima_vip.py tests/test_qianlima_vip.py
git commit -m "feat: add qianlima vip mapping helpers"
```

---

### Task 2: Qianlima VIP Search Client and Adaptive Pagination

**Files:**
- Modify: `src/crawler/qianlima_vip.py`
- Test: `tests/test_qianlima_vip.py`

**Interfaces:**
- Consumes: `build_search_payload`, `map_search_record_to_notice`, `parse_membership_payload`, `has_qianlima_cookie`
- Produces: `QianlimaVipSearchClient(crawler: Any, source: Source, config: Mapping[str, Any], notice_exists: Callable[[Notice], bool] | None = None)`
- Produces: `QianlimaVipSearchClient.collect(keywords: Iterable[str], stop_event: Any | None = None) -> CrawlResult`
- Produces: `QianlimaVipSearchClient.fetch_membership_status() -> dict[str, Any]`

- [ ] **Step 1: Write failing pagination, duplicate-stop, and membership fetch tests**

Append to `tests/test_qianlima_vip.py`:

```python
class FakeQianlimaCrawler:
    timeout = 10
    session = object()

    def __init__(self, pages, statuses=None):
        self.pages = pages
        self.statuses = statuses or {}
        self.calls = []
        self.auth_cookies = [{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}]

    def _respect_rate_limit(self, url):
        self.calls.append(("rate", url))

    def _get_headers(self):
        return {"User-Agent": "test-agent"}

    def _get_cookie_for_url(self, url):
        return "SESSION=secret"

    def _emit_info(self, message):
        self.calls.append(("info", message))

    def post_json(self, url, payload):
        self.calls.append(("POST", url, payload))
        page = payload["currentPage"]
        status = self.statuses.get(page, 200)
        if status >= 400:
            return {"code": status, "data": {}}, status, "ERR"
        return self.pages.get(page, {"code": 200, "data": {"data": []}}), status, "OK"

    def get_json(self, url):
        self.calls.append(("GET", url))
        return {
            "code": 200,
            "data": {
                "memberLevelName": "VIP会员",
                "expireDate": "2026-12-31",
                "showExpireDate": True,
            },
        }, 200, "OK"


class QianlimaVipClientTests(unittest.TestCase):
    def make_source(self):
        return Source(id="qianlima", name="千里马", url="https://www.qianlima.com/")

    def test_collect_pages_until_empty_and_maps_notices(self):
        from crawler.qianlima_vip import QianlimaVipSearchClient

        crawler = FakeQianlimaCrawler(
            {
                1: {
                    "code": 200,
                    "data": {
                        "data": [
                            {
                                "contentid": 1,
                                "progName": "上海会议系统招标公告",
                                "updateTime": "2026-07-05",
                                "url": "http://www.qianlima.com/zb/detail/20260705_1.html",
                                "areaName": "上海",
                            }
                        ]
                    },
                },
                2: {"code": 200, "data": {"data": []}},
            }
        )
        client = QianlimaVipSearchClient(
            crawler,
            self.make_source(),
            {"qianlima_max_pages_per_keyword": 5, "qianlima_max_results_per_run": 100},
        )

        result = client.collect(["会议"])

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].source_item_id, "1")
        self.assertEqual(result.candidate_count, 1)
        post_pages = [call[2]["currentPage"] for call in crawler.calls if call[0] == "POST"]
        self.assertEqual(post_pages, [1, 2])

    def test_collect_stops_after_duplicate_only_pages(self):
        from crawler.qianlima_vip import QianlimaVipSearchClient

        duplicate_record = {
            "contentid": 7,
            "progName": "上海会议系统招标公告",
            "updateTime": "2026-07-05",
            "url": "http://www.qianlima.com/zb/detail/20260705_7.html",
        }
        crawler = FakeQianlimaCrawler(
            {
                1: {"code": 200, "data": {"data": [duplicate_record]}},
                2: {"code": 200, "data": {"data": [duplicate_record]}},
                3: {"code": 200, "data": {"data": [duplicate_record]}},
                4: {"code": 200, "data": {"data": [duplicate_record]}},
            }
        )
        client = QianlimaVipSearchClient(
            crawler,
            self.make_source(),
            {
                "qianlima_max_pages_per_keyword": 10,
                "qianlima_stop_after_duplicate_pages": 2,
                "qianlima_max_results_per_run": 100,
            },
            notice_exists=lambda notice: notice.source_item_id == "7",
        )

        result = client.collect(["会议"])

        self.assertEqual(result.notices, [])
        post_pages = [call[2]["currentPage"] for call in crawler.calls if call[0] == "POST"]
        self.assertEqual(post_pages, [1, 2])
        self.assertIn("duplicate-only", result.diagnostics[-1]["reason"])

    def test_fetch_membership_status_uses_safe_parser(self):
        from crawler.qianlima_vip import QianlimaVipSearchClient

        crawler = FakeQianlimaCrawler({})
        client = QianlimaVipSearchClient(crawler, self.make_source(), {})

        status = client.fetch_membership_status()

        self.assertEqual(status["status"], "success")
        self.assertEqual(status["member_level"], "VIP会员")
        self.assertEqual(status["expire_date"], "2026-12-31")
        self.assertTrue(any(call[0] == "GET" and call[1].endswith("/rest/u/company/getCompanyInfo") for call in crawler.calls))
```

- [ ] **Step 2: Run Task 2 red tests to verify they fail**

Run: `python3 -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_pages_until_empty_and_maps_notices tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_after_duplicate_only_pages tests/test_qianlima_vip.py::QianlimaVipClientTests::test_fetch_membership_status_uses_safe_parser -q`

Expected: FAIL with `ImportError` or `AttributeError` for `QianlimaVipSearchClient`.

- [ ] **Step 3: Implement client collection with duplicate-page stopping**

Append to `src/crawler/qianlima_vip.py`:

```python
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

    def collect(self, keywords: Iterable[str], stop_event: Any | None = None) -> Any:
        try:
            from .source_models import CrawlResult
        except ImportError:  # pragma: no cover
            from crawler.source_models import CrawlResult

        result = CrawlResult()
        seen_keys: set[str] = set()
        for keyword in [str(item).strip() for item in keywords if str(item).strip()]:
            duplicate_pages = 0
            for page in range(1, self.max_pages + 1):
                if stop_event and stop_event.is_set():
                    return result
                if len(result.notices) >= self.max_results:
                    result.diagnostics.append({"status": "stopped", "reason": "max-results", "keyword": keyword})
                    return result
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
                    return result
                if status_code == 429 or status_code >= 500:
                    result.error_count += 1
                    result.errors.append(f"qianlima search HTTP {status_code}: {status_text}")
                    result.diagnostics.append(
                        {"status": "failed", "reason": f"qianlima search HTTP {status_code}", "status_code": status_code}
                    )
                    return result
                records = _extract_records(response_payload)
                if not records:
                    result.diagnostics.append({"status": "stopped", "reason": "empty-page", "keyword": keyword, "page": page})
                    break
                page_new_count = 0
                for record in records:
                    notice = map_search_record_to_notice(self.source, record)
                    if notice is None:
                        result.skipped_count += 1
                        continue
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
                    result.candidate_count += 1
                    page_new_count += 1
                if page_new_count == 0:
                    duplicate_pages += 1
                    if duplicate_pages >= self.duplicate_page_limit:
                        result.diagnostics.append(
                            {"status": "stopped", "reason": "duplicate-only-pages", "keyword": keyword, "page": page}
                        )
                        break
                else:
                    duplicate_pages = 0
        result.parsed_count = len(result.notices)
        return result

    def fetch_membership_status(self) -> dict[str, Any]:
        self.crawler._respect_rate_limit(self.member_info_endpoint)
        payload, status_code, status_text = self.crawler.get_json(self.member_info_endpoint)
        if status_code in (401, 403):
            return {"status": "failed", "reason": "qianlima_cookie_invalid_or_expired", "status_code": status_code}
        if status_code >= 400:
            return {"status": "failed", "reason": f"HTTP {status_code}: {status_text}", "status_code": status_code}
        return parse_membership_payload(payload)
```

- [ ] **Step 4: Run pagination tests to verify they pass**

Run: `python3 -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests -q`

Expected: PASS.

- [ ] **Step 5: Run all Task 2 tests**

Run: `python3 -m pytest tests/test_qianlima_vip.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/crawler/qianlima_vip.py tests/test_qianlima_vip.py
git commit -m "feat: add qianlima vip search client"
```

---

### Task 3: Adapter Integration, Detail Merge, and Topology Updates

**Files:**
- Modify: `src/crawler/source_adapter.py`
- Modify: `src/crawler/source_crawler.py`
- Modify: `server/site_topologies.json`
- Test: `tests/test_source_adapter.py`
- Test: `tests/test_source_crawler.py`
- Test: `tests/test_url_list_crawler.py`

**Interfaces:**
- Consumes: `QianlimaVipSearchClient.collect(keywords, stop_event) -> CrawlResult`
- Consumes: `has_qianlima_cookie(auth_cookies) -> bool`
- Produces: `TopologySourceAdapter.collect(source: Source, stop_event=None, notice_exists=None) -> CrawlResult`

- [ ] **Step 1: Write failing adapter test for VIP-first Qianlima search and detail enrichment**

Append this method inside `TopologySourceAdapterTests` in `tests/test_source_adapter.py`:

```python
    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_qianlima_uses_vip_search_then_enriches_details(self, mock_request_url):
        from crawler.source_models import CrawlResult

        detail_url = "http://www.qianlima.com/zb/detail/20260705_8.html"
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            topology={
                "id": "qianlima",
                "name": "千里马",
                "entry_url": "https://www.qianlima.com/",
                "allowed_hosts": ["www.qianlima.com", "search.vip.qianlima.com"],
                "detail_url_regex": [r"^https?://www\\.qianlima\\.com/zb/detail/\\d{8}_\\d+\\.html$"],
            },
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )

        mock_request_url.return_value = (
            """
            <html><body>
                <h1>上海会议系统招标公告</h1>
                <main>
                    项目名称：上海会议系统公开招标项目
                    采购人：上海采购单位
                    预算金额：120万元
                    发布时间：2026-07-05
                </main>
            </body></html>
            """,
            200,
            "OK",
        )

        adapter = TopologySourceAdapter(
            {
                "keywords": ["会议"],
                "qianlima_max_pages_per_keyword": 1,
                "qianlima_max_results_per_run": 20,
            }
        )
        vip_result = CrawlResult(
            notices=[
                Notice(
                    source_id="qianlima",
                    source_name="千里马",
                    source_item_id="8",
                    title="上海会议系统招标公告",
                    detail_url=detail_url,
                    publish_date="2026-07-05",
                    content="project_stage: 招标公告",
                    raw={"qianlima": {"contentid": 8}},
                )
            ],
            fetched_count=1,
            candidate_count=1,
            parsed_count=1,
            diagnostics=[{"status": "success", "parsed_count": 1}],
        )

        with patch("crawler.qianlima_vip.QianlimaVipSearchClient.collect", return_value=vip_result) as collect_mock:
            result = adapter.collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].source_item_id, "8")
        self.assertEqual(result.notices[0].title, "上海会议系统招标公告")
        self.assertIn("预算金额", result.notices[0].content)
        self.assertIn("qianlima_search", result.notices[0].raw)
        mock_request_url.assert_called_once_with(detail_url)
        collect_mock.assert_called_once()
```

- [ ] **Step 2: Run adapter test to verify it fails**

Run: `python3 -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details -q`

Expected: FAIL because `TopologySourceAdapter.collect()` does not call `QianlimaVipSearchClient`.

- [ ] **Step 3: Add JSON HTTP helpers to `UrlListCrawler` through adapter-built crawler instances**

Modify `src/crawler/source_adapter.py` inside `_build_crawler()` after `crawler = UrlListCrawler(config, source_config)`:

```python
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
```

- [ ] **Step 4: Integrate Qianlima VIP collection and detail enrichment in `TopologySourceAdapter.collect()`**

Modify `src/crawler/source_adapter.py` imports:

```python
    from .qianlima_vip import QIANLIMA_SOURCE_ID, QianlimaVipSearchClient, has_qianlima_cookie
```

and in the fallback import block:

```python
    from crawler.qianlima_vip import QIANLIMA_SOURCE_ID, QianlimaVipSearchClient, has_qianlima_cookie
```

Change the method signature:

```python
    def collect(self, source: Source, stop_event=None, notice_exists=None) -> CrawlResult:
```

At the beginning of `collect()` after `crawler = self._build_crawler(source)`, replace the existing timestamp line with this early VIP branch followed by the existing generic topology path:

```python
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
```

Keep the existing generic topology code below that branch, but remove its duplicate `timestamp = datetime.now().isoformat(timespec="seconds")` assignment. Add these methods inside `TopologySourceAdapter`:

```python
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
                if detail_notice.title and _is_admissible_notice_detail_url(detail_notice.detail_url):
                    return detail_notice
        return None

    def _merge_qianlima_detail_notice(self, search_notice: Notice, detail_notice: Notice) -> Notice:
        if not detail_notice.publish_date:
            detail_notice.publish_date = search_notice.publish_date
        if not detail_notice.source_item_id:
            detail_notice.source_item_id = search_notice.source_item_id
        if not detail_notice.notice_type:
            detail_notice.notice_type = search_notice.notice_type
        if not detail_notice.purchaser:
            detail_notice.purchaser = search_notice.purchaser
        if not detail_notice.region:
            detail_notice.region = search_notice.region
        if detail_notice.title == detail_notice.detail_url:
            detail_notice.title = search_notice.title
        detail_notice.raw = {
            "qianlima_search": search_notice.raw.get("qianlima", search_notice.raw),
            "detail": detail_notice.raw.get("legacy", detail_notice.raw),
        }
        return detail_notice
```

- [ ] **Step 5: Run adapter test to verify it passes**

Run: `python3 -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details -q`

Expected: PASS.

- [ ] **Step 6: Write failing source runner test for persistent duplicate checker wiring**

Append this method inside `CrawlRunnerTests` in `tests/test_source_crawler.py`:

```python
    def test_run_source_passes_notice_exists_callback(self):
        class DuplicateAwareAdapter:
            def __init__(self):
                self.notice_exists = None

            def collect(self, source, stop_event=None, notice_exists=None):
                self.notice_exists = notice_exists
                result = CrawlResult()
                notice = Notice(
                    source_id=source.id,
                    source_name=source.name,
                    title="A",
                    detail_url="https://example.com/a",
                )
                self.notice_exists(notice)
                result.notices = [notice]
                return result

        class DuplicateAwareStorage(FakeStorage):
            def __init__(self):
                super().__init__()
                self.exists_called = False

            def exists(self, bid):
                self.exists_called = True
                return False

        storage = DuplicateAwareStorage()
        adapter = DuplicateAwareAdapter()
        runner = CrawlRunner(storage, adapter=adapter)

        runner.run_source(Source(id="qianlima", name="千里马", url="https://www.qianlima.com/"))

        self.assertTrue(storage.exists_called)
```

- [ ] **Step 7: Run source runner test to verify it fails**

Run: `python3 -m pytest tests/test_source_crawler.py::CrawlRunnerTests::test_run_source_passes_notice_exists_callback -q`

Expected: FAIL because `CrawlRunner.run_source()` does not pass `notice_exists`.

- [ ] **Step 8: Pass persistent duplicate checker from `CrawlRunner`**

Modify `src/crawler/source_crawler.py` inside `CrawlRunner.run_source()`:

```python
            result = self.adapter.collect(
                source,
                stop_event=stop_event,
                notice_exists=lambda notice: self.storage.exists(notice.to_bid_info()),
            )
```

Modify the test helpers at the top of `tests/test_source_crawler.py` so existing tests accept the new adapter contract:

```python
class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def collect(self, source, stop_event=None, notice_exists=None):
        self.calls.append((source, stop_event, notice_exists))
        return self.result


class RaisingAdapter:
    def __init__(self, exception):
        self.exception = exception
        self.calls = []

    def collect(self, source, stop_event=None, notice_exists=None):
        self.calls.append((source, stop_event, notice_exists))
        raise self.exception
```

In `test_run_source_records_successful_run_and_tags_legacy_bids`, replace:

```python
        self.assertEqual(adapter.calls, [(source, None)])
```

with:

```python
        self.assertEqual(adapter.calls[0][0], source)
        self.assertIsNone(adapter.calls[0][1])
        self.assertTrue(callable(adapter.calls[0][2]))
```

- [ ] **Step 9: Run source runner tests**

Run: `python3 -m pytest tests/test_source_crawler.py::CrawlRunnerTests -q`

Expected: PASS.

- [ ] **Step 10: Update topology and test recognized hosts/search URL**

Modify `server/site_topologies.json` for the Qianlima site:

```json
"allowed_hosts": [
  "www.qianlima.com",
  "search.qianlima.com",
  "search.vip.qianlima.com",
  "vip.qianlima.com",
  "home.qianlima.com",
  "wap.qianlima.com",
  "gw-static.qianlima.com",
  "customer.qianlima.com"
],
"search_url_regex": [
  "^https?://search\\.vip\\.qianlima\\.com/rest/service/website/search/solr$"
],
```

Add this test to `tests/test_url_list_crawler.py` near existing Qianlima tests:

```python
    def test_qianlima_vip_search_endpoint_is_classified_as_search(self):
        crawler = self.make_crawler("missing.txt")
        rule = crawler._classify_url("https://search.vip.qianlima.com/rest/service/website/search/solr")
        self.assertEqual(rule["topology_id"], "qianlima")
        self.assertEqual(rule["page_type"], "search")
```

- [ ] **Step 11: Run integration-related tests**

Run: `python3 -m pytest tests/test_qianlima_vip.py tests/test_source_adapter.py tests/test_source_crawler.py::CrawlRunnerTests tests/test_url_list_crawler.py::UrlListCrawlerTests::test_qianlima_vip_search_endpoint_is_classified_as_search -q`

Expected: PASS.

- [ ] **Step 12: Commit Task 3**

```bash
git add src/crawler/source_adapter.py src/crawler/source_crawler.py server/site_topologies.json tests/test_source_adapter.py tests/test_source_crawler.py tests/test_url_list_crawler.py
git commit -m "feat: integrate qianlima vip search"
```

---

### Task 4: Membership Status Backend API and Config Defaults

**Files:**
- Modify: `server/app.py`
- Test: `tests/test_server_config_defaults.py`

**Interfaces:**
- Consumes: `parse_membership_payload(payload) -> dict[str, Any]`
- Produces: `GET /api/sites/qianlima/membership -> {"status": str, "member_level": str, "expire_date": str, "show_expire_date": bool, "is_expired": Any}`

- [ ] **Step 1: Write failing config default test**

Add to `tests/test_server_config_defaults.py`:

```python
    def test_default_config_backfills_qianlima_vip_search_options(self):
        config = app.normalize_config({"csv_url_sources": [{"file_path": app.DEFAULT_URL_SOURCES_PATH}]})

        self.assertTrue(config["qianlima_vip_search_enabled"])
        self.assertEqual(config["qianlima_num_per_page"], 20)
        self.assertEqual(config["qianlima_max_pages_per_keyword"], 30)
        self.assertEqual(config["qianlima_backfill_max_pages_per_keyword"], 100)
        self.assertEqual(config["qianlima_stop_after_duplicate_pages"], 3)
        self.assertEqual(config["qianlima_max_results_per_run"], 1000)
        self.assertEqual(config["qianlima_time_type"], 8)
        self.assertEqual(config["qianlima_sort_type"], 6)
```

- [ ] **Step 2: Run config default test to verify it fails**

Run: `python3 -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_default_config_backfills_qianlima_vip_search_options -q`

Expected: FAIL because the defaults are missing.

- [ ] **Step 3: Add config defaults**

Modify `server/app.py` inside `normalize_config()` before `return config`:

```python
    config.setdefault('qianlima_vip_search_enabled', True)
    config.setdefault('qianlima_num_per_page', 20)
    config.setdefault('qianlima_max_pages_per_keyword', 30)
    config.setdefault('qianlima_backfill_max_pages_per_keyword', 100)
    config.setdefault('qianlima_stop_after_duplicate_pages', 3)
    config.setdefault('qianlima_max_results_per_run', 1000)
    config.setdefault('qianlima_time_type', 8)
    config.setdefault('qianlima_sort_type', 6)
```

Also add optional fields to `ConfigModel`:

```python
    qianlima_vip_search_enabled: Optional[bool] = None
    qianlima_num_per_page: Optional[int] = None
    qianlima_max_pages_per_keyword: Optional[int] = None
    qianlima_backfill_max_pages_per_keyword: Optional[int] = None
    qianlima_stop_after_duplicate_pages: Optional[int] = None
    qianlima_max_results_per_run: Optional[int] = None
    qianlima_time_type: Optional[int] = None
    qianlima_sort_type: Optional[int] = None
```

- [ ] **Step 4: Run config default test to verify it passes**

Run: `python3 -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_default_config_backfills_qianlima_vip_search_options -q`

Expected: PASS.

- [ ] **Step 5: Write failing membership endpoint tests**

Append to `tests/test_server_config_defaults.py`:

```python
    @patch("app.UrlListCrawler")
    def test_qianlima_membership_endpoint_returns_safe_status(self, crawler_cls):
        fake_crawler = crawler_cls.return_value
        fake_crawler.get_json.return_value = (
            {
                "code": 200,
                "data": {
                    "memberLevelName": "VIP会员",
                    "expireDate": "2026-12-31",
                    "showExpireDate": True,
                    "username": "secret-user",
                    "shouji": "13800000000",
                },
            },
            200,
            "OK",
        )
        app.app_state.config = app.normalize_config(
            {
                "csv_url_sources": [
                    {
                        "name": "招标URL源",
                        "source_type": "json",
                        "file_path": app.DEFAULT_URL_SOURCES_PATH,
                        "auth_cookies": [{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
                    }
                ]
            }
        )

        result = asyncio.run(app.get_qianlima_membership(user={"role": "user"}))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["member_level"], "VIP会员")
        self.assertEqual(result["expire_date"], "2026-12-31")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("secret-user", serialized)
        self.assertNotIn("13800000000", serialized)

    def test_qianlima_membership_endpoint_reports_missing_cookie(self):
        app.app_state.config = app.normalize_config({"csv_url_sources": [{"file_path": app.DEFAULT_URL_SOURCES_PATH, "auth_cookies": []}]})

        result = asyncio.run(app.get_qianlima_membership(user={"role": "user"}))

        self.assertEqual(result["status"], "missing_cookie")
```

- [ ] **Step 6: Run membership endpoint tests to verify they fail**

Run: `python3 -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_returns_safe_status tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_reports_missing_cookie -q`

Expected: FAIL because `get_qianlima_membership` does not exist.

- [ ] **Step 7: Implement backend membership endpoint**

Add imports near other crawler imports in `server/app.py`:

```python
from crawler.url_list import UrlListCrawler
from crawler.qianlima_vip import QIANLIMA_MEMBER_INFO_ENDPOINT, has_qianlima_cookie, parse_membership_payload
```

Add helper functions near site helpers:

```python
def qianlima_auth_cookies_from_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for source in config.get('csv_url_sources', []):
        for item in source.get('auth_cookies', []) or []:
            if isinstance(item, dict):
                cookies.append(item)
    return cookies


def build_qianlima_membership_crawler(config: Dict[str, Any]) -> UrlListCrawler:
    source_config = {
        "name": "千里马会员状态",
        "file_path": "",
        "auth_cookies": qianlima_auth_cookies_from_config(config),
        "domain_delay": config.get("domain_delay", 0),
    }
    crawler = UrlListCrawler(config, source_config)

    def get_json(url: str):
        html, status_code, status_text = crawler._request_url(url)
        try:
            return json.loads(html or "{}"), status_code, status_text
        except (TypeError, ValueError):
            return {}, status_code, status_text

    crawler.get_json = get_json
    return crawler
```

Add endpoint before `result_summary()`:

```python
@app.get("/api/sites/qianlima/membership")
async def get_qianlima_membership(user: Dict[str, Any] = Depends(get_current_user)):
    config = app_state.config
    cookies = qianlima_auth_cookies_from_config(config)
    if not has_qianlima_cookie(cookies):
        return {"status": "missing_cookie", "reason": "未配置 qianlima.com 授权 Cookie"}
    crawler = build_qianlima_membership_crawler(config)
    payload, status_code, status_text = crawler.get_json(
        config.get("qianlima_member_info_endpoint") or QIANLIMA_MEMBER_INFO_ENDPOINT
    )
    if status_code in (401, 403):
        return {"status": "failed", "reason": "qianlima_cookie_invalid_or_expired", "status_code": status_code}
    if status_code >= 400:
        return {"status": "failed", "reason": f"HTTP {status_code}: {status_text}", "status_code": status_code}
    return parse_membership_payload(payload)
```

- [ ] **Step 8: Run backend membership tests**

Run: `python3 -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_returns_safe_status tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_reports_missing_cookie -q`

Expected: PASS.

- [ ] **Step 9: Run server config tests**

Run: `python3 -m pytest tests/test_server_config_defaults.py -q`

Expected: PASS.

- [ ] **Step 10: Commit Task 4**

```bash
git add server/app.py tests/test_server_config_defaults.py
git commit -m "feat: expose qianlima membership status"
```

---

### Task 5: Web UI Membership Status Display

**Files:**
- Modify: `server/static/app.js`
- Modify: `server/static/styles.css`
- Test: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: `GET /api/sites/qianlima/membership`
- Produces: a Qianlima-only membership line rendered in the sites list.

- [ ] **Step 1: Write failing frontend contract test**

Add to `tests/test_static_frontend_assets.py`:

```python
    def test_qianlima_membership_status_contract_exists(self):
        js = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn("/api/sites/qianlima/membership", js)
        self.assertIn("loadQianlimaMembership", js)
        self.assertIn("qianlima_membership", js)
        self.assertIn("site-membership", css)
```

- [ ] **Step 2: Run frontend contract test to verify it fails**

Run: `python3 -m pytest tests/test_static_frontend_assets.py::StaticFrontendAssetTests::test_qianlima_membership_status_contract_exists -q`

Expected: FAIL because the JS and CSS do not include the membership contract.

- [ ] **Step 3: Add membership state and loader to `app.js`**

Modify `server/static/app.js` near other top-level state:

```javascript
let qianlimaMembership = null;
```

Add after `loadSites()`:

```javascript
async function loadQianlimaMembership() {
    try {
        const res = await apiFetch('/api/sites/qianlima/membership');
        qianlimaMembership = await res.json();
    } catch (e) {
        qianlimaMembership = { status: 'failed', reason: e.message };
    }
    renderSites();
}
```

Modify `loadSites()`:

```javascript
async function loadSites() {
    try {
        const res = await apiFetch('/api/sites');
        currentSites = await res.json();
        renderSites();
        loadQianlimaMembership();
    } catch (e) {
        console.error(e);
        document.getElementById('sitesList').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}
```

Add a render helper before `renderSites()`:

```javascript
function renderQianlimaMembership(site) {
    if (!site || site.key !== 'qianlima') return '';
    if (!qianlimaMembership) return '<div class="site-membership is-muted">会员状态：检测中</div>';
    if (qianlimaMembership.status === 'missing_cookie') {
        return '<div class="site-membership is-warning">会员状态：未配置 Cookie</div>';
    }
    if (qianlimaMembership.status !== 'success') {
        const reason = qianlimaMembership.reason || '检测失败';
        return `<div class="site-membership is-warning">会员状态：${escapeHtml(reason)}</div>`;
    }
    const level = qianlimaMembership.member_level || '会员';
    const expire = qianlimaMembership.expire_date ? `，到期：${qianlimaMembership.expire_date}` : '';
    return `<div class="site-membership">会员状态：${escapeHtml(level + expire)}</div>`;
}
```

Modify the Qianlima row in `renderSites()` after `site-meta`:

```javascript
                    <div class="site-meta">最近检测：${checkedAt}</div>
                    ${renderQianlimaMembership(s)}
                    ${diagnostic}
```

- [ ] **Step 4: Add CSS**

Append near existing site styles in `server/static/styles.css`:

```css
.site-membership {
    color: var(--text-secondary);
    font-size: var(--font-size-sm);
    line-height: 1.5;
    margin-top: 4px;
}

.site-membership.is-warning {
    color: #8a5a00;
}

.site-membership.is-muted {
    color: var(--muted);
}
```

- [ ] **Step 5: Run frontend contract test**

Run: `python3 -m pytest tests/test_static_frontend_assets.py::StaticFrontendAssetTests::test_qianlima_membership_status_contract_exists -q`

Expected: PASS.

- [ ] **Step 6: Run broader static frontend tests**

Run: `python3 -m pytest tests/test_static_frontend_assets.py -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add server/static/app.js server/static/styles.css tests/test_static_frontend_assets.py
git commit -m "feat: show qianlima membership status"
```

---

## Final Verification

- [ ] **Step 1: Run focused crawler and server tests**

Run:

```bash
python3 -m pytest tests/test_qianlima_vip.py tests/test_source_adapter.py tests/test_url_list_crawler.py tests/test_server_config_defaults.py tests/test_static_frontend_assets.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
python3 -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: no unstaged implementation files. The developer-only `tools/qianlima_playwright_probe.py` may remain untracked unless the user explicitly wants to keep and commit it.

---

## Plan Self-Review

Spec coverage:

- HTTP API first with Cookie-authenticated requests: Tasks 2 and 3.
- Adaptive pagination and duplicate-only stop: Task 2.
- Existing topology detail parsing preserved: Task 3 enriches VIP search candidates through the existing detail-page parser, falls back to search metadata when detail fetch is blocked, and keeps generic topology fallback when VIP search yields no notices.
- Membership expiration display: Tasks 4 and 5.
- No credential storage or sensitive logging: Tasks 1, 2, and 4 keep only sanitized fields; no task logs Cookie values.
- Playwright not in production path: no production dependency or runtime code uses Playwright.
- Conservative defaults: Task 4.
- Tests: each planned behavior has a focused test.

Placeholder scan:

- No `TBD`, `TODO`, or open-ended "add appropriate" steps are present.
- Example placeholders such as `<keyword>` appear only as literal request-template values from the approved spec.

Type consistency:

- `QianlimaVipSearchClient.collect()` returns `CrawlResult`.
- `parse_membership_payload()` returns a safe dict consumed by the FastAPI endpoint and frontend.
- `notice_exists` accepts a `Notice` and returns `bool` in both adapter and runner tasks.
