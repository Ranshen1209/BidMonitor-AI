import os
import tempfile
import unittest
from unittest.mock import patch

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import monitor_core as monitor_core_module
from monitor_core import MonitorCore
from crawler.url_list import UrlListCrawler
from database.storage import Storage


class MonitorCoreUrlSourcesTests(unittest.TestCase):
    def test_default_sites_are_loaded_from_canonical_url_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "url_sources.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    '{"sources": ['
                    '{"id": "source-a", "name": "源 A", "url": "https://example.com/a", "enabled": true},'
                    '{"id": "source-b", "name": "源 B", "url": "http://example.org/b", "enabled": true},'
                    '{"id": "source-off", "name": "禁用", "url": "https://example.com/off", "enabled": false}'
                    ']}'
                )

            with patch.object(monitor_core_module, "DEFAULT_URL_SOURCES_PATH", path):
                sites = monitor_core_module.get_default_sites()

            self.assertEqual(list(sites.keys()), ["source-a", "source-b"])
            self.assertEqual(sites["source-a"]["name"], "源 A")
            self.assertEqual(sites["source-a"]["url"], "https://example.com/a")
            self.assertEqual(sites["source-b"]["url"], "http://example.org/b")

    def test_legacy_url_list_enabled_sites_are_not_loaded_as_crawlers(self):
        fake_default_sites = {
            "url_list_001": {"name": "旧 URL", "url": "https://old.example.com"}
        }

        with patch.object(monitor_core_module, "get_default_sites", return_value=fake_default_sites):
            monitor = MonitorCore(
                keywords=["弱电"],
                notify_method="none",
                crawler_overrides={
                    "enabled_sites": ["url_list_001"],
                    "use_selenium": False,
                    "csv_url_sources": [],
                },
            )

        self.assertEqual(monitor.crawlers, [])

    def test_monitor_core_loads_enabled_csv_url_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com\n")

            monitor = MonitorCore(
                keywords=["弱电"],
                notify_method="none",
                crawler_overrides={
                    "enabled_sites": [],
                    "use_selenium": False,
                    "csv_url_sources": [
                        {"name": "上海招投标URL清单", "file_path": path, "enabled": True},
                        {"name": "禁用清单", "file_path": path, "enabled": False},
                    ],
                },
            )

            url_crawlers = [crawler for crawler in monitor.crawlers if isinstance(crawler, UrlListCrawler)]
            self.assertEqual(len(url_crawlers), 1)
            self.assertEqual(url_crawlers[0].name, "上海招投标URL清单")
            self.assertEqual(url_crawlers[0].get_list_urls(), ["https://example.com"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_monitor_core_run_once_saves_url_list_results_to_storage(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body><h1>上海弱电公开招标公告</h1><p>综合布线和安防监控项目。</p></body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            db_path = os.path.join(tmpdir, "bids.db")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/detail\n")

            monitor = MonitorCore(
                keywords=["弱电", "公开招标"],
                notify_method="none",
                crawler_overrides={
                    "enabled_sites": [],
                    "use_selenium": False,
                    "csv_url_sources": [
                        {
                            "name": "上海招投标URL清单",
                            "file_path": path,
                            "diagnostics_path": diagnostics_path,
                            "enabled": True,
                        }
                    ],
                },
            )
            monitor.storage = Storage(db_path)

            result = monitor.run_once()
            saved = monitor.storage.get_all()

            self.assertEqual(result["new_count"], 1)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].source, "上海招投标URL清单")
            self.assertEqual(saved[0].url, "https://example.com/detail")
            self.assertIn("original_url: https://example.com/detail", saved[0].content)


if __name__ == "__main__":
    unittest.main()
