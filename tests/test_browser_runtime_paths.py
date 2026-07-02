import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BrowserRuntimePathTests(unittest.TestCase):
    def test_configure_uses_project_local_browser_binary_cache(self):
        from crawler.browser import runtime_paths

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            bundle = runtime_paths.configure_browser_binary_environment(Path(tmp))

            expected_root = Path(tmp) / ".browser-binaries"
            self.assertEqual(bundle.root, expected_root)
            self.assertEqual(bundle.cloakbrowser, expected_root / "cloakbrowser")
            self.assertEqual(bundle.playwright, expected_root / "playwright")
            self.assertEqual(bundle.webdriver_manager, expected_root / "webdriver-manager")
            self.assertEqual(bundle.selenium, expected_root / "selenium")
            self.assertEqual(os.environ["BIDMONITOR_BROWSER_BINARIES"], str(expected_root))
            self.assertEqual(os.environ["CLOAKBROWSER_CACHE_DIR"], str(expected_root / "cloakbrowser"))
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(expected_root / "playwright"))
            self.assertTrue(bundle.cloakbrowser.is_dir())
            self.assertTrue(bundle.playwright.is_dir())
            self.assertTrue(bundle.webdriver_manager.is_dir())
            self.assertTrue(bundle.selenium.is_dir())

    def test_explicit_browser_binary_root_overrides_default(self):
        from crawler.browser import runtime_paths

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as override:
            with patch.dict(os.environ, {"BIDMONITOR_BROWSER_BINARIES": override}, clear=True):
                bundle = runtime_paths.configure_browser_binary_environment(Path(tmp))
                self.assertEqual(
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"],
                    str(Path(override) / "playwright"),
                )
                self.assertEqual(
                    os.environ["CLOAKBROWSER_CACHE_DIR"],
                    str(Path(override) / "cloakbrowser"),
                )

            self.assertEqual(bundle.root, Path(override))

    def test_existing_playwright_path_is_respected(self):
        from crawler.browser import runtime_paths

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as existing:
            with patch.dict(
                os.environ,
                {"PLAYWRIGHT_BROWSERS_PATH": existing},
                clear=True,
            ):
                bundle = runtime_paths.configure_browser_binary_environment(Path(tmp))
                self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], existing)

            self.assertEqual(bundle.playwright, Path(existing))

    def test_existing_cloakbrowser_cache_is_respected(self):
        from crawler.browser import runtime_paths

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as existing:
            with patch.dict(
                os.environ,
                {"CLOAKBROWSER_CACHE_DIR": existing},
                clear=True,
            ):
                bundle = runtime_paths.configure_browser_binary_environment(Path(tmp))
                self.assertEqual(os.environ["CLOAKBROWSER_CACHE_DIR"], existing)

            self.assertEqual(bundle.cloakbrowser, Path(existing))

    def test_finds_project_local_selenium_binaries(self):
        from crawler.browser import runtime_paths

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            bundle = runtime_paths.configure_browser_binary_environment(Path(tmp))
            chrome = bundle.selenium / "chrome"
            driver = bundle.selenium / "chromedriver"
            chrome.write_text("#!/bin/sh\n", encoding="utf-8")
            driver.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(runtime_paths.find_selenium_chrome_binary(Path(tmp)), chrome)
            self.assertEqual(runtime_paths.find_chromedriver_binary(Path(tmp)), driver)


if __name__ == "__main__":
    unittest.main()
