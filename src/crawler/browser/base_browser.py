"""浏览器爬虫抽象基类 - 所有浏览器后端共享 crawl/parse/重试逻辑。"""
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from urllib.parse import urljoin

from crawler.base import BidInfo


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
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
        except ImportError:  # pragma: no cover - exercised in minimal test envs
            from crawler.url_list import _MiniSoup
            soup = _MiniSoup(html)
        bids: List[BidInfo] = []
        today = datetime.now().strftime("%Y-%m-%d")
        seen = set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
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
