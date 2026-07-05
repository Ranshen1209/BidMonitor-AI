import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

import requests

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
    @patch("crawler.url_list.UrlListCrawler._request_http")
    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search(self, mock_request_url, mock_request_http):
        from crawler.source_models import CrawlResult

        with open(os.path.join(ROOT_DIR, "server", "site_topologies.json"), "r", encoding="utf-8") as f:
            qianlima_topology = next(
                site for site in json.load(f)["sites"] if site.get("id") == "qianlima"
            )

        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            topology=qianlima_topology,
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )
        vip_result = CrawlResult(diagnostics=[{"status": "stopped", "reason": "empty-page"}])
        requested_http = []
        discovered_vip_url = "https://search.vip.qianlima.com/rest/service/website/search/solr"

        def fake_request(url):
            if url == "https://www.qianlima.com/":
                return (
                    f'<html><body><a href="{discovered_vip_url}">search link</a></body></html>',
                    200,
                    "OK",
                )
            if url in {
                "https://www.qianlima.com/zbgg/",
                "https://www.qianlima.com/mfzb",
                "https://www.qianlima.com/zbyg",
            }:
                return "<html><body></body></html>", 200, "OK"
            if url == discovered_vip_url:
                raise AssertionError("generic fallback must not request discovered VIP search endpoint")
            raise AssertionError(f"unexpected url {url}")

        def fake_request_http(method, url, params=None, data=None):
            requested_http.append((method, url, params, data))
            self.assertNotIn("search.vip.qianlima.com", url)
            self.assertEqual(method, "GET")
            self.assertEqual(url, "https://search.qianlima.com/")
            self.assertEqual(params, {"q": ""})
            return "<html><body></body></html>", 200, "OK"

        mock_request_url.side_effect = fake_request
        mock_request_http.side_effect = fake_request_http

        with patch("crawler.qianlima_vip.QianlimaVipSearchClient.collect", return_value=vip_result) as collect_mock:
            result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0, "keywords": ["会议"]}).collect(source)

        self.assertEqual(result.notices, [])
        self.assertEqual(result.error_count, 0)
        self.assertEqual(len(requested_http), 1)
        self.assertNotIn(discovered_vip_url, [call.args[0] for call in mock_request_url.call_args_list])
        collect_mock.assert_called_once()

    @patch("crawler.url_list.UrlListCrawler._request_url_with_browser")
    @patch("crawler.url_list.UrlListCrawler._request_http")
    def test_collect_qianlima_empty_vip_result_falls_back_without_browser_auto(
        self,
        mock_request_http,
        mock_request_url_with_browser,
    ):
        from crawler.source_models import CrawlResult

        with open(os.path.join(ROOT_DIR, "server", "site_topologies.json"), "r", encoding="utf-8") as f:
            qianlima_topology = next(
                site for site in json.load(f)["sites"] if site.get("id") == "qianlima"
            )

        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            topology=qianlima_topology,
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )
        vip_result = CrawlResult()
        requested_http = []
        discovered_vip_url = "https://search.vip.qianlima.com/rest/service/website/search/solr"

        def fake_request_http(method, url, params=None, data=None):
            requested_http.append((method, url, params, data))
            self.assertNotIn("search.vip.qianlima.com", url)
            if method == "GET" and url == "https://www.qianlima.com/":
                return (
                    f'<html><body><a href="{discovered_vip_url}">search link</a></body></html>',
                    200,
                    "OK",
                )
            if method == "GET" and url in {
                "https://www.qianlima.com/zbgg/",
                "https://www.qianlima.com/mfzb",
                "https://www.qianlima.com/zbyg",
            }:
                return "<html><body></body></html>", 200, "OK"
            if method == "GET" and url == "https://search.qianlima.com/":
                self.assertEqual(params, {"q": ""})
                return "<html><body></body></html>", 200, "OK"
            raise AssertionError(f"unexpected {method} {url}")

        mock_request_http.side_effect = fake_request_http
        mock_request_url_with_browser.side_effect = AssertionError(
            "generic fallback must stay HTTP-only when empty VIP result falls back"
        )

        with patch("crawler.qianlima_vip.QianlimaVipSearchClient.collect", return_value=vip_result) as collect_mock:
            result = TopologySourceAdapter(
                {
                    "request_delay": 0,
                    "domain_delay": 0,
                    "keywords": ["会议"],
                    "browser_backend": {"mode": "browser_auto"},
                }
            ).collect(source)

        self.assertEqual(result.notices, [])
        self.assertEqual(result.error_count, 0)
        self.assertTrue(requested_http)
        self.assertNotIn(
            discovered_vip_url,
            [url for _method, url, _params, _data in requested_http],
        )
        mock_request_url_with_browser.assert_not_called()
        collect_mock.assert_called_once()

    @patch("crawler.url_list.UrlListCrawler._request_url_with_browser")
    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_qianlima_uses_vip_search_then_enriches_details(
        self,
        mock_request_url,
        mock_request_url_with_browser,
    ):
        from crawler.source_models import CrawlResult

        detail_url = "http://www.qianlima.com/zb/detail/20260705_8.html"
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            topology={
                "id": "qianlima",
                "name": "千里马",
                "entry_url": "https://www.qianlima.com/",
                "allowed_hosts": ["www.qianlima.com", "search.vip.qianlima.com"],
                "detail_url_regex": [r"^https?://www\.qianlima\.com/zb/detail/\d{8}_\d+\.html$"],
            },
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )

        mock_request_url.return_value = (
            """
            <html><body>
                <h1>上海会议系统招标公告</h1>
                <main>
                    项目名称：上海会议系统公开招标项目
                    采购人：上海采购单位
                    预算金额：120万元
                    发布时间：2026-07-05
                </main>
            </body></html>
            """,
            200,
            "OK",
        )

        adapter = TopologySourceAdapter(
            {
                "keywords": ["会议"],
                "qianlima_max_pages_per_keyword": 1,
                "qianlima_max_results_per_run": 20,
                "browser_backend": {"mode": "browser_auto"},
            }
        )
        vip_result = CrawlResult(
            notices=[
                Notice(
                    source_id="qianlima",
                    source_name="千里马",
                    source_item_id="8",
                    title="上海会议系统招标公告",
                    detail_url=detail_url,
                    publish_date="2026-07-05",
                    content="project_stage: 招标公告",
                    raw={"qianlima": {"contentid": 8}},
                )
            ],
            fetched_count=1,
            candidate_count=1,
            parsed_count=1,
            diagnostics=[{"status": "success", "parsed_count": 1}],
        )

        mock_request_url_with_browser.side_effect = AssertionError(
            "VIP detail enrichment must stay HTTP-only"
        )

        with patch("crawler.qianlima_vip.QianlimaVipSearchClient.collect", return_value=vip_result) as collect_mock:
            result = adapter.collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].source_item_id, "8")
        self.assertEqual(result.notices[0].title, "上海会议系统招标公告")
        self.assertIn("预算金额", result.notices[0].content)
        self.assertIn("qianlima_search", result.notices[0].raw)
        self.assertIn("detail", result.notices[0].raw)
        self.assertNotIn("qianlima", result.notices[0].raw)
        self.assertNotIn("legacy", result.notices[0].raw)
        self.assertEqual(result.notices[0].raw["detail"]["title"], "上海会议系统招标公告")
        mock_request_url.assert_called_once_with(detail_url)
        mock_request_url_with_browser.assert_not_called()
        collect_mock.assert_called_once()

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_qianlima_reports_failed_detail_enrichment_attempt(self, mock_request_url):
        from crawler.source_models import CrawlResult

        detail_url = "http://www.qianlima.com/zb/detail/20260705_9.html"
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            topology={
                "id": "qianlima",
                "name": "千里马",
                "entry_url": "https://www.qianlima.com/",
                "allowed_hosts": ["www.qianlima.com", "search.vip.qianlima.com"],
                "detail_url_regex": [r"^https?://www\.qianlima\.com/zb/detail/\d{8}_\d+\.html$"],
                "blocked_phrases": ["需要项目通权限才能查看"],
            },
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )
        search_notice = Notice(
            source_id="qianlima",
            source_name="千里马",
            source_item_id="9",
            title="上海会议系统招标公告",
            detail_url=detail_url,
            publish_date="2026-07-05",
            content="project_stage: 招标公告",
            raw={"qianlima": {"contentid": 9, "token": "redacted-token"}},
        )
        vip_result = CrawlResult(
            notices=[search_notice],
            fetched_count=1,
            candidate_count=1,
            parsed_count=1,
            diagnostics=[{"status": "success", "parsed_count": 1}],
        )
        mock_request_url.return_value = (
            "<html><body>需要项目通权限才能查看</body></html>",
            403,
            "Forbidden",
        )

        with patch("crawler.qianlima_vip.QianlimaVipSearchClient.collect", return_value=vip_result):
            result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0, "keywords": ["会议"]}).collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, detail_url)
        self.assertEqual(result.notices[0].content, "project_stage: 招标公告")
        self.assertEqual(result.fetched_count, 2)
        self.assertGreaterEqual(result.error_count + result.skipped_count, 1)
        self.assertGreaterEqual(result.error_count, 1)
        self.assertTrue(any("detail" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == detail_url
                and diagnostic.get("status") in {"failed", "skipped"}
                and "detail" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )
        serialized = json.dumps(result.diagnostics + [{"errors": result.errors}], ensure_ascii=False)
        self.assertNotIn("redacted-token", serialized)

    @patch("crawler.url_list.UrlListCrawler._request_http")
    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_admits_structured_json_from_post_search(self, mock_request_url, mock_request_http):
        source = Source(
            id="portal",
            name="Portal",
            url="https://portal.example.com/",
            topology={
                "id": "portal",
                "name": "Portal",
                "entry_url": "https://portal.example.com/",
                "allowed_hosts": ["portal.example.com"],
                "search": {
                    "method": "POST",
                    "url": "/api/search",
                    "params": ["pageNum", "title"],
                    "defaults": {"pageNum": 1, "title": ""},
                },
            },
        )
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/detail/42",
                    "publishDate": "2026-07-01",
                    "purchaser": "上海采购人",
                    "content": "本项目采购弱电智能化系统",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body></body></html>", 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        def fake_request_http(method, url, params=None, data=None):
            self.assertEqual(method, "POST")
            self.assertEqual(url, "https://portal.example.com/api/search")
            self.assertEqual(data, {"pageNum": 1, "title": ""})
            return json.dumps(payload, ensure_ascii=False), 200, "OK"

        mock_request_url.side_effect = fake_request
        mock_request_http.side_effect = fake_request_http

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertEqual(result.notices[0].publish_date, "2026-07-01")
        self.assertEqual(result.error_count, 0)

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
            if url == "https://portal.example.com/notices/":
                return "<html><body></body></html>", 200, "OK"
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
            if url == "https://portal.example.com/notices/":
                return "<html><body></body></html>", 200, "OK"
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
    def test_collect_skips_structured_json_record_with_placeholder_url(self, mock_request_url):
        for detail_url in ("javascript:void(0)", "mailto:test@example.com", "#", "tel:123"):
            with self.subTest(detail_url=detail_url):
                payload = {
                    "records": [
                        {
                            "title": "上海智能化设备采购意向",
                            "detailUrl": detail_url,
                            "publishDate": "2026-07-01",
                            "purchaser": "上海采购人",
                            "content": "本项目采购弱电智能化系统",
                        }
                    ]
                }

                def fake_request(url):
                    if url == "https://portal.example.com/":
                        return json.dumps(payload, ensure_ascii=False), 200, "OK"
                    if url == "https://portal.example.com/notices/":
                        return "<html><body></body></html>", 200, "OK"
                    raise AssertionError(f"unexpected url {url}")

                mock_request_url.reset_mock(side_effect=True)
                mock_request_url.side_effect = fake_request

                result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

                self.assertEqual(result.notices, [])
                self.assertEqual(result.parsed_count, 0)
                self.assertEqual(result.error_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_structured_json_record_with_template_detail_url(self, mock_request_url):
        for detail_url in ("{{detailUrl}}", "${detailUrl}", "{id}", "<detailUrl>", "about:blank"):
            with self.subTest(detail_url=detail_url):
                payload = {
                    "records": [
                        {
                            "title": "上海智能化设备采购意向",
                            "detailUrl": detail_url,
                            "publishDate": "2026-07-01",
                            "purchaser": "上海采购人",
                            "content": "本项目采购弱电智能化系统",
                        }
                    ]
                }

                def fake_request(url):
                    if url == "https://portal.example.com/":
                        return json.dumps(payload, ensure_ascii=False), 200, "OK"
                    if url == "https://portal.example.com/notices/":
                        return "<html><body></body></html>", 200, "OK"
                    raise AssertionError(f"unexpected url {url}")

                mock_request_url.reset_mock(side_effect=True)
                mock_request_url.side_effect = fake_request

                result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

                self.assertEqual(result.notices, [])
                self.assertEqual(result.parsed_count, 0)
                self.assertEqual(result.error_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_structured_json_record_with_empty_container_title(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": [],
                    "detailUrl": "/api/detail/1",
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
    def test_collect_skips_structured_json_record_with_nested_title(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": ["上海智能化设备采购意向"],
                    "detailUrl": "/api/detail/1",
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
    def test_collect_skips_structured_json_record_with_empty_container_explicit_url(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": {},
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
    def test_collect_skips_structured_json_record_with_nested_explicit_url(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": {"href": "/detail/42"},
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
    def test_collect_uses_later_good_scalar_aliases_when_earlier_aliases_are_containers(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": [],
                    "noticeTitle": "Good 招标公告",
                    "url": {},
                    "detailUrl": "/detail/42",
                    "content": "本项目采购设备",
                }
            ]
        }

        def fake_request(url):
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            if url == "https://portal.example.com/notices/":
                return "<html><body></body></html>", 200, "OK"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].title, "Good 招标公告")
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertNotEqual(result.notices[0].title, "[]")
        self.assertNotEqual(result.notices[0].detail_url, "https://portal.example.com/{}")

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
    def test_collect_skips_structured_json_record_with_empty_container_evidence(self, mock_request_url):
        for empty_content in ([], {}):
            with self.subTest(empty_content=empty_content):
                payload = {
                    "records": [
                        {
                            "title": "上海智能化设备采购意向",
                            "detailUrl": "/api/detail/1",
                            "content": empty_content,
                        }
                    ]
                }

                def fake_request(url):
                    if url == "https://portal.example.com/":
                        return json.dumps(payload, ensure_ascii=False), 200, "OK"
                    raise AssertionError(f"unexpected url {url}")

                mock_request_url.reset_mock(side_effect=True)
                mock_request_url.side_effect = fake_request

                result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

                self.assertEqual(result.notices, [])
                self.assertEqual(result.parsed_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_admits_structured_json_record_with_nested_raw_evidence(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海智能化设备采购意向",
                    "detailUrl": "/api/detail/1",
                    "content": {"summary": "本项目采购弱电"},
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
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/api/detail/1")

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
            if url == "https://portal.example.com/notices/":
                return "<html><body></body></html>", 200, "OK"
            if url == "https://portal.example.com/api/detail/1":
                raise AssertionError("structured JSON detail URL should not be fetched")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.error_count, 0)
        self.assertEqual(len(result.notices), 1)
        self.assertNotIn("https://portal.example.com/api/detail/1", requested_urls)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_topology_detail_fetch_for_initial_structured_url(self, mock_request_url):
        payload = {
            "records": [
                {
                    "title": "上海安防工程公开招标公告",
                    "detailUrl": "/detail/42",
                    "publishDate": "2026-07-02",
                    "purchaser": "上海测试单位",
                    "content": "本项目采购安防监控系统。",
                }
            ]
        }
        requested_urls = []

        def fake_request(url):
            requested_urls.append(url)
            if url == "https://portal.example.com/":
                return json.dumps(payload, ensure_ascii=False), 200, "OK"
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                raise AssertionError("already-admitted structured URL should not be fetched as detail")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertNotIn("https://portal.example.com/detail/42", requested_urls)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_skips_already_queued_detail_after_topology_api_admits_url(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = ["https://portal.example.com/api/notices"]
        source.topology["list_url_regex"] = [r"/api/notices$"]
        api_payload = {
            "records": [
                {
                    "title": "上海安防工程公开招标公告",
                    "detailUrl": "/detail/42",
                    "publishDate": "2026-07-02",
                    "purchaser": "上海测试单位",
                    "content": "本项目采购安防监控系统。",
                }
            ]
        }
        requested_urls = []

        def fake_request(url):
            requested_urls.append(url)
            if url == "https://portal.example.com/":
                return (
                    "<html><body>"
                    "<a href='/api/notices'>API notices</a>"
                    "<a href='/detail/42'>上海安防工程公开招标公告</a>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/api/notices":
                return json.dumps(api_payload, ensure_ascii=False), 200, "OK"
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

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertNotIn("https://portal.example.com/detail/42", requested_urls)
        self.assertEqual(result.fetched_count, 2)

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

    def test_collect_counts_entry_list_and_detail_fetches_without_mock_call_count(self):
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0})
        source = make_source()
        crawler = adapter._build_crawler(source)

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

        crawler._request_url = fake_request

        with patch.object(adapter, "_build_crawler", return_value=crawler):
            result = adapter.collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertGreaterEqual(result.fetched_count, 3)

    def test_collect_counts_delegated_get_once_per_actual_request(self):
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0})
        source = make_source()
        crawler = adapter._build_crawler(source)
        responses = {
            "https://portal.example.com/": (
                "<html><body><a href='/notices/'>Notices</a></body></html>",
                200,
                "OK",
            ),
            "https://portal.example.com/notices/": (
                "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                200,
                "OK",
            ),
            "https://portal.example.com/detail/42": (
                "<html><body><h1>上海安防工程公开招标公告</h1>"
                "<p>发布时间：2026-07-02</p>"
                "<p>采购单位：上海测试单位。</p>"
                "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                200,
                "OK",
            ),
        }
        requested = []

        def fake_request_http(method, url, params=None, data=None):
            requested.append((method, url, params, data))
            self.assertEqual(method, "GET")
            return responses[url]

        crawler._request_http = fake_request_http

        with patch.object(adapter, "_build_crawler", return_value=crawler):
            result = adapter.collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(len(requested), 3)
        self.assertEqual(result.fetched_count, len(requested))

    def test_build_crawler_post_json_attaches_cookie_without_logging_body(self):
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )
        logs = []
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0, "log_callback": logs.append})
        crawler = adapter._build_crawler(source)
        response = Mock(status_code=200, reason="OK", text='{"ok": true}', apparent_encoding="utf-8", encoding="utf-8")
        crawler.session = Mock()
        crawler.session.post.return_value = response

        payload = {"keywords": "会议", "token": "should-not-log"}
        result_payload, status_code, status_text = crawler.post_json(
            "https://search.vip.qianlima.com/rest/service/website/search/solr",
            payload,
        )

        self.assertEqual(result_payload, {"ok": True})
        self.assertEqual(status_code, 200)
        self.assertEqual(status_text, "OK")
        crawler.session.post.assert_called_once()
        kwargs = crawler.session.post.call_args.kwargs
        self.assertEqual(kwargs["json"], payload)
        self.assertEqual(kwargs["headers"]["Cookie"], "SESSION=secret")
        self.assertTrue(any("HTTP POST JSON" in message for message in logs))
        self.assertFalse(any("SESSION=secret" in message or "should-not-log" in message for message in logs))

    @patch("crawler.url_list.UrlListCrawler._request_url_with_browser")
    @patch("crawler.url_list.UrlListCrawler._request_http")
    def test_build_crawler_get_json_uses_http_without_browser_auto(
        self,
        mock_request_http,
        mock_request_url_with_browser,
    ):
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
        )
        adapter = TopologySourceAdapter(
            {
                "request_delay": 0,
                "domain_delay": 0,
                "browser_backend": {"mode": "browser_auto"},
            }
        )
        crawler = adapter._build_crawler(source)
        mock_request_http.return_value = ('{"ok": true, "count": 1}', 200, "OK")
        mock_request_url_with_browser.side_effect = AssertionError(
            "get_json() must stay HTTP-only"
        )

        result_payload, status_code, status_text = crawler.get_json(
            "https://search.vip.qianlima.com/rest/service/website/search/solr"
        )

        self.assertEqual(result_payload, {"ok": True, "count": 1})
        self.assertEqual(status_code, 200)
        self.assertEqual(status_text, "OK")
        mock_request_http.assert_called_once_with(
            "GET",
            "https://search.vip.qianlima.com/rest/service/website/search/solr",
        )
        mock_request_url_with_browser.assert_not_called()

    def test_build_crawler_post_json_returns_sanitized_error_on_request_exception(self):
        source = Source(
            id="qianlima",
            name="千里马",
            url="https://www.qianlima.com/",
            auth_cookies=[{"domain": "qianlima.com", "cookie": "SESSION=secret", "enabled": True}],
        )
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0})
        crawler = adapter._build_crawler(source)
        crawler.session = Mock()
        crawler.session.post.side_effect = requests.RequestException("request failed for payload=secret")

        result_payload, status_code, status_text = crawler.post_json(
            "https://search.vip.qianlima.com/rest/service/website/search/solr",
            {"keywords": "会议", "token": "should-not-leak"},
        )

        self.assertEqual(result_payload, {})
        self.assertEqual(status_code, 599)
        self.assertEqual(status_text, "RequestException: request failed")
        self.assertNotIn("should-not-leak", status_text)
        self.assertNotIn("SESSION=secret", status_text)

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

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_accounts_for_failed_topology_seed_fetch(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body><a href='/notices/'>Notices</a></body></html>", 200, "OK"
            if url == "https://portal.example.com/notices/":
                return "list failed", 500, "Internal Server Error"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(make_source())

        self.assertEqual(result.notices, [])
        self.assertGreaterEqual(result.candidate_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("HTTP 500" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == "https://portal.example.com/notices/"
                and "HTTP 500" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )
        self.assertEqual(result.diagnostics[-1].get("status"), "failed")

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_continues_seed_traversal_after_entry_request_exception(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                raise requests.exceptions.ConnectionError("entry down")
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
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("ConnectionError" in error and "entry down" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == "https://portal.example.com/"
                and diagnostic.get("status") == "failed"
                and "entry down" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )
        self.assertEqual(result.diagnostics[-1].get("status"), "partial")

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_treats_unexpected_entry_exception_as_real_failure(self, mock_request_url):
        called_urls = []

        def fake_request(url):
            called_urls.append(url)
            if url == "https://portal.example.com/":
                raise AttributeError("programmer bug")
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

        self.assertEqual(result.notices, [])
        self.assertEqual(result.error_count, 1)
        self.assertTrue(
            any("AttributeError" in error and "programmer bug" in error for error in result.errors)
        )
        self.assertEqual(result.diagnostics[-1].get("status"), "failed")
        self.assertEqual(called_urls, ["https://portal.example.com/"])

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_continues_seed_traversal_after_entry_http_error(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return "server exploded", 500, "Internal Server Error"
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
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("HTTP 500" in error for error in result.errors))
        self.assertGreaterEqual(result.candidate_count, 1)
        self.assertEqual(result.parsed_count, 1)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_continues_seed_traversal_after_entry_blocked_content(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return "<html><body>请先登录后查看公告</body></html>", 200, "OK"
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
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("登录" in error for error in result.errors))
        self.assertEqual(result.parsed_count, 1)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_accounts_for_failed_detail_candidate_fetch(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = []

        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return "detail failed", 500, "Internal Server Error"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(result.notices, [])
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("HTTP 500" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == "https://portal.example.com/detail/42"
                and "detail" in diagnostic.get("reason", "").lower()
                for diagnostic in result.diagnostics
            )
        )

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_accounts_for_followed_candidate_request_exception(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = []
        source.topology["detail_url_regex"] = [r"/detail/\d+$"]

        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body><a href='/notice?id=42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/notice?id=42":
                raise requests.exceptions.Timeout("timed out")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(result.notices, [])
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("Timeout" in error and "timed out" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == "https://portal.example.com/notice?id=42"
                and "page_type" in diagnostic
                and diagnostic.get("page_type") != "detail"
                and "Timeout" in diagnostic.get("reason", "")
                and "timed out" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )

    @patch("crawler.url_list.UrlListCrawler._request_url")
    @patch("crawler.url_list.UrlListCrawler._request_url_with_browser")
    def test_collect_counts_browser_recovered_candidate_request_exception(
        self,
        mock_browser_request,
        mock_request_url,
    ):
        source = make_source()
        source.topology["seed_urls"] = []
        source.topology["detail_url_regex"] = [r"/detail/\d+$"]
        detail_url = "https://portal.example.com/detail/42"

        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                raise requests.exceptions.Timeout("timed out")
            raise AssertionError(f"unexpected url {url}")

        def fake_browser_request(url):
            if url == detail_url:
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位。</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "Browser",
                )
            raise AssertionError(f"unexpected browser url {url}")

        mock_request_url.side_effect = fake_request
        mock_browser_request.side_effect = fake_browser_request

        result = TopologySourceAdapter(
            {"request_delay": 0, "domain_delay": 0, "use_selenium": True}
        ).collect(source)

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].detail_url, detail_url)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(result.error_count, 0)
        self.assertGreaterEqual(result.fetched_count, 3)
        self.assertFalse(
            any(
                diagnostic.get("url") == detail_url
                and diagnostic.get("status") == "failed"
                and "timed out" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )
        mock_browser_request.assert_called_once_with(detail_url)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_rejects_invalid_notice_detail_url_before_append(self, mock_request_url):
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0})

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
        invalid_notice = Notice(
            source_id="portal",
            source_name="Portal",
            title="上海安防工程公开招标公告",
            detail_url="javascript:void(0)",
        )

        with patch.object(adapter, "_notice_from_bid", return_value=invalid_notice):
            result = adapter.collect(make_source())

        self.assertEqual(result.notices, [])
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.parsed_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_rejects_template_notice_detail_url_before_append(self, mock_request_url):
        adapter = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0})

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
        invalid_notice = Notice(
            source_id="portal",
            source_name="Portal",
            title="上海安防工程公开招标公告",
            detail_url="https://portal.example.com/{{detailUrl}}",
        )

        with patch.object(adapter, "_notice_from_bid", return_value=invalid_notice):
            result = adapter.collect(make_source())

        self.assertEqual(result.notices, [])
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.parsed_count, 0)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_collect_accounts_for_failed_followed_non_detail_candidate_fetch(self, mock_request_url):
        source = make_source()
        source.topology["seed_urls"] = []
        source.topology["detail_url_regex"] = [r"/detail/\d+$"]

        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body><a href='/notice?id=42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/notice?id=42":
                return "detail failed", 500, "Internal Server Error"
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"request_delay": 0, "domain_delay": 0}).collect(source)

        self.assertEqual(result.notices, [])
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertTrue(any("HTTP 500" in error for error in result.errors))
        self.assertTrue(
            any(
                diagnostic.get("url") == "https://portal.example.com/notice?id=42"
                and "page_type" in diagnostic
                and diagnostic.get("page_type") != "detail"
                and "HTTP 500" in diagnostic.get("reason", "")
                for diagnostic in result.diagnostics
            )
        )

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
