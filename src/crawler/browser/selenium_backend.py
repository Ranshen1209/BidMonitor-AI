"""Selenium 浏览器后端(降级兜底)。由旧 selenium_crawler.py 迁入并清理。"""
import time
import random
import logging
import threading
from typing import Optional

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
    IMPORT_ERROR_MSG = None
except Exception as e:  # ImportError 及其它初始化异常
    SELENIUM_AVAILABLE = False
    IMPORT_ERROR_MSG = str(e)

from crawler.base import USER_AGENTS
from .base_browser import BrowserCrawler

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
const _gp = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p){
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel Iris OpenGL Engine';
  return _gp.call(this, p);
};
"""


def _build_options(headless: bool) -> "Options":
    """构建 Chrome 选项(单一实现,独立爬虫与共享管理器共用)。"""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    # 注意:不再使用 --single-process(会破坏 CDP 注入并在容器中崩溃)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _create_driver(headless: bool, timeout: int):
    if not SELENIUM_AVAILABLE:
        return None
    options = _build_options(headless)
    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logging.error(f"Chrome 初始化失败: {e}")
            return None
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _STEALTH_JS})
    driver.set_page_load_timeout(timeout)
    return driver


class SharedBrowserManager:
    """共享 Chrome 实例,所有站点复用。"""
    _driver = None
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_driver(cls, timeout: int = 30):
        with cls._lock:
            if cls._driver is None:
                cls._driver = _create_driver(headless=True, timeout=timeout)
                cls._instance = True
            return cls._driver

    @classmethod
    def close(cls):
        if cls._driver:
            try:
                cls._driver.quit()
            except Exception:
                pass
            cls._driver = None
            cls._instance = None


class SeleniumCrawler(BrowserCrawler):
    """Selenium 后端。"""

    def __init__(self, config: dict, name: str, url: str, headless: bool = True):
        super().__init__(config, name, url, headless=headless)
        self.driver = None

    def _fetch(self, url: str) -> Optional[str]:
        if not SELENIUM_AVAILABLE:
            self.logger.error("Selenium 未安装")
            return None
        if not self.driver:
            self.driver = SharedBrowserManager.get_driver(self.timeout)
            if not self.driver:
                self.driver = _create_driver(self.headless, self.timeout)
            if not self.driver:
                return None
        try:
            self.logger.info(f"[Selenium] 访问: {url}")
            self.driver.get(url)
            time.sleep(2)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return self.driver.page_source
        except Exception as e:
            self.logger.warning(f"[Selenium] 取页失败,重置 driver: {e}")
            self.driver = None
            return None

    def close(self) -> None:
        # 仅关闭本爬虫私有的独立 driver;共享 driver 由 SharedBrowserManager.close() 统一关闭
        if self.driver is not None and self.driver is not SharedBrowserManager._driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None
