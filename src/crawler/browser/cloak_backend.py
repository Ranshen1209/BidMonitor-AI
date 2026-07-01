"""CloakBrowser 隐身浏览器后端(反爬首选)。"""
import time
import logging
from typing import Optional

try:
    from cloakbrowser import launch as _cloak_launch
    CLOAK_AVAILABLE = True
    IMPORT_ERROR_MSG = None
except Exception as e:
    CLOAK_AVAILABLE = False
    IMPORT_ERROR_MSG = str(e)
    _cloak_launch = None

from .base_browser import BrowserCrawler


def _build_launch_kwargs(config: dict, headless: bool) -> dict:
    """从 config 组装 cloakbrowser.launch 参数。仅传显式提供的可选项。"""
    bcfg = (config or {}).get("browser", {}) or {}
    kwargs = {
        "headless": headless,
        "humanize": bcfg.get("humanize", True),
        "stealth_args": True,
    }
    for key in ("proxy", "geoip", "timezone", "locale", "license_key"):
        if key in bcfg and bcfg[key] not in (None, ""):
            kwargs[key] = bcfg[key]
    return kwargs


class CloakBrowserManager:
    """共享 CloakBrowser(Playwright Browser)实例。"""
    _browser = None
    _lock = None

    @classmethod
    def get_browser(cls, config: dict, headless: bool = True):
        import threading
        if cls._lock is None:
            cls._lock = threading.Lock()
        with cls._lock:
            if cls._browser is None and CLOAK_AVAILABLE:
                try:
                    cls._browser = _cloak_launch(**_build_launch_kwargs(config, headless))
                except Exception as e:
                    logging.error(f"CloakBrowser 启动失败: {e}")
                    cls._browser = None
            return cls._browser

    @classmethod
    def close(cls):
        if cls._browser:
            try:
                cls._browser.close()
            except Exception:
                pass
            cls._browser = None


class CloakBrowserCrawler(BrowserCrawler):
    """CloakBrowser 后端。每站点独立 context,复用同一 browser 进程。"""

    def _fetch(self, url: str) -> Optional[str]:
        if not CLOAK_AVAILABLE:
            self.logger.error("cloakbrowser 未安装")
            return None
        browser = CloakBrowserManager.get_browser(self.config, self.headless)
        if browser is None:
            return None
        context = browser.new_context()
        try:
            page = context.new_page()
            self.logger.info(f"[Cloak] 访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # networkidle 超时容忍
            time.sleep(1)  # 拟人小延时
            return page.content()
        finally:
            try:
                context.close()
            except Exception:
                pass

    def close(self) -> None:
        # 共享 browser 由 CloakBrowserManager.close() 统一关闭
        pass
