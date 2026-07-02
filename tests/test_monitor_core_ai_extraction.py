import unittest
from unittest.mock import Mock, patch

from src.database.storage import BidInfo, Storage
from src.monitor_core import MonitorCore


class FakeCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "弱电智能化")]


class MonitorCoreAIExtractionTests(unittest.TestCase):
    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_new_saved_bid_triggers_enrichment(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage

        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={"enabled_sites": []},
            ai_config={"enable": False},
        )
        monitor.crawlers = [FakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            result = monitor.run_once()

        self.assertEqual(result["new_count"], 1)
        enrich.assert_called_once()
        self.assertEqual(enrich.call_args.args[1], 123)
