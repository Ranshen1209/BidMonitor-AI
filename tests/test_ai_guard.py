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

    def test_string_false_relevant_value_is_treated_as_false(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"relevant": "false", "reason": "纯平台推广页"}, ensure_ascii=False)
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

        with patch("requests.post", return_value=response):
            relevant, reason = AIGuard(config).check_relevance("平台首页", "招标采购平台介绍")

        self.assertFalse(relevant)
        self.assertEqual(reason, "纯平台推广页")

    def test_non_json_negative_text_checks_not_relevant_before_relevant(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "不相关：这是新闻资讯，不是招标公告"}}]
        }
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", return_value=response):
            relevant, reason = AIGuard(config).check_relevance("行业新闻", "智慧楼宇趋势")

        self.assertFalse(relevant)
        self.assertIn("不相关", reason)

    def test_ambiguous_non_json_response_returns_unknown_reason(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": "模型输出无法判断"}}]}
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", return_value=response):
            relevant, reason = AIGuard(config).check_relevance("平台首页", "欢迎访问")

        self.assertFalse(relevant)
        self.assertIn("AI结果未知", reason)

    def test_ambiguous_non_json_response_containing_relevant_word_returns_unknown_reason(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": "无法判断是否相关"}}]}
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", return_value=response):
            relevant, reason = AIGuard(config).check_relevance("平台首页", "欢迎访问")

        self.assertFalse(relevant)
        self.assertIn("AI结果未知", reason)

    def test_non_json_negated_positive_words_return_not_relevant(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        for ai_content in ["不值得跟进：不是招标公告", "不太符合业务方向", "没有必要跟进"]:
            with self.subTest(ai_content=ai_content):
                response = Mock()
                response.status_code = 200
                response.json.return_value = {"choices": [{"message": {"content": ai_content}}]}

                with patch("requests.post", return_value=response):
                    relevant, reason = AIGuard(config).check_relevance("行业新闻", "智慧楼宇趋势")

                self.assertFalse(relevant)
                self.assertEqual(reason, ai_content)

    def test_clear_positive_non_json_response_returns_relevant(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        for ai_content in [
            "相关",
            "是相关",
            "该项目相关",
            "相关：明确是视频监控采购公告",
            "值得跟进",
            "符合业务方向",
        ]:
            with self.subTest(ai_content=ai_content):
                response = Mock()
                response.status_code = 200
                response.json.return_value = {"choices": [{"message": {"content": ai_content}}]}

                with patch("requests.post", return_value=response):
                    relevant, reason = AIGuard(config).check_relevance("视频监控采购公告", "公开招标")

                self.assertTrue(relevant)
                self.assertEqual(reason, ai_content)

    def test_network_error_returns_unknown_when_ai_enabled(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", side_effect=Exception("boom")):
            relevant, reason = AIGuard(config).check_relevance("智能化公开招标", "视频监控")

        self.assertFalse(relevant)
        self.assertIn("AI请求异常", reason)

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
