import os, sys, threading, unittest
from unittest.mock import MagicMock, patch
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from crawler.browser import cloak_backend as cb


class CloakLaunchKwargsTests(unittest.TestCase):
    def test_defaults_humanize_on_and_no_optional_keys(self):
        kw = cb._build_launch_kwargs({}, headless=True)
        self.assertTrue(kw["headless"])
        self.assertTrue(kw["humanize"])
        self.assertTrue(kw["stealth_args"])
        for k in ("proxy", "geoip", "timezone", "locale", "license_key"):
            self.assertNotIn(k, kw)

    def test_optional_keys_passed_when_configured(self):
        cfg = {"browser": {"humanize": False, "proxy": "http://u:p@h:8080",
                            "geoip": True, "timezone": "Asia/Shanghai",
                            "locale": "zh-CN", "license_key": "abc"}}
        kw = cb._build_launch_kwargs(cfg, headless=False)
        self.assertFalse(kw["headless"])
        self.assertFalse(kw["humanize"])
        self.assertEqual(kw["proxy"], "http://u:p@h:8080")
        self.assertTrue(kw["geoip"])
        self.assertEqual(kw["timezone"], "Asia/Shanghai")
        self.assertEqual(kw["locale"], "zh-CN")
        self.assertEqual(kw["license_key"], "abc")

    def test_empty_or_none_optional_keys_excluded(self):
        cfg = {"browser": {"proxy": "", "license_key": None, "timezone": ""}}
        kw = cb._build_launch_kwargs(cfg, headless=True)
        self.assertNotIn("proxy", kw)
        self.assertNotIn("license_key", kw)
        self.assertNotIn("timezone", kw)


class CloakBrowserManagerThreadTests(unittest.TestCase):
    def tearDown(self):
        # Reset shared class state so tests do not bleed into each other
        cb.CloakBrowserManager._browser = None
        cb.CloakBrowserManager._owner_thread = None

    def test_manager_recreates_browser_on_thread_change(self):
        browser1 = MagicMock()
        browser2 = MagicMock()
        side_effects = [browser1, browser2]

        def _factory(**kwargs):
            return side_effects.pop(0)

        with patch.object(cb, "CLOAK_AVAILABLE", True), \
             patch.object(cb, "_cloak_launch", side_effect=_factory):
            # First call — browser created on current thread
            result1 = cb.CloakBrowserManager.get_browser({})
            self.assertIs(result1, browser1)

            # Simulate a thread change by spoofing _owner_thread
            cb.CloakBrowserManager._owner_thread = threading.get_ident() + 1

            # Second call — should close browser1 and recreate
            result2 = cb.CloakBrowserManager.get_browser({})
            self.assertIs(result2, browser2)
            self.assertIsNot(result2, browser1)
            browser1.close.assert_called_once()

    def test_manager_reuses_browser_same_thread(self):
        browser1 = MagicMock()
        launch_mock = MagicMock(return_value=browser1)

        with patch.object(cb, "CLOAK_AVAILABLE", True), \
             patch.object(cb, "_cloak_launch", launch_mock):
            result1 = cb.CloakBrowserManager.get_browser({})
            result2 = cb.CloakBrowserManager.get_browser({})
            self.assertIs(result1, result2)
            launch_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
