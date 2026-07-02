"""
Tests for browser factory wiring in MonitorCore._init_crawlers.

Tests assert the fallback chain:
  create_browser_crawler (factory) → CustomCrawler (when factory returns None)
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import monitor_core as mc
from monitor_core import MonitorCore
from crawler.custom import CustomCrawler


class BrowserModeWiringTests(unittest.TestCase):
    """Tests that MonitorCore uses the browser factory and falls back to CustomCrawler."""

    def test_factory_result_used_when_available(self):
        """When create_browser_crawler returns a sentinel, it should appear in crawlers."""
        sentinel = MagicMock(name="browser_crawler")

        custom_sites = [{"name": "TestSite", "url": "https://example.com"}]

        with patch.object(mc, "get_default_sites", return_value={}):
            with patch.object(mc, "create_browser_crawler", return_value=sentinel) as mock_factory:
                monitor = MonitorCore(
                    keywords=["test"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": [],
                        "use_selenium": True,
                        "custom_sites": custom_sites,
                    },
                )

        # The factory should have been called once for the custom site
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args
        # Verify url and name were passed
        args = call_kwargs[0]  # positional args: (config, name, url)
        self.assertEqual(args[1], "TestSite")
        self.assertEqual(args[2], "https://example.com")

        # The sentinel should be in the crawlers list
        self.assertIn(sentinel, monitor.crawlers)

    def test_falls_back_to_custom_when_factory_returns_none(self):
        """When create_browser_crawler returns None, a CustomCrawler should be created."""
        custom_sites = [{"name": "FallbackSite", "url": "https://fallback.example.com"}]

        with patch.object(mc, "get_default_sites", return_value={}):
            with patch.object(mc, "create_browser_crawler", return_value=None):
                monitor = MonitorCore(
                    keywords=["test"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": [],
                        "use_selenium": True,
                        "custom_sites": custom_sites,
                    },
                )

        # Should have fallen back to CustomCrawler
        self.assertEqual(len(monitor.crawlers), 1)
        self.assertIsInstance(monitor.crawlers[0], CustomCrawler)
        self.assertEqual(monitor.crawlers[0].name, "FallbackSite")
        self.assertEqual(monitor.crawlers[0].url, "https://fallback.example.com")

    def test_factory_used_for_default_sites(self):
        """When use_selenium=True and a default site is enabled, the factory is called for it."""
        sentinel = MagicMock(name="browser_crawler_default")

        fake_default_sites = {
            "url_list_001": {"name": "上海招投标URL 001", "url": "https://default.example.com"}
        }

        with patch.object(mc, "get_default_sites", return_value=fake_default_sites):
            with patch.object(mc, "create_browser_crawler", return_value=sentinel) as mock_factory:
                monitor = MonitorCore(
                    keywords=["test"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": ["url_list_001"],
                        "use_selenium": True,
                    },
                )

        mock_factory.assert_called_once()
        args = mock_factory.call_args[0]
        self.assertEqual(args[1], "上海招投标URL 001")
        self.assertEqual(args[2], "https://default.example.com")
        self.assertIn(sentinel, monitor.crawlers)

    def test_default_sites_fall_back_to_custom_when_factory_returns_none(self):
        """Default-sites loop: factory returns None -> CustomCrawler for that site."""
        fake_default_sites = {
            "url_list_001": {"name": "上海招投标URL 001", "url": "https://default.example.com"}
        }

        with patch.object(mc, "get_default_sites", return_value=fake_default_sites):
            with patch.object(mc, "create_browser_crawler", return_value=None):
                monitor = MonitorCore(
                    keywords=["test"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": ["url_list_001"],
                        "use_selenium": True,
                    },
                )

        self.assertEqual(len(monitor.crawlers), 1)
        self.assertIsInstance(monitor.crawlers[0], CustomCrawler)
        self.assertEqual(monitor.crawlers[0].name, "上海招投标URL 001")
        self.assertEqual(monitor.crawlers[0].url, "https://default.example.com")

    def test_factory_not_called_when_selenium_disabled(self):
        """When use_selenium=False, factory should NOT be called; CustomCrawler used directly."""
        custom_sites = [{"name": "NoBrowserSite", "url": "https://nobrowser.example.com"}]

        with patch.object(mc, "get_default_sites", return_value={}):
            with patch.object(mc, "create_browser_crawler") as mock_factory:
                monitor = MonitorCore(
                    keywords=["test"],
                    notify_method="none",
                    crawler_overrides={
                        "enabled_sites": [],
                        "use_selenium": False,
                        "custom_sites": custom_sites,
                    },
                )

        mock_factory.assert_not_called()
        self.assertEqual(len(monitor.crawlers), 1)
        self.assertIsInstance(monitor.crawlers[0], CustomCrawler)


if __name__ == "__main__":
    unittest.main()
