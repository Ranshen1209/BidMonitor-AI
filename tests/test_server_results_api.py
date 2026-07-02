import asyncio
import os
import sys
import unittest
from unittest.mock import Mock, patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
SRC_DIR = os.path.join(ROOT_DIR, "src")
for path in [SERVER_DIR, SRC_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

import app
from database.storage import BidInfo


class ServerResultsApiTests(unittest.TestCase):
    def setUp(self):
        self.storage = Mock()
        app.app_state.storage = self.storage
        app.app_state.config = {
            "non_follow_reason_tags": ["地域问题", "其它"],
            "ai_config": {"api_key": "secret"},
        }

    def make_bid(self):
        bid = BidInfo("项目A", "https://example.com/a", "2026-07-01", "源", purchaser="采购人")
        bid.id = 7
        bid.fit_status = "pending"
        bid.follow_decision = "pending"
        bid.urgency = "medium"
        bid.urgency_source = "auto"
        bid.project_stage = "lead"
        bid.region = "上海"
        bid.category = "弱电智能化"
        bid.amount = "50"
        bid.amount_unit = "万元"
        bid.registration_deadline = "2026-07-03 17:00"
        bid.submission_deadline = "2026-07-05 10:00"
        bid.bid_opening_time = "2026-07-05 10:30"
        bid.ai_extract_status = "extracted"
        bid.detail_fetch_status = "success"
        bid.ai_extracted_data = {"organization": "AI单位", "deadlines": []}
        bid.manual_overrides = {"organization": "人工单位"}
        bid.non_follow_reasons = []
        bid.review_notes = ""
        return bid

    def test_get_results_returns_table_fields_and_filters(self):
        bid = self.make_bid()
        self.storage.query_results.return_value = ([bid], 1)

        result = asyncio.run(app.get_results(limit=20, offset=0, fit_status="pending", user={"role": "user"}))

        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["id"], 7)
        self.assertEqual(item["organization"], "人工单位")
        self.assertEqual(item["registration_deadline"], "2026-07-03 17:00")
        self.assertEqual(item["submission_deadline"], "2026-07-05 10:00")
        self.assertEqual(item["bid_opening_time"], "2026-07-05 10:30")
        self.storage.query_results.assert_called_once()
        self.assertEqual(self.storage.query_results.call_args.args[0]["fit_status"], "pending")

    def test_get_results_applies_q_without_forwarding_unsupported_filter(self):
        bid = self.make_bid()
        bid.title = "智能化项目A"
        self.storage.query_results.return_value = ([bid], 1)

        result = asyncio.run(app.get_results(limit=20, offset=0, q="智能化", user={"role": "user"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertNotIn("q", self.storage.query_results.call_args.args[0])

    def test_get_results_q_filters_current_page_without_crashing(self):
        matching = self.make_bid()
        matching.title = "智能化项目A"
        non_matching = self.make_bid()
        non_matching.id = 8
        non_matching.title = "市政项目B"
        non_matching.category = "市政工程"
        non_matching.ai_extracted_data = {"organization": "市政单位", "deadlines": []}
        non_matching.manual_overrides = {"organization": "人工市政单位"}
        self.storage.query_results.return_value = ([matching, non_matching], 2)

        result = asyncio.run(app.get_results(limit=20, offset=0, q="智能化", user={"role": "user"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual([item["id"] for item in result["items"]], [7])

    def test_get_result_detail_returns_ai_manual_and_resolved_data(self):
        bid = self.make_bid()
        self.storage.get_by_id.return_value = bid

        result = asyncio.run(app.get_result_detail(7, user={"role": "user"}))

        self.assertEqual(result["id"], 7)
        self.assertEqual(result["resolved"]["organization"], "人工单位")
        self.assertEqual(result["ai_extracted_data"]["organization"], "AI单位")
        self.assertEqual(result["manual_overrides"]["organization"], "人工单位")

    def test_update_review_validates_not_follow_reason(self):
        self.storage.get_by_id.return_value = self.make_bid()

        with self.assertRaises(app.HTTPException) as ctx:
            asyncio.run(
                app.update_result_review(
                    7,
                    {"follow_decision": "not_follow", "non_follow_reasons": []},
                    user={"role": "user"},
                )
            )

        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_review_saves_valid_payload(self):
        self.storage.get_by_id.return_value = self.make_bid()

        result = asyncio.run(
            app.update_result_review(
                7,
                {"follow_decision": "not_follow", "non_follow_reasons": ["地域问题"], "urgency": "urgent"},
                user={"role": "user"},
            )
        )

        self.assertTrue(result["success"])
        self.storage.update_review.assert_called_once()
        self.assertEqual(self.storage.update_review.call_args.args[0], [7])
        self.assertEqual(self.storage.update_review.call_args.args[1]["urgency_source"], "manual")

    def test_bulk_review_rejects_invalid_batch_atomically(self):
        with self.assertRaises(app.HTTPException):
            asyncio.run(
                app.bulk_update_result_review(
                    {"ids": [1, 2], "update": {"project_stage": "bad"}},
                    user={"role": "user"},
                )
            )
        self.storage.update_review.assert_not_called()

    def test_update_manual_fields_saves_overrides(self):
        bid = self.make_bid()
        bid.manual_overrides = {"organization": "人工单位", "region": "上海"}
        self.storage.get_by_id.return_value = bid

        result = asyncio.run(app.update_result_fields(7, {"organization": "修正单位", "amount": "80"}, user={"role": "user"}))

        self.assertTrue(result["success"])
        self.storage.update_manual_overrides.assert_called_once_with(
            7,
            {"organization": "修正单位", "region": "上海", "amount": "80"},
        )

    def test_update_manual_fields_rejects_nonexistent_result(self):
        self.storage.get_by_id.return_value = None

        with self.assertRaises(app.HTTPException) as ctx:
            asyncio.run(app.update_result_fields(7, {"organization": "修正单位"}, user={"role": "user"}))

        self.assertEqual(ctx.exception.status_code, 404)
        self.storage.update_manual_overrides.assert_not_called()

    def test_update_manual_fields_rejects_unknown_override_keys(self):
        self.storage.get_by_id.return_value = self.make_bid()

        with self.assertRaises(app.HTTPException) as ctx:
            asyncio.run(app.update_result_fields(7, {"unexpected": "value"}, user={"role": "user"}))

        self.assertEqual(ctx.exception.status_code, 400)
        self.storage.update_manual_overrides.assert_not_called()

    def test_result_settings_masks_defaults_and_updates_reasons_for_admin(self):
        settings = asyncio.run(app.get_result_settings(user={"role": "user"}))
        self.assertEqual(settings["non_follow_reason_tags"], ["地域问题", "其它"])
        self.assertIn("urgent", settings["urgencies"])

        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.update_non_follow_reasons({"tags": ["地域问题", "金额不合适"]}, user={"role": "admin"}))

        self.assertTrue(result["success"])
        self.assertEqual(app.app_state.config["non_follow_reason_tags"], ["地域问题", "金额不合适"])
        save_config.assert_called_once_with(app.app_state.config)


if __name__ == "__main__":
    unittest.main()
