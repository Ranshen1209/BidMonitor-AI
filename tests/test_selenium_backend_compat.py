import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
from pathlib import Path
from unittest.mock import MagicMock, patch


class SeleniumBackendCompatTests(unittest.TestCase):
    def test_backend_module_exports_symbols(self):
        from crawler.browser import selenium_backend as sb
        self.assertTrue(hasattr(sb, "SeleniumCrawler"))
        self.assertTrue(hasattr(sb, "SharedBrowserManager"))
        self.assertIn("SELENIUM_AVAILABLE", dir(sb))
        self.assertIn("IMPORT_ERROR_MSG", dir(sb))

    def test_legacy_shim_reexports(self):
        # 向后兼容:旧路径仍可导入
        from crawler.selenium_crawler import (
            SeleniumCrawler, SharedBrowserManager,
            SELENIUM_AVAILABLE, IMPORT_ERROR_MSG,
        )
        from crawler.browser.selenium_backend import SeleniumCrawler as NewCls
        self.assertIs(SeleniumCrawler, NewCls)

    def test_build_options_has_no_single_process(self):
        from crawler.browser import selenium_backend as sb
        if not sb.SELENIUM_AVAILABLE:
            self.skipTest("selenium 未安装")
        opts = sb._build_options(headless=True)
        args = " ".join(opts.arguments)
        self.assertNotIn("--single-process", args)
        self.assertIn("--headless", args)

    def test_build_options_uses_project_local_chrome_when_present(self):
        from crawler.browser import selenium_backend as sb

        class FakeOptions:
            def __init__(self):
                self.arguments = []
                self.binary_location = ""

            def add_argument(self, value):
                self.arguments.append(value)

            def add_experimental_option(self, name, value):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            chrome = Path(tmp) / ".browser-binaries" / "selenium" / "chrome"
            chrome.parent.mkdir(parents=True)
            chrome.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch.dict(os.environ, {"BIDMONITOR_BROWSER_BINARIES": str(Path(tmp) / ".browser-binaries")}, clear=True):
                with patch.object(sb, "Options", FakeOptions, create=True):
                    opts = sb._build_options(headless=True)
        self.assertEqual(opts.binary_location, str(chrome))

    def test_create_driver_uses_project_local_chromedriver_when_present(self):
        from crawler.browser import selenium_backend as sb

        class FakeService:
            def __init__(self, path):
                self.path = path

        class FakeDriverFactory:
            def __init__(self, driver):
                self.driver = driver
                self.call_args = None

            def Chrome(self, **kwargs):
                self.call_args = kwargs
                return self.driver

        with tempfile.TemporaryDirectory() as tmp:
            driver_path = Path(tmp) / ".browser-binaries" / "selenium" / "chromedriver"
            driver_path.parent.mkdir(parents=True)
            driver_path.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_driver = MagicMock()
            fake_webdriver = FakeDriverFactory(fake_driver)
            with patch.dict(os.environ, {"BIDMONITOR_BROWSER_BINARIES": str(Path(tmp) / ".browser-binaries")}, clear=True), \
                 patch.object(sb, "SELENIUM_AVAILABLE", True), \
                 patch.object(sb, "Service", FakeService, create=True), \
                 patch.object(sb, "webdriver", fake_webdriver, create=True), \
                 patch.object(sb, "_build_options", return_value=object()):
                result = sb._create_driver(headless=True, timeout=7)

        self.assertIs(result, fake_driver)
        service = fake_webdriver.call_args["service"]
        self.assertEqual(service.path, str(driver_path))


if __name__ == "__main__":
    unittest.main()
