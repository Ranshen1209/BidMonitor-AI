import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from src.database.storage import BidInfo, Storage
from src.results.ai_extractor import AIExtractor, build_column_updates, enrich_new_bid, suggest_urgency


class AIExtractorTests(unittest.TestCase):
    def test_responses_payload_and_parse_output_text_json(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "output_text": json.dumps({"organization": "上海某单位", "amount": "30", "deadlines": []}, ensure_ascii=False)
        }

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            data = AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")

        self.assertEqual(data["organization"], "上海某单位")
        url, kwargs = post.call_args
        self.assertEqual(url[0], "https://api.example.com/v1/responses")
        self.assertEqual(kwargs["json"]["model"], "grok-4.20-fast")
        self.assertIn("input", kwargs["json"])
        self.assertNotIn("messages", kwargs["json"])

    def test_chat_completions_payload_and_parse_message_json(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1/chat/completions",
            "api_key": "secret",
            "model": "deepseek-chat",
            "endpoint_type": "chat_completions",
        }
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "```json\n{\"region\":\"上海\",\"deadlines\":[]}\n```"}}]
        }

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            data = AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")

        self.assertEqual(data["region"], "上海")
        self.assertEqual(post.call_args[0][0], "https://api.example.com/v1/chat/completions")
        self.assertIn("messages", post.call_args.kwargs["json"])

    def test_test_connection_uses_responses_endpoint(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }
        response = Mock()
        response.json.return_value = {"output_text": "ok"}

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            result = AIExtractor(config).test_connection("Reply ok")

        self.assertEqual(result, "ok")
        self.assertEqual(post.call_args[0][0], "https://api.example.com/v1/responses")
        self.assertIn("input", post.call_args.kwargs["json"])

    def test_test_connection_uses_chat_completions_endpoint(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1/chat/completions",
            "api_key": "secret",
            "model": "deepseek-chat",
            "endpoint_type": "chat_completions",
        }
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            result = AIExtractor(config).test_connection("Reply ok")

        self.assertEqual(result, "ok")
        self.assertEqual(post.call_args[0][0], "https://api.example.com/v1/chat/completions")
        self.assertIn("messages", post.call_args.kwargs["json"])

    def test_build_column_updates_extracts_three_deadline_columns(self):
        data = {
            "amount": "50",
            "amount_unit": "万元",
            "region": "上海",
            "category": "弱电智能化",
            "project_type": "公开招标",
            "nature": "服务",
            "deadlines": [
                {"type": "registration_deadline", "end_at": "2026-07-03 17:00"},
                {"type": "submission_deadline", "end_at": "2026-07-05 10:00"},
                {"type": "bid_opening_time", "start_at": "2026-07-05 10:30"},
            ],
        }

        columns = build_column_updates(data)

        self.assertEqual(columns["registration_deadline"], "2026-07-03 17:00")
        self.assertEqual(columns["submission_deadline"], "2026-07-05 10:00")
        self.assertEqual(columns["bid_opening_time"], "2026-07-05 10:30")
        self.assertEqual(columns["deadline_source"], "ai")

    def test_build_column_updates_serializes_structured_recommendation(self):
        columns = build_column_updates(
            {
                "ai_recommendation": {
                    "decision": "follow",
                    "reasons": ["上海项目", "智能化"],
                },
                "deadlines": [],
            }
        )

        self.assertEqual(
            columns["ai_recommendation"],
            json.dumps({"decision": "follow", "reasons": ["上海项目", "智能化"]}, ensure_ascii=False),
        )

    def test_suggest_urgency_uses_submission_deadline_first(self):
        data = {
            "deadlines": [
                {"type": "registration_deadline", "end_at": "2026-07-20 17:00"},
                {"type": "submission_deadline", "end_at": "2026-07-04 10:00"},
            ]
        }

        suggestion = suggest_urgency(data, now=datetime(2026, 7, 2, 9, 0))

        self.assertEqual(suggestion["urgency"], "urgent")
        self.assertEqual(suggestion["urgency_source"], "auto")
        self.assertEqual(suggestion["urgency_reference_type"], "submission")

    def test_invalid_json_raises_value_error(self):
        config = {"enable": True, "base_url": "https://api.example.com/v1", "api_key": "secret", "model": "grok", "endpoint_type": "responses"}
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"output_text": "not json"}

        with patch("src.results.ai_extractor.requests.post", return_value=response):
            with self.assertRaises(ValueError):
                AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")

    def test_enrich_new_bid_preserves_manual_urgency(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        storage = Storage(os.path.join(tmpdir.name, "bids.db"))
        bid = BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "摘要")
        result_id = storage.save(bid)
        storage.update_review(
            [result_id],
            {
                "urgency": "low",
                "urgency_source": "manual",
                "urgency_reference_time": "2026-07-20 17:00",
                "urgency_reference_type": "registration",
            },
        )
        ai_data = {
            "region": "上海",
            "deadlines": [
                {"type": "submission_deadline", "end_at": "2026-07-04 10:00"},
            ],
        }

        with patch("src.results.ai_extractor.fetch_detail_text", return_value=(True, "详情", None)):
            with patch.object(AIExtractor, "extract", return_value=ai_data):
                enrich_new_bid(
                    storage,
                    result_id,
                    bid,
                    {"enable": True, "api_key": "secret", "model": "grok"},
                )

        updated = storage.get_by_id(result_id)
        self.assertEqual(updated.ai_extract_status, "extracted")
        self.assertEqual(updated.region, "上海")
        self.assertEqual(updated.urgency, "low")
        self.assertEqual(updated.urgency_source, "manual")
        self.assertEqual(updated.urgency_reference_time, "2026-07-20 17:00")
        self.assertEqual(updated.urgency_reference_type, "registration")

    def test_enrich_new_bid_marks_ai_status_when_detail_fetch_fails(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        storage = Storage(os.path.join(tmpdir.name, "bids.db"))
        bid = BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "摘要")
        result_id = storage.save(bid)

        with patch("src.results.ai_extractor.fetch_detail_text", return_value=(False, "", "detail timeout")):
            enrich_new_bid(
                storage,
                result_id,
                bid,
                {"enable": True, "api_key": "secret", "model": "grok"},
            )

        updated = storage.get_by_id(result_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.detail_fetch_status, "failed")
        self.assertEqual(updated.ai_extract_status, "detail_fetch_failed")
        self.assertEqual(updated.ai_extract_error, "detail timeout")
