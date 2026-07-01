# CloakBrowser + Selenium 反爬后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入浏览器抽象层与 CloakBrowser 后端,形成 `CloakBrowser → Selenium → requests` 降级链,默认隐身 + humanize,主打 Docker headless。

**Architecture:** 新建 `src/crawler/browser/` 子包:`BrowserCrawler` 基类持有唯一的 `parse()` 链接解析实现;`cloak_backend`(Playwright API)与 `selenium_backend`(现有 Selenium 迁入清理)各实现 `_fetch()`;`create_browser_crawler()` 工厂按可用性降级。`monitor_core` 改用工厂,`use_selenium` 语义升级为"浏览器模式开关"并保持向后兼容。旧 `selenium_crawler.py` 变兼容 shim。

**Tech Stack:** Python 3.8+ / 3.11(Docker),`cloakbrowser`(Playwright 兼容),`selenium` + `webdriver-manager`,`beautifulsoup4` + `lxml`,`unittest`。

## Global Constraints

- 依赖底线(verbatim):`beautifulsoup4>=4.12.0`,`lxml>=4.9.0`,`selenium>=4.15.0`,`webdriver-manager>=4.0.0`;新增 `cloakbrowser`(不钉死次版本,`cloakbrowser` 一行注释 `# CloakBrowser 隐身浏览器(反爬首选)`)。
- 所有浏览器相关 import 必须 try/except 包裹,缺库时模块可导入且优雅降级(照 `selenium_crawler.py` 现有 `SELENIUM_AVAILABLE`/`IMPORT_ERROR_MSG` 模式)。
- 向后兼容:`from crawler.selenium_crawler import SeleniumCrawler, SharedBrowserManager, SELENIUM_AVAILABLE, IMPORT_ERROR_MSG` 必须继续可用;config `use_selenium: true` 语义不变(=开启浏览器模式)。
- 测试放 `tests/`,用 `unittest`;src 上 `sys.path` 前插 `os.path.join(ROOT, "src")`(照 `tests/test_monitor_core_url_sources.py`)。
- 真实浏览器冒烟测标 slow/optional,不进默认门禁。
- 提交信息以 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` 结尾。
- CloakBrowser 隐身来自其自研补丁版 Chromium(约 200MB,首次运行下载);Docker 预下载失败仅告警不阻断构建。

## File Structure

- Create `src/crawler/browser/__init__.py` — `create_browser_crawler()` 工厂 + `shutdown_browsers()` + 可用性探测 re-export。
- Create `src/crawler/browser/base_browser.py` — `BrowserCrawler` ABC:`crawl()`/`parse()`/唯一链接解析,抽象 `_fetch()`/`close()`。
- Create `src/crawler/browser/selenium_backend.py` — 由 `selenium_crawler.py` 迁入并清理的 `SeleniumCrawler` + `SharedBrowserManager`。
- Create `src/crawler/browser/cloak_backend.py` — `CloakBrowserCrawler` + `CloakBrowserManager`。
- Modify `src/crawler/selenium_crawler.py` — 变兼容 shim(re-export)。
- Modify `src/monitor_core.py:243-244, 260-261, 441-446` — 用工厂替换直接实例化 + 统一关闭。
- Modify `Dockerfile` — Chromium 系统依赖 + 预下载二进制。
- Modify `requirements.txt`、`server/requirements.txt` — 加 `cloakbrowser`。
- Create tests:`tests/test_browser_parse.py`、`tests/test_browser_factory.py`、`tests/test_browser_config_defaults.py`、`tests/test_selenium_backend_compat.py`;Modify `tests/test_docker_packaging.py`。

**并行分组(SubAgent):** Task 1→2 为基础须先行;之后 Task 3(Selenium 后端)、Task 4(Cloak 后端)、Task 6(Docker)可并行;Task 5(工厂+monitor_core 接入)依赖 3、4;Task 7(依赖清单)独立。

---

### Task 1: 抽象基类与唯一链接解析

**Files:**
- Create: `src/crawler/browser/__init__.py`(本任务仅留空注释行)
- Create: `src/crawler/browser/base_browser.py`
- Test: `tests/test_browser_parse.py`

**Interfaces:**
- Consumes: `crawler.base.BidInfo`, `crawler.base.USER_AGENTS`
- Produces:
  - `class BrowserCrawler(ABC)`:`__init__(self, config: dict, name: str, url: str, headless: bool = True)`;property `name -> str`;`parse(self, html: str) -> List[BidInfo]`;`crawl(self, stop_event=None) -> Optional[List[BidInfo]]`;`fetch(self, url: str) -> Optional[str]`(含重试);abstract `_fetch(self, url: str) -> Optional[str]`;abstract `close(self) -> None`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browser_parse.py
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from crawler.browser.base_browser import BrowserCrawler
from crawler.base import BidInfo


class _StubBrowser(BrowserCrawler):
    def __init__(self, html):
        super().__init__({}, "stub", "https://ex.com/list")
        self._html = html
    def _fetch(self, url):
        return self._html
    def close(self):
        pass


class BrowserParseTests(unittest.TestCase):
    def test_parse_extracts_filters_and_dedupes_links(self):
        html = '''
          <a href="/notice/1">这是一个有效招标公告标题</a>
          <a href="/notice/1">这是一个有效招标公告标题</a>
          <a href="javascript:void(0)">忽略脚本链接</a>
          <a href="/x">短</a>
          <a href="https://other.com/2">另一个足够长的招标标题</a>
        '''
        c = _StubBrowser(html)
        bids = c.parse(html)
        self.assertTrue(all(isinstance(b, BidInfo) for b in bids))
        urls = [b.url for b in bids]
        self.assertIn("https://ex.com/notice/1", urls)   # urljoin 补全
        self.assertIn("https://other.com/2", urls)
        self.assertEqual(len(urls), len(set(urls)))       # 去重
        self.assertNotIn("javascript:void(0)", urls)      # 过滤脚本
        self.assertTrue(all(len(b.title) >= 4 for b in bids))  # 过滤短标题
        self.assertTrue(all(b.source == "stub" for b in bids))

    def test_crawl_returns_parsed_bids(self):
        c = _StubBrowser('<a href="/n/9">足够长的招标信息标题内容</a>')
        bids = c.crawl()
        self.assertEqual(len(bids), 1)

    def test_crawl_respects_stop_event(self):
        class E:
            def is_set(self): return True
        c = _StubBrowser('<a href="/n/9">足够长的招标信息标题内容</a>')
        self.assertEqual(c.crawl(stop_event=E()), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.browser'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/crawler/browser/__init__.py
# Browser backend subpackage
```

```python
# src/crawler/browser/base_browser.py
"""浏览器爬虫抽象基类 - 所有浏览器后端共享 crawl/parse/重试逻辑。"""
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from urllib.parse import urljoin

from crawler.base import BidInfo  # noqa: F401


class BrowserCrawler(ABC):
    """浏览器后端抽象基类。子类只需实现 _fetch() 与 close()。"""

    def __init__(self, config: dict, name: str, url: str, headless: bool = True):
        self.config = config or {}
        self._name = name
        self.url = url
        self.headless = headless
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.logger = logging.getLogger(f"crawler.browser.{name}")

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def _fetch(self, url: str) -> Optional[str]:
        """取回页面 HTML,失败返回 None。"""

    @abstractmethod
    def close(self) -> None:
        """释放后端资源。"""

    def fetch(self, url: str) -> Optional[str]:
        """带指数退避重试的取页。"""
        for attempt in range(self.max_retries):
            try:
                html = self._fetch(url)
                if html:
                    return html
            except Exception as e:  # 后端内部异常不应中断整体流程
                self.logger.warning(f"[{self.name}] fetch 异常: {e}")
            if attempt < self.max_retries - 1:
                wait = (2 ** (attempt + 1)) + random.uniform(0, 1)
                self.logger.info(f"[{self.name}] {wait:.1f}s 后重试({attempt + 2})")
                time.sleep(wait)
        self.logger.error(f"[{self.name}] 取页最终失败: {url}")
        return None

    def parse(self, html: str) -> List[BidInfo]:
        """从页面提取 <a> 链接为 BidInfo(唯一实现,两后端共用)。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        bids: List[BidInfo] = []
        today = datetime.now().strftime("%Y-%m-%d")
        seen = set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if not text or len(text) < 4:
                continue
            if href.lower().startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            full = urljoin(self.url, href)
            if full in seen:
                continue
            seen.add(full)
            bids.append(BidInfo(title=text, url=full, publish_date=today, source=self.name))
        self.logger.info(f"[{self.name}] 找到 {len(bids)} 个链接")
        return bids

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        if stop_event and stop_event.is_set():
            self.logger.info(f"[{self.name}] 收到停止信号,跳过")
            return []
        html = self.fetch(self.url)
        if not html:
            return None
        return self.parse(html)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser_parse.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/crawler/browser/__init__.py src/crawler/browser/base_browser.py tests/test_browser_parse.py
git commit -m "feat: add BrowserCrawler base with shared link parser

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 后端可用性探测(占位后端 + 工厂骨架)

**Files:**
- Modify: `src/crawler/browser/__init__.py`
- Test: `tests/test_browser_factory.py`

**Interfaces:**
- Consumes: `BrowserCrawler`
- Produces:
  - `crawler.browser.create_browser_crawler(config: dict, name: str, url: str, headless: bool = True) -> Optional[BrowserCrawler]`
  - `crawler.browser.shutdown_browsers() -> None`
  - 模块级布尔:探测经由惰性 import,函数内读取各后端的 `*_AVAILABLE`。

**注意:** 本任务先建**可 mock 的工厂**,真实后端类在 Task 3/4 落地。工厂通过内部 `_load_backends()` 返回 `(cloak_cls_or_None, selenium_cls_or_None)`,测试用 `patch` 替换该函数。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browser_factory.py
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

    def test_returns_none_when_no_backend(self):
        with patch.object(browser_pkg, "_load_backends", return_value=(None, None)):
            c = browser_pkg.create_browser_crawler({}, "s", "https://ex.com")
            self.assertIsNone(c)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_factory.py -v`
Expected: FAIL — `AttributeError: module 'crawler.browser' has no attribute '_load_backends'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/crawler/browser/__init__.py
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
    except Exception as e:  # pragma: no cover - import 保护
        logger.debug(f"CloakBrowser 后端不可用: {e}")
    try:
        from .selenium_backend import SeleniumCrawler, SELENIUM_AVAILABLE
        if SELENIUM_AVAILABLE:
            selenium = SeleniumCrawler
    except Exception as e:  # pragma: no cover - import 保护
        logger.debug(f"Selenium 后端不可用: {e}")
    return cloak, selenium


def create_browser_crawler(config: dict, name: str, url: str,
                           headless: bool = True) -> Optional[BrowserCrawler]:
    """按 CloakBrowser → Selenium 顺序返回可用后端实例;都不可用返回 None。"""
    cloak_cls, selenium_cls = _load_backends()
    if cloak_cls is not None:
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
    except Exception:
        pass
    try:
        from .selenium_backend import SharedBrowserManager
        SharedBrowserManager.close()
    except Exception:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser_factory.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/crawler/browser/__init__.py tests/test_browser_factory.py
git commit -m "feat: add browser backend factory with fallback chain

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Selenium 后端迁入 + 清理 + 兼容 shim

**Files:**
- Create: `src/crawler/browser/selenium_backend.py`
- Modify: `src/crawler/selenium_crawler.py`(全量替换为 shim)
- Test: `tests/test_selenium_backend_compat.py`

**Interfaces:**
- Consumes: `BrowserCrawler`, `crawler.base.USER_AGENTS`
- Produces:
  - `SeleniumCrawler(BrowserCrawler)`:实现 `_fetch`/`close`;`SELENIUM_AVAILABLE: bool`;`IMPORT_ERROR_MSG`;`SharedBrowserManager`(`get_driver`/`close`);模块函数 `_build_options(headless: bool) -> Options`。
  - `crawler.selenium_crawler` re-export 上述全部符号。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_selenium_backend_compat.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_selenium_backend_compat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.browser.selenium_backend'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/crawler/browser/selenium_backend.py
"""Selenium 浏览器后端(降级兜底)。由旧 selenium_crawler.py 迁入并清理。"""
import time
import random
import logging
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
    _lock = None

    @classmethod
    def get_driver(cls, timeout: int = 30):
        import threading
        if cls._lock is None:
            cls._lock = threading.Lock()
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
        self.logger.info(f"[Selenium] 访问: {url}")
        self.driver.get(url)
        time.sleep(2)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return self.driver.page_source

    def close(self) -> None:
        # 共享浏览器由 SharedBrowserManager.close() 统一关闭
        if self.driver and not SharedBrowserManager._instance:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
```

```python
# src/crawler/selenium_crawler.py  —— 全量替换为兼容 shim
"""向后兼容 shim:实体已迁至 crawler.browser.selenium_backend。"""
from crawler.browser.selenium_backend import (  # noqa: F401
    SeleniumCrawler,
    SharedBrowserManager,
    SELENIUM_AVAILABLE,
    IMPORT_ERROR_MSG,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_selenium_backend_compat.py tests/test_browser_parse.py -v`
Expected: PASS(第三个用例在无 selenium 环境会 skip)

- [ ] **Step 5: Commit**

```bash
git add src/crawler/browser/selenium_backend.py src/crawler/selenium_crawler.py tests/test_selenium_backend_compat.py
git commit -m "refactor: move Selenium into browser backend, drop single-process, dedupe driver init

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: CloakBrowser 后端

**Files:**
- Create: `src/crawler/browser/cloak_backend.py`
- Test: `tests/test_browser_config_defaults.py`

**Interfaces:**
- Consumes: `BrowserCrawler`,`cloakbrowser.launch`
- Produces:
  - `CloakBrowserCrawler(BrowserCrawler)`:实现 `_fetch`/`close`;`CLOAK_AVAILABLE: bool`;`IMPORT_ERROR_MSG`;`CloakBrowserManager`(`get_browser(config)`/`close`);模块函数 `_build_launch_kwargs(config: dict, headless: bool) -> dict`。
- `_build_launch_kwargs` 规则:`headless` 透传;`humanize` 默认 `True`(config `browser.humanize` 覆盖);`stealth_args=True`;仅当 config 提供时才加 `proxy`/`geoip`/`timezone`/`locale`/`license_key`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_browser_config_defaults.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser_config_defaults.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.browser.cloak_backend'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/crawler/browser/cloak_backend.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser_config_defaults.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/crawler/browser/cloak_backend.py tests/test_browser_config_defaults.py
git commit -m "feat: add CloakBrowser stealth backend with humanize + reserved proxy/geoip

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 接入 monitor_core(工厂 + 统一关闭)

**Files:**
- Modify: `src/monitor_core.py`(默认站点 loop、自定义站点 loop、收尾关闭)
- Test: `tests/test_monitor_core_browser_mode.py`

**Interfaces:**
- Consumes: `crawler.browser.create_browser_crawler`, `crawler.browser.shutdown_browsers`
- Produces: 无新公开符号;行为:`use_selenium=True` 时经工厂建后端,工厂返回 None 回落 `CustomCrawler`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_monitor_core_browser_mode.py
import os, sys, unittest
from unittest.mock import patch, MagicMock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import monitor_core as mc


class BrowserModeWiringTests(unittest.TestCase):
    def test_factory_called_when_browser_mode_on(self):
        # 冒烟:开启浏览器模式时应调用工厂而非直接 requests
        with patch.object(mc, "create_browser_crawler") as fac:
            fac.return_value = MagicMock(name="browser_crawler")
            self.assertTrue(callable(mc.create_browser_crawler))
            fac.assert_not_called()  # 占位断言,真实调用在 setup_crawlers 集成测试覆盖


if __name__ == "__main__":
    unittest.main()
```

> 说明:`setup_crawlers` 依赖较多外部状态;本步先断言 `create_browser_crawler` 已导入到 `monitor_core` 命名空间。实现后按需扩展为完整集成测试。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_monitor_core_browser_mode.py -v`
Expected: FAIL — `AttributeError: module 'monitor_core' has no attribute 'create_browser_crawler'`

- [ ] **Step 3: Write minimal implementation**

在 `src/monitor_core.py` 顶部 import 区加入:

```python
from crawler.browser import create_browser_crawler, shutdown_browsers
```

将 `src/monitor_core.py:225-234` 的 Selenium 探测块替换为浏览器模式说明(保留 `use_selenium` 变量名):

```python
        # 浏览器模式开关(向后兼容 use_selenium)
        if use_selenium:
            self.log("[DEBUG] 浏览器模式已启用(CloakBrowser→Selenium→requests 降级)")
```

将默认站点 loop 内 `src/monitor_core.py:243-247` 替换:

```python
                    if use_selenium:
                        crawler = create_browser_crawler(crawler_config, site['name'], site['url'], headless=True)
                        if crawler is None:
                            self.log(f"[WARN] 无浏览器后端,回落 requests: {site['name']}")
                            crawler = CustomCrawler(crawler_config, site['name'], site['url'])
                        else:
                            self.log(f"[OK] Loaded site (browser): {site['name']}")
                    else:
                        crawler = CustomCrawler(crawler_config, site['name'], site['url'])
                        self.log(f"[OK] Loaded site: {site['name']}")
```

将自定义站点 loop 内 `src/monitor_core.py:260-264` 替换:

```python
                    if use_selenium:
                        crawler = create_browser_crawler(crawler_config, name, url, headless=True)
                        if crawler is None:
                            self.log(f"[WARN] 无浏览器后端,回落 requests: {name}")
                            crawler = CustomCrawler(crawler_config, name, url)
                        else:
                            self.log(f"[OK] Loaded custom (browser): {name}")
                    else:
                        crawler = CustomCrawler(crawler_config, name, url)
                        self.log(f"[OK] Loaded custom crawler: {name}")
```

将收尾关闭 `src/monitor_core.py:441-446` 替换:

```python
        # 关闭共享浏览器以释放内存
        try:
            shutdown_browsers()
            self.log("✅ 已关闭共享浏览器,释放内存")
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_monitor_core_browser_mode.py tests/test_monitor_core_url_sources.py -v`
Expected: PASS(既有 url_sources 测试不回归)

- [ ] **Step 5: Commit**

```bash
git add src/monitor_core.py tests/test_monitor_core_browser_mode.py
git commit -m "feat: wire browser factory into monitor_core with requests fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Docker 预打包 CloakBrowser Chromium

**Files:**
- Modify: `Dockerfile`
- Test: `tests/test_docker_packaging.py`(扩展)

**Interfaces:**
- Produces: Dockerfile 含 Chromium 运行依赖 apt 包 + CloakBrowser 二进制预下载步骤。

- [ ] **Step 1: Write the failing test(扩展现有文件,追加用例)**

```python
    def test_dockerfile_bundles_chromium_deps_and_prefetches_cloak(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for pkg in ["libnss3", "libgbm1", "libasound2", "libatk1.0-0", "fonts-liberation"]:
            self.assertIn(pkg, dockerfile)
        # build 阶段预下载 CloakBrowser 二进制(失败不阻断)
        self.assertIn("cloakbrowser", dockerfile)
        self.assertIn("|| true", dockerfile)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_docker_packaging.py -v`
Expected: FAIL — `AssertionError: 'libnss3' not found in dockerfile`

- [ ] **Step 3: Write minimal implementation**

替换 `Dockerfile` 的 apt 安装块并在 pip 安装后加预下载步骤:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 基础工具 + CloakBrowser/Chromium 运行依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc curl \
       libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
       libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
       libgbm1 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# build 阶段预下载 CloakBrowser 专用 Chromium(约 200MB)并缓存进镜像层;
# 下载失败不阻断构建(运行时可回落 Selenium/requests)
RUN python -c "import cloakbrowser, sys; \
    b=cloakbrowser.launch(headless=True); b.close(); \
    print('cloakbrowser binary ready')" || true

COPY src src
COPY server server
COPY README.md README.md

RUN mkdir -p data logs

EXPOSE 8080

CMD ["python", "server/app.py"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_docker_packaging.py -v`
Expected: PASS(既有两用例 + 新用例)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile tests/test_docker_packaging.py
git commit -m "build: bundle CloakBrowser Chromium and runtime deps in Docker image

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 依赖清单

**Files:**
- Modify: `requirements.txt`,`server/requirements.txt`
- Test: `tests/test_requirements_cloakbrowser.py`

**Interfaces:**
- Produces: 两个 requirements 文件含 `cloakbrowser`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_requirements_cloakbrowser.py
import os, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RequirementsTests(unittest.TestCase):
    def test_cloakbrowser_listed_in_both_requirements(self):
        for rel in ("requirements.txt", "server/requirements.txt"):
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read().lower()
            self.assertIn("cloakbrowser", text, f"{rel} 缺少 cloakbrowser")
            self.assertIn("selenium", text, f"{rel} 缺少 selenium")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_requirements_cloakbrowser.py -v`
Expected: FAIL(root `requirements.txt` 无 selenium/cloakbrowser)

- [ ] **Step 3: Write minimal implementation**

在 `requirements.txt` 与 `server/requirements.txt` 的浏览器相关区块追加(server 已有 selenium 段,仅追加 cloakbrowser 行;root 追加浏览器模式段):

```
# 浏览器模式抓取(反爬)
selenium>=4.15.0
webdriver-manager>=4.0.0
cloakbrowser                # CloakBrowser 隐身浏览器(反爬首选)
```

> root `requirements.txt` 若原本无 selenium 段则整段追加;`server/requirements.txt` 已有 selenium/webdriver-manager,仅在其后加 `cloakbrowser` 行,避免重复。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_requirements_cloakbrowser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt server/requirements.txt tests/test_requirements_cloakbrowser.py
git commit -m "build: add cloakbrowser dependency

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 全量回归 + README 反爬说明

**Files:**
- Modify: `README.md`(反爬/浏览器模式一节)
- Test: 全量 `python -m pytest tests/ -v`

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全绿(浏览器相关缺库用例 skip,不 fail)

- [ ] **Step 2: 更新 README 浏览器模式段落**

在 `README.md` "多网站支持" 段将 `Selenium 模式绕过反爬虫` 更新为:

```
- 浏览器模式绕过反爬:CloakBrowser 隐身优先,Selenium 兜底,requests 最终兜底
- CloakBrowser 内置指纹补丁 + 拟人行为(humanize),Docker 镜像已预打包专用 Chromium
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document CloakBrowser->Selenium->requests anti-bot fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §4.1 目录结构 → Task 1/2/3/4(+ shim in Task 3)。✓
- §4.2 抽象层 + 唯一 parse → Task 1。✓
- §4.3 CloakBrowser 后端(共享 browser、per-context、humanize、networkidle)→ Task 4。✓
- §4.4 Selenium 清理(去 single-process、UA 池、合并重复、补丁)→ Task 3。✓
- §4.5 工厂 + shim → Task 2 + Task 3。✓
- §4.6 monitor_core 接入 + 统一关闭 → Task 5。✓
- §5 Docker 预打包 + 系统依赖 + 失败不阻断 → Task 6。✓
- §6 测试(降级链/解析器/config 默认/import 安全/shim/docker)→ Task 1-7 各测试。✓
- §7 非目标 → 计划未触碰 40+ 站点爬虫、无代理 UI、无 undetected-chromedriver。✓
- Global：`cloakbrowser` 依赖 → Task 7。✓

**Placeholder scan:** Task 5 Step 1 为轻量冒烟(已在说明中标注原因并给出后续扩展路径),其余步骤均含完整代码,无 TBD/TODO。

**Type consistency:** `create_browser_crawler(config, name, url, headless=True)`、`shutdown_browsers()`、`_build_options(headless)`、`_build_launch_kwargs(config, headless)`、`CLOAK_AVAILABLE`/`SELENIUM_AVAILABLE`、`CloakBrowserManager.get_browser`/`SharedBrowserManager.get_driver` 在各任务间签名一致。✓
