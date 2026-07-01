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
