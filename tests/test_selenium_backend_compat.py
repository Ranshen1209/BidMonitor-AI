import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


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


if __name__ == "__main__":
    unittest.main()
