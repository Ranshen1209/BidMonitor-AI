import os, sys, unittest
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


if __name__ == "__main__":
    unittest.main()
