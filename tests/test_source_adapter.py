import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_adapter import TopologySourceAdapter
from crawler.source_models import Notice, NoticeDeduplicator, Source


def make_source():
    return Source(
        id="portal",
        name="Portal",
        url="https://portal.example.com/",
        topology={
            "id": "portal",
            "name": "Portal",
            "entry_url": "https://portal.example.com/",
            "allowed_hosts": ["portal.example.com"],
            "seed_urls": ["https://portal.example.com/notices/"],
            "list_url_regex": [r"/notices/?$"],
            "detail_url_regex": [r"/detail/42$"],
        },
    )


class TopologySourceAdapterTests(unittest.TestCase):
    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_admits_structured_json_record_without_detail_fetch(self, mock_request_url):
        payload = {
            "data": {
                "records": [
                    {
                        "title": "上海智能化设备采购意向",
                        "detailUrl": "/api/detail/1",
                        "publishDate": "2026-07-01",
                        "purchaser": "上海采购人",
                        "content": "本项目采购弱电智能化系统",
                    }
                ]
            }
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].title, "上海智能化设备采购意向")
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/api/detail/1")
        self.assertEqual(result.notices[0].publish_date, "2026-07-01")
        self.assertEqual(result.notices[0].purchaser, "上海采购人")
        self.assertIn("本项目采购弱电智能化系统", result.notices[0].content)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_preserves_missing_structured_publish_date_as_empty(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                    "content": "本项目采购弱电智能化系统",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].publish_date, "")

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_structured_json_record_without_explicit_url(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "publishDate": "2026-07-01",
                    "purchaser": "上海采购人",
                    "content": "本项目采购弱电智能化系统",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.notices, [])
        self.assertEqual(result.parsed_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_structured_json_record_without_raw_evidence(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.notices, [])
        self.assertEqual(result.parsed_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_initial_structured_json_record_does_not_fetch_detail_url(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                    "publishDate": "2026-07-01",
                    "purchaser": "上海采购人",
                    "content": "本项目采购弱电智能化系统",
                }
            ]
        }
        requested_urls = []

        def fake_request(url):
            requested_urls.append(url)
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            if url == "https://portal.example.com/api/detail/1":
                raise AssertionError("structured JSON detail URL should not be fetched")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.error_count, 0)
        self.assertEqual(len(result.notices), 1)
        self.assertNotIn("https://portal.example.com/api/detail/1", requested_urls)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_admits_structured_json_record_from_topology_seed_api(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = ["https://portal.example.com/api/notices"]
        source.topology["list_url_regex"] = [r"/api/notices$"]
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                    "publishDate": "2026-07-01",
                    "purchaser": "上海采购人",
                    "content": "本项目采购弱电智能化系统",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body><a href='/api/notices'>API notices</a></body></html>", 200, "OK"
            if url == "https://portal.example.com/api/notices":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            if url == "https://portal.example.com/api/detail/1":
                raise AssertionError("structured API detail URL should not be fetched")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].title, "上海智能化设备采购意向")
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/api/detail/1")
        self.assertEqual(result.notices[0].publish_date, "2026-07-01")
        self.assertEqual(result.notices[0].purchaser, "上海采购人")
        self.assertIn("本项目采购弱电智能化系统", result.notices[0].content)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_counts_topology_seed_api_structured_candidates(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = ["https://portal.example.com/api/notices"]
        source.topology["list_url_regex"] = [r"/api/notices$"]
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                    "publishDate": "2026-07-01",
                    "purchaser": "上海采购人",
                    "content": "本项目采购弱电智能化系统",
                },
                {
                    "title": "上海安防监控采购公告",
                    "detailUrl": "/api/detail/2",
                    "publishDate": "2026-07-02",
                    "purchaser": "上海采购单位",
                    "content": "采购安防监控系统设备",
                },
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body><a href='/api/notices'>API notices</a></body></html>", 200, "OK"
            if url == "https://portal.example.com/api/notices":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(result.parsed_count, 2)
        self.assertGreaterEqual(result.candidate_count, result.parsed_count)
        self.assertGreaterEqual(result.candidate_count, 2)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_does_not_emit_plain_html_list_link_without_detail_validation(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.notices, [])

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_fetches_entry_list_and_detail_before_emitting_notice(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body><a href='/notices/'>Notices</a></body></html>", 200, "OK"
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位。</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertEqual(result.notices[0].publish_date, "2026-07-02")
        self.assertEqual(result.notices[0].purchaser, "上海测试单位")
        self.assertIn("本项目采购安防监控系统", result.notices[0].content)
        self.assertGreaterEqual(result.candidate_count, 1)
        self.assertEqual(result.parsed_count, 1)
        self.assertGreaterEqual(mock_request_url.call_count, 3)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_preserves_missing_detail_publish_date_as_empty(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body><a href='/notices/'>Notices</a></body></html>", 200, "OK"
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>采购单位：上海测试单位。</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].publish_date, "")

    def test_notice_deduplicator_collapses_tracking_query_variants(self):
        deduplicator = NoticeDeduplicator()
        first = Notice(
            source_id="portal",
            source_name="Portal",
            title="上海安防工程公开招标公告",
            detail_url="https://portal.example.com/detail/42?utm_source=list&id=42",
        )
        duplicate = Notice(
            source_id="portal",
            source_name="Portal",
            title="上海安防工程公开招标公告",
            detail_url="https://portal.example.com/detail/42?id=42&from=home",
        )

        self.assertTrue(deduplicator.add(first))
        self.assertFalse(deduplicator.add(duplicate))


if __name__ == "__main__":
    unittest.main()
