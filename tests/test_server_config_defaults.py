import os
import json
import tempfile
import unittest
from unittest.mock import patch
import asyncio
import inspect

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import app


class ServerConfigDefaultsTests(unittest.TestCase):
    def test_app_logs_strip_visual_emoji_icons(self):
        original_logs = app.app_state.logs
        try:
            app.app_state.logs = []

            app.app_state.add_log("✅ AI测试成功，⏰ 下次检索时间: 17:03:28")

            self.assertEqual(len(app.app_state.logs), 1)
            self.assertIn("AI测试成功", app.app_state.logs[0])
            self.assertIn("下次检索时间: 17:03:28", app.app_state.logs[0])
            self.assertNotIn("✅", app.app_state.logs[0])
            self.assertNotIn("⏰", app.app_state.logs[0])
        finally:
            app.app_state.logs = original_logs

    def test_default_config_targets_shanghai_url_list_first(self):
        with patch.object(app.os.path, "exists", return_value=False):
            config = app.load_config()

        self.assertIn("弱电", config["keywords"])
        self.assertIn("智能化", config["keywords"])
        self.assertEqual(config["must_contain"], "")
        self.assertFalse(config["use_selenium"])
        self.assertEqual(config["enabled_sites"], [])
        self.assertEqual(config["csv_url_sources"][0]["name"], "上海招投标URL清单")
        self.assertTrue(config["csv_url_sources"][0]["enabled"])
        self.assertTrue(config["csv_url_sources"][0]["file_path"].endswith("bid_related_url_list.txt"))
        self.assertEqual(config["csv_url_sources"][0]["domain_delay"], 2)
        self.assertEqual(config["csv_url_sources"][0]["auth_cookies"], [])
        self.assertEqual(config["browser_backend"]["mode"], "http")
        self.assertFalse(config["browser_backend"]["cloakbrowser_enabled"])
        self.assertEqual(config["site_metadata"], {})
        self.assertIn("non_follow_reason_tags", config)
        self.assertIn("地域问题", config["non_follow_reason_tags"])
        self.assertEqual(config["ai_config"]["base_url"], "https://api.sakrylle.com/v1")
        self.assertEqual(config["ai_config"]["model"], "grok-4.20-fast")
        self.assertEqual(config["ai_config"]["endpoint_type"], "responses")
        self.assertNotIn("custom_sites", config)

    def test_browser_backend_config_keeps_anti_crawler_boundary_explicit(self):
        with patch.object(app.os.path, "exists", return_value=False):
            config = app.load_config()

        serialized = json.dumps(config["browser_backend"], ensure_ascii=False).lower()
        self.assertIn("授权 cookie", config["browser_backend"]["note"].lower())
        self.assertIn("人工验证码", config["browser_backend"]["note"])
        self.assertNotIn("proxy", serialized)
        self.assertNotIn("stealth", serialized)
        self.assertNotIn("bypass", serialized)

    def test_sites_api_uses_bid_related_url_list_as_builtin_sites(self):
        sites = app.get_default_sites()

        self.assertEqual(len(sites), 30)
        self.assertIn("url_list_001", sites)
        self.assertEqual(sites["url_list_001"]["url"], "http://www.qianlima.com/")
        self.assertEqual(sites["url_list_030"]["url"], "https://sxtsrm.sngbs.com.cn/epoint-sso/default/login_bidder?display=bidder&response_type=code&redirect_uri=https%3A%2F%2Fsxtsrm.sngbs.com.cn%2Ftpbidder%2Fdefault%2Flogin_auto%3Ftimestamp%3D1761792220671&state=ba11004e-49ec-4c24-be5c-b09bcac4b354&code_challenge_method=S256&client_id=98c4cd51-bb2b-4f6d-afc2-998badd9e586&code_challenge=73E4B098310F270722DD315BCA6263786A36025F4CBC8C7CCC34B441DFDF11B6")
        self.assertNotIn("dlzb", sites)
        self.assertNotIn("powerchina", sites)

    def test_load_config_backfills_url_source_cookie_and_rate_limit_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "server_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "csv_url_sources": [
                            {
                                "name": "上海招投标URL清单",
                                "file_path": app.DEFAULT_URL_LIST_PATH,
                                "enabled": True,
                            }
                        ]
                    },
                    f,
                )

            with patch.object(app, "CONFIG_FILE", config_path):
                config = app.load_config()

        source = config["csv_url_sources"][0]
        self.assertEqual(source["domain_delay"], 2)
        self.assertEqual(source["auth_cookies"], [])

    def test_load_config_backfills_site_metadata_defaults(self):
        normalized = app.normalize_config({"enabled_sites": []})

        self.assertEqual(normalized["site_metadata"], {})

    def test_get_config_masks_ai_key(self):
        app.app_state.config = app.normalize_config(
            {
                "ai_config": {
                    "api_key": "secret",
                    "base_url": "https://api.example.com/v1",
                    "model": "grok-4.20-fast",
                    "endpoint_type": "responses",
                }
            }
        )

        config = asyncio.run(app.get_config(user={"role": "user"}))

        self.assertEqual(config["ai_config"]["api_key"], "***")

    def test_get_config_masks_all_secret_bearing_values(self):
        app.app_state.config = app.normalize_config(
            {
                "sms_config": {
                    "provider": "aliyun",
                    "access_key_id": "sms-id",
                    "access_key_secret": "sms-secret",
                },
                "voice_config": {
                    "provider": "aliyun",
                    "access_key_id": "voice-id",
                    "access_key_secret": "voice-secret",
                },
                "ai_config": {
                    "api_key": "ai-secret",
                    "endpoint_type": "responses",
                },
                "wechat_config": {
                    "provider": "pushplus",
                    "token": "wechat-secret",
                },
                "email_configs": [
                    {
                        "sender": "alerts@example.com",
                        "password": "email-secret",
                        "smtp_server": "smtp.example.com",
                    }
                ],
                "contacts": [
                    {
                        "name": "Alice",
                        "email": "alice@example.com",
                        "email_password": "contact-email-secret",
                        "wechat_token": "contact-wechat-secret",
                    }
                ],
                "custom_nested": {
                    "display_name": "Nested Display",
                    "service_token": "nested-token-secret",
                    "metadata": {
                        "api_key": "nested-api-secret",
                        "access_key_id": "public-id",
                    },
                },
            }
        )

        config = asyncio.run(app.get_config(user={"role": "user"}))

        self.assertEqual(config["sms_config"]["access_key_secret"], "***")
        self.assertEqual(config["voice_config"]["access_key_secret"], "***")
        self.assertEqual(config["ai_config"]["api_key"], "***")
        self.assertEqual(config["wechat_config"]["token"], "***")
        self.assertEqual(config["email_configs"][0]["password"], "***")
        self.assertEqual(config["email_configs"][0]["sender"], "alerts@example.com")
        self.assertEqual(config["contacts"][0]["email_password"], "***")
        self.assertEqual(config["contacts"][0]["wechat_token"], "***")
        self.assertEqual(config["contacts"][0]["name"], "Alice")
        self.assertEqual(config["contacts"][0]["email"], "alice@example.com")
        self.assertEqual(config["custom_nested"]["service_token"], "***")
        self.assertEqual(config["custom_nested"]["metadata"]["api_key"], "***")
        self.assertEqual(config["custom_nested"]["metadata"]["access_key_id"], "public-id")
        self.assertEqual(app.app_state.config["wechat_config"]["token"], "wechat-secret")
        self.assertEqual(app.app_state.config["contacts"][0]["wechat_token"], "contact-wechat-secret")

    def test_get_contacts_masks_secret_bearing_values_without_mutating_config(self):
        app.app_state.config = app.normalize_config(
            {
                "contacts": [
                    {
                        "name": "Alice",
                        "email": "alice@example.com",
                        "email_password": "contact-email-secret",
                        "wechat_token": "contact-wechat-secret",
                    }
                ],
            }
        )

        contacts = asyncio.run(app.get_contacts(user={"role": "user"}))

        self.assertEqual(contacts[0]["email_password"], "***")
        self.assertEqual(contacts[0]["wechat_token"], "***")
        self.assertEqual(contacts[0]["name"], "Alice")
        self.assertEqual(app.app_state.config["contacts"][0]["email_password"], "contact-email-secret")
        self.assertEqual(app.app_state.config["contacts"][0]["wechat_token"], "contact-wechat-secret")

    def test_normalize_config_infers_chat_endpoint_type_for_legacy_chat_base_url(self):
        config = app.normalize_config(
            {
                "ai_config": {
                    "base_url": "https://api.deepseek.com/chat/completions",
                    "api_key": "secret",
                    "model": "deepseek-chat",
                }
            }
        )

        self.assertEqual(config["ai_config"]["endpoint_type"], "chat_completions")

    def test_update_full_config_preserves_masked_secrets(self):
        app.app_state.config = app.normalize_config(
            {
                "sms_config": {
                    "provider": "aliyun",
                    "access_key_id": "sms-id",
                    "access_key_secret": "sms-secret",
                },
                "voice_config": {
                    "provider": "aliyun",
                    "access_key_id": "voice-id",
                    "access_key_secret": "voice-secret",
                },
                "ai_config": {
                    "api_key": "ai-secret",
                    "endpoint_type": "responses",
                },
                "wechat_config": {
                    "provider": "pushplus",
                    "token": "wechat-secret",
                },
                "email_configs": [
                    {
                        "sender": "alerts@example.com",
                        "password": "email-secret",
                    }
                ],
                "contacts": [
                    {
                        "name": "Alice",
                        "email": "alice@example.com",
                        "email_password": "contact-email-secret",
                        "wechat_token": "contact-wechat-secret",
                    }
                ],
            }
        )

        payload = app.normalize_config(
            {
                "sms_config": {
                    "provider": "aliyun",
                    "access_key_id": "sms-id",
                    "access_key_secret": "***",
                },
                "voice_config": {
                    "provider": "aliyun",
                    "access_key_id": "voice-id",
                    "access_key_secret": "",
                },
                "ai_config": {
                    "api_key": "***",
                    "endpoint_type": "responses",
                },
                "wechat_config": {
                    "provider": "pushplus",
                    "token": "***",
                },
                "email_configs": [
                    {
                        "sender": "alerts@example.com",
                        "password": "***",
                    }
                ],
                "contacts": [
                    {
                        "name": "Alice",
                        "email": "alice@example.com",
                        "email_password": "",
                        "wechat_token": "***",
                    }
                ],
            }
        )

        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.update_full_config(payload, user={"role": "user"}))

        self.assertTrue(result["success"])
        self.assertEqual(app.app_state.config["sms_config"]["access_key_secret"], "sms-secret")
        self.assertEqual(app.app_state.config["voice_config"]["access_key_secret"], "voice-secret")
        self.assertEqual(app.app_state.config["ai_config"]["api_key"], "ai-secret")
        self.assertEqual(app.app_state.config["wechat_config"]["token"], "wechat-secret")
        self.assertEqual(app.app_state.config["email_configs"][0]["password"], "email-secret")
        self.assertEqual(app.app_state.config["contacts"][0]["email_password"], "contact-email-secret")
        self.assertEqual(app.app_state.config["contacts"][0]["wechat_token"], "contact-wechat-secret")
        save_config.assert_called_once_with(app.app_state.config)

    def test_get_sites_merges_metadata_and_returns_full_shape(self):
        app.app_state.config = {
            "enabled_sites": ["url_list_001"],
            "site_metadata": {
                "url_list_001": {
                    "display_name": "上海政府采购",
                    "access_status": "public_no_antibot",
                    "requires_login": False,
                    "has_antibot": False,
                    "note": "可公开访问",
                    "last_checked_at": "2026-07-01T10:00:00+08:00",
                    "last_diagnostic": "HTTP 200",
                    "unexpected": "drop me",
                }
            },
        }

        sites = asyncio.run(app.get_sites(user={"role": "user"}))
        first = sites[0]

        self.assertEqual(first["key"], "url_list_001")
        self.assertEqual(first["name"], "上海招投标URL 001")
        self.assertEqual(first["display_name"], "上海政府采购")
        self.assertEqual(first["url"], "http://www.qianlima.com/")
        self.assertTrue(first["enabled"])
        self.assertEqual(first["access_status"], "public_no_antibot")
        self.assertFalse(first["requires_login"])
        self.assertFalse(first["has_antibot"])
        self.assertEqual(first["note"], "可公开访问")
        self.assertEqual(first["last_checked_at"], "2026-07-01T10:00:00+08:00")
        self.assertEqual(first["last_diagnostic"], "HTTP 200")
        self.assertNotIn("unexpected", first)

    def test_update_sites_accepts_legacy_string_list(self):
        app.app_state.config = {"enabled_sites": [], "site_metadata": {"url_list_001": {"note": "keep"}}}

        with patch.object(app, "save_config") as save_config:
            response = asyncio.run(app.update_sites(["url_list_001"], user={"role": "admin"}))

        self.assertTrue(response["success"])
        self.assertEqual(app.app_state.config["enabled_sites"], ["url_list_001"])
        self.assertEqual(app.app_state.config["site_metadata"], {"url_list_001": {"note": "keep"}})
        save_config.assert_called_once_with(app.app_state.config)

    def test_update_sites_accepts_metadata_payload_and_filters_fields(self):
        app.app_state.config = {"enabled_sites": [], "site_metadata": {}}
        payload = {
            "sites": [
                {
                    "key": "url_list_001",
                    "enabled": True,
                    "display_name": "上海政府采购",
                    "access_status": "public_no_antibot",
                    "requires_login": False,
                    "has_antibot": False,
                    "note": "可公开访问",
                    "last_checked_at": "2026-07-01T10:00:00+08:00",
                    "last_diagnostic": "HTTP 200",
                    "url": "https://evil.example",
                    "name": "should not save",
                },
                {
                    "key": "url_list_002",
                    "enabled": False,
                    "note": "暂不启用",
                },
            ]
        }

        with patch.object(app, "save_config") as save_config:
            response = asyncio.run(app.update_sites(payload, user={"role": "admin"}))

        self.assertTrue(response["success"])
        self.assertEqual(app.app_state.config["enabled_sites"], ["url_list_001"])
        self.assertEqual(
            app.app_state.config["site_metadata"],
            {
                "url_list_001": {
                    "display_name": "上海政府采购",
                    "access_status": "public_no_antibot",
                    "requires_login": False,
                    "has_antibot": False,
                    "note": "可公开访问",
                    "last_checked_at": "2026-07-01T10:00:00+08:00",
                    "last_diagnostic": "HTTP 200",
                },
                "url_list_002": {
                    "note": "暂不启用",
                },
            },
        )
        save_config.assert_called_once_with(app.app_state.config)

    def test_update_sites_declares_payload_as_request_body(self):
        signature = inspect.signature(app.update_sites)

        self.assertIsNot(signature.parameters["payload"].default, inspect._empty)


if __name__ == "__main__":
    unittest.main()
