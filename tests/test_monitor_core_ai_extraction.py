import unittest
from unittest.mock import Mock, patch

from src.database.storage import BidInfo, Storage
from src.monitor_core import MonitorCore


class FakeCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "弱电智能化")]


class NonMatchingFakeCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("普通办公用品采购", "https://example.com/b", "2026-07-01", "源", "办公耗材")]


class AiOnlyOpportunityCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("消防维保服务采购公告", "https://example.com/c", "2026-07-01", "源", "消防设施维护")]


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

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_crawled_bid_is_saved_even_when_keywords_do_not_match(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage

        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={"enabled_sites": []},
            ai_config={"enable": False},
        )
        monitor.crawlers = [NonMatchingFakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            result = monitor.run_once()

        self.assertEqual(result["new_count"], 1)
        storage.save.assert_called_once()
        enrich.assert_called_once()
        storage.mark_notified.assert_called_once()

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_ai_rejection_marks_review_but_does_not_block_storage(self, _sites, _classes, storage_cls):
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
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (False, "不符合当前业务方向")

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            result = monitor.run_once()

        self.assertEqual(result["new_count"], 1)
        storage.save.assert_called_once()
        enrich.assert_called_once()
        storage.mark_notified.assert_called_once()
        storage.update_review.assert_called_once_with(
            [123],
            {"fit_status": "not_fit", "review_notes": "AI初判: 不符合当前业务方向"},
        )

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_enrichment_receives_browser_fetch_config(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage

        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "use_selenium": True,
                "browser_backend": {"mode": "browser_auto"},
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [FakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            monitor.run_once()

        self.assertTrue(enrich.call_args.kwargs["fetch_config"]["use_selenium"])
        self.assertEqual(enrich.call_args.kwargs["fetch_config"]["browser_backend"]["mode"], "browser_auto")

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_ai_only_policy_notifies_ai_relevant_without_keyword_match(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "notification_policy": "keyword_or_ai",
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [AiOnlyOpportunityCrawler()]
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (True, "边界机会")

        with patch("src.monitor_core.enrich_new_bid"):
            result = monitor.run_once()

        self.assertEqual(result["matched_count"], 1)
        storage.mark_notified.assert_not_called()

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_strict_policy_does_not_notify_on_ai_error(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "notification_policy": "strict_keyword_and_ai",
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [FakeCrawler()]
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (False, "AI请求异常: boom")

        with patch("src.monitor_core.enrich_new_bid"):
            result = monitor.run_once()

        self.assertEqual(result["matched_count"], 0)
        storage.mark_notified.assert_called_once()
