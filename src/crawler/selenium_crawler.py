"""向后兼容 shim:实体已迁至 crawler.browser.selenium_backend。"""
from crawler.browser.selenium_backend import (  # noqa: F401
    SeleniumCrawler,
    SharedBrowserManager,
    SELENIUM_AVAILABLE,
    IMPORT_ERROR_MSG,
)
