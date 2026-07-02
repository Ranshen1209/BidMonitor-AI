import json
import unittest
from unittest.mock import Mock, patch

from src.ai_guard import AIGuard


class AIGuardTests(unittest.TestCase):
    def test_chat_completions_config_appends_endpoint_and_disables_streaming(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"relevant": True, "reason": "匹配智能化项目"}, ensure_ascii=False)
                    }
                }
            ]
        }
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", return_value=response) as post:
            relevant, reason = AIGuard(config).check_relevance("智能化公开招标", "视频监控")

        self.assertTrue(relevant)
        self.assertEqual(reason, "匹配智能化项目")
        self.assertEqual(post.call_args.args[0], "https://api.example.com/v1/chat/completions")
        self.assertIs(post.call_args.kwargs["json"]["stream"], False)

    def test_responses_config_parses_output_text(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "output_text": json.dumps({"relevant": False, "reason": "地域不匹配"}, ensure_ascii=False)
        }
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }

        with patch("requests.post", return_value=response) as post:
            relevant, reason = AIGuard(config).check_relevance("湖南项目", "报告厅装修")

        self.assertFalse(relevant)
        self.assertEqual(reason, "地域不匹配")
        self.assertEqual(post.call_args.args[0], "https://api.example.com/v1/responses")
        self.assertIn("input", post.call_args.kwargs["json"])

    def test_default_prompt_uses_configured_business_keywords_not_legacy_drone_domain(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"relevant": True, "reason": "关键词匹配"})}}]
        }
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
            "filter_keywords": ["弱电智能化", "视频监控"],
            "must_contain_keywords": ["招标公告"],
            "exclude_keywords": ["大疆"],
        }

        with patch("requests.post", return_value=response) as post:
            AIGuard(config).check_relevance("视频监控招标公告", "弱电智能化")

        messages = post.call_args.kwargs["json"]["messages"]
        system_prompt = messages[0]["content"]
        self.assertIn("弱电智能化", system_prompt)
        self.assertIn("视频监控", system_prompt)
        self.assertIn("招标公告", system_prompt)
        self.assertIn("大疆", system_prompt)
        self.assertNotIn("无人机", system_prompt)
