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
