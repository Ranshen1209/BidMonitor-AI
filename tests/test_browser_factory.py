import os, sys, unittest
from unittest.mock import patch
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from crawler.browser import base_browser
from crawler import browser as browser_pkg


class _Cloak(base_browser.BrowserCrawler):
    def _fetch(self, url): return "<html></html>"
    def close(self): pass

class _Sel(base_browser.BrowserCrawler):
    def _fetch(self, url): return "<html></html>"
    def close(self): pass


class FactoryTests(unittest.TestCase):
    def test_prefers_cloak_when_available(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(_Cloak, _Sel)):
            c = browser_pkg.create_browser_crawler({}, "s", "https://ex.com")
            self.assertIsInstance(c, _Cloak)

    def test_falls_back_to_selenium(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(None, _Sel)):
            c = browser_pkg.create_browser_crawler({}, "s", "https://ex.com")
            self.assertIsInstance(c, _Sel)

    def test_respects_cloakbrowser_disabled_config(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(_Cloak, _Sel)):
            c = browser_pkg.create_browser_crawler(
                {"browser_backend": {"cloakbrowser_enabled": False}},
                "s",
                "https://ex.com",
            )
            self.assertIsInstance(c, _Sel)

    def test_browser_selenium_mode_skips_cloak(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(_Cloak, _Sel)):
            c = browser_pkg.create_browser_crawler(
                {"browser_backend": {"mode": "browser_selenium"}},
                "s",
                "https://ex.com",
            )
            self.assertIsInstance(c, _Sel)

    def test_browser_cloak_mode_does_not_fall_back_to_selenium_when_cloak_missing(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(None, _Sel)):
            c = browser_pkg.create_browser_crawler(
                {"browser_backend": {"mode": "browser_cloak"}},
                "s",
                "https://ex.com",
            )
            self.assertIsNone(c)

    def test_returns_none_when_no_backend(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(None, None)):
            c = browser_pkg.create_browser_crawler({}, "s", "https://ex.com")
            self.assertIsNone(c)

    def test_shutdown_browsers_no_backends(self):
        # neither backend module exists yet; must complete without raising
        browser_pkg.shutdown_browsers()


if __name__ == "__main__":
    unittest.main()
