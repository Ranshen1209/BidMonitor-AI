"""浏览器后端子包:抽象层 + 降级工厂。"""
import logging
from typing import Optional, Tuple, Type

from .base_browser import BrowserCrawler

logger = logging.getLogger("crawler.browser")


def _load_backends() -> Tuple[Optional[Type[BrowserCrawler]], Optional[Type[BrowserCrawler]]]:
    """惰性加载 (CloakBrowserCrawler, SeleniumCrawler);缺库返回 None。"""
    cloak = None
    selenium = None
    try:
        from .cloak_backend import CloakBrowserCrawler, CLOAK_AVAILABLE
        if CLOAK_AVAILABLE:
            cloak = CloakBrowserCrawler
    except ImportError as e:  # pragma: no cover - import 保护
        logger.debug(f"CloakBrowser 后端不可用: {e}")
    try:
        from .selenium_backend import SeleniumCrawler, SELENIUM_AVAILABLE
        if SELENIUM_AVAILABLE:
            selenium = SeleniumCrawler
    except ImportError as e:  # pragma: no cover - import 保护
        logger.debug(f"Selenium 后端不可用: {e}")
    return cloak, selenium


def create_browser_crawler(config: dict, name: str, url: str,
                           headless: bool = True) -> Optional[BrowserCrawler]:
    """按 CloakBrowser → Selenium 顺序返回可用后端实例;都不可用返回 None。"""
    browser_backend = (config or {}).get("browser_backend") or {}
    mode = browser_backend.get("mode")
    cloak_enabled = browser_backend.get("cloakbrowser_enabled", True) is not False
    cloak_cls, selenium_cls = _load_backends()
    if mode == "browser_selenium":
        cloak_enabled = False
    if mode == "browser_cloak":
        selenium_cls = None
    if cloak_cls is not None and cloak_enabled:
        logger.info(f"[browser] 使用 CloakBrowser 后端: {name}")
        return cloak_cls(config, name, url, headless=headless)
    if selenium_cls is not None:
        logger.info(f"[browser] 回落 Selenium 后端: {name}")
        return selenium_cls(config, name, url, headless=headless)
    logger.warning("[browser] 无可用浏览器后端,调用方应回落 requests")
    return None


def shutdown_browsers() -> None:
    """关闭两类共享浏览器,释放资源。"""
    try:
        from .cloak_backend import CloakBrowserManager
        CloakBrowserManager.close()
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[browser] CloakBrowserManager.close() failed: {e}")
    try:
        from .selenium_backend import SharedBrowserManager
        SharedBrowserManager.close()
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[browser] SharedBrowserManager.close() failed: {e}")
