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
from crawler.source_crawler import SourceBackedCrawler
from crawler.url_list import UrlListCrawler
from database.storage import BidInfo, Storage


class FakeCrawler:
    name = "FakeCrawler"

    def __init__(self, bids):
        self.bids = bids

    def crawl(self, stop_event=None):
        return self.bids


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

    def test_monitor_core_builds_source_backed_crawler_for_json_sources_filtered_by_enabled_sites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                f.write(
                    '{"sources": ['
                    '{"id": "source-a", "name": "源 A", "url": "https://example.com/a", "enabled": true},'
                    '{"id": "source-b", "name": "源 B", "url": "https://example.com/b", "enabled": true}'
                    ']}'
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                f.write('{"sites": [{"id": "source-a"}, {"id": "source-b"}]}')

            monitor = MonitorCore(
                keywords=["弱电"],
                notify_method="none",
                crawler_overrides={
                    "enabled_sites": ["source-a"],
                    "use_selenium": False,
                    "site_topologies_path": topologies_path,
                    "csv_url_sources": [
                        {
                            "name": "JSON sources",
                            "file_path": sources_path,
                            "source_type": "json",
                            "enabled": True,
                        }
                    ],
                },
            )

            source_crawlers = [
                crawler for crawler in monitor.crawlers if isinstance(crawler, SourceBackedCrawler)
            ]
            self.assertEqual(len(source_crawlers), 1)
            self.assertEqual([source.id for source in source_crawlers[0].sources], ["source-a"])

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

    @patch.object(monitor_core_module, "enrich_new_bid")
    def test_monitor_core_updates_crawl_run_inserted_and_skipped_counts(self, mock_enrich):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            try:
                run_id = storage.start_crawl_run("source-a", "Source A")
                bid = BidInfo(
                    title="上海弱电公开招标公告",
                    url="https://example.com/source-a/1",
                    publish_date="2026-07-03",
                    source="Source A",
                    content="综合布线和安防监控项目。",
                    crawl_run_id=run_id,
                    source_id="source-a",
                )
                monitor = MonitorCore(
                    keywords=["弱电"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": [],
                        "use_selenium": False,
                        "csv_url_sources": [],
                    },
                )
                monitor.storage = storage
                monitor.crawlers = [FakeCrawler([bid])]

                result = monitor.run_once()
                run = storage.get_crawl_run(run_id)
            finally:
                storage.close()

        self.assertEqual(result["new_count"], 1)
        self.assertEqual(run["inserted_count"], 1)
        self.assertEqual(run["skipped_count"], 0)
        mock_enrich.assert_called_once()

    @patch.object(monitor_core_module, "enrich_new_bid")
    def test_monitor_core_updates_crawl_run_skipped_count_for_duplicate_bid(self, mock_enrich):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            try:
                existing_bid = BidInfo(
                    title="上海弱电公开招标公告",
                    url="https://example.com/source-a/1",
                    publish_date="2026-07-03",
                    source="Source A",
                    content="综合布线和安防监控项目。",
                )
                storage.save(existing_bid, notified=False)
                run_id = storage.start_crawl_run("source-a", "Source A")
                duplicate_bid = BidInfo(
                    title=existing_bid.title,
                    url=existing_bid.url,
                    publish_date=existing_bid.publish_date,
                    source=existing_bid.source,
                    content=existing_bid.content,
                    crawl_run_id=run_id,
                    source_id="source-a",
                )
                monitor = MonitorCore(
                    keywords=["弱电"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": [],
                        "use_selenium": False,
                        "csv_url_sources": [],
                    },
                )
                monitor.storage = storage
                monitor.crawlers = [FakeCrawler([duplicate_bid])]

                result = monitor.run_once()
                run = storage.get_crawl_run(run_id)
            finally:
                storage.close()

        self.assertEqual(result["new_count"], 0)
        self.assertEqual(run["inserted_count"], 0)
        self.assertEqual(run["skipped_count"], 1)
        mock_enrich.assert_not_called()


if __name__ == "__main__":
    unittest.main()
