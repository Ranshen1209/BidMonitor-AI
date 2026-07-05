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
