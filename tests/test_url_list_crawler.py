import json
import os
import threading
import tempfile
import unittest
from unittest.mock import patch

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.url_list import UrlListCrawler, requests


class UrlListCrawlerTests(unittest.TestCase):
    def make_crawler(self, file_path, diagnostics_path=None):
        return UrlListCrawler(
            {
                "timeout": 1,
                "request_delay": 0,
                "max_retries": 1,
                "diagnostics_path": diagnostics_path,
            },
            {"name": "上海招投标URL清单", "file_path": file_path},
        )

    def make_crawler_with_logs(self, file_path, diagnostics_path, logs):
        return UrlListCrawler(
            {
                "timeout": 1,
                "request_delay": 0,
                "max_retries": 1,
                "diagnostics_path": diagnostics_path,
                "log_callback": logs.append,
            },
            {"name": "上海招投标URL清单", "file_path": file_path},
        )

    def make_crawler_with_source_config(self, file_path, diagnostics_path, source_config, config=None):
        merged_source = {"name": "上海招投标URL清单", "file_path": file_path}
        merged_source.update(source_config)
        merged_config = {
            "timeout": 1,
            "request_delay": 0,
            "domain_delay": 0,
            "max_retries": 1,
            "diagnostics_path": diagnostics_path,
        }
        if config:
            merged_config.update(config)
        return UrlListCrawler(merged_config, merged_source)

    def write_topologies(self, tmpdir, sites):
        path = os.path.join(tmpdir, "site_topologies.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"version": 1, "sites": sites}, ensure_ascii=False))
        return path

    def test_topology_search_request_uses_post_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "search": {
                            "method": "POST",
                            "url": "https://portal.example.com/api/search",
                            "params": ["pageNum", "title"],
                            "defaults": {"pageNum": 1, "title": ""},
                        },
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            request = crawler._topology_search_request("https://portal.example.com/")

        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://portal.example.com/api/search")
        self.assertEqual(request["data"], {"pageNum": 1, "title": ""})

    def test_topology_search_request_uses_get_params_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "search": {
                            "method": "GET",
                            "url": "/api/search",
                            "params": ["pageNum", "title"],
                            "defaults": {"pageNum": 1, "title": ""},
                        },
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            request = crawler._topology_search_request("https://portal.example.com/")

        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["url"], "https://portal.example.com/api/search")
        self.assertEqual(request["params"], {"pageNum": 1, "title": ""})
        self.assertEqual(request["data"], {})

    def test_topology_search_request_rejects_templated_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "search": {"method": "POST", "url": "/api/search/{page}"},
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            request = crawler._topology_search_request("https://portal.example.com/")

        self.assertIsNone(request)

    def test_topology_crawl_executes_post_search_request(self):
        calls = []

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/detail/\d+$"],
                        "search": {
                            "method": "POST",
                            "url": "/api/search",
                            "params": ["pageNum", "title"],
                            "defaults": {"pageNum": 1, "title": ""},
                        },
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )

            def fake_request_http(method, url, params=None, data=None):
                calls.append((method, url, params, data))
                self.assertEqual(method, "POST")
                self.assertEqual(url, "https://portal.example.com/api/search")
                self.assertEqual(data, {"pageNum": 1, "title": ""})
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )

            def fake_request_url(url):
                if url == "https://portal.example.com/detail/42":
                    return (
                        "<html><body><h1>上海安防工程公开招标公告</h1>"
                        "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                        "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                        200,
                        "OK",
                    )
                raise AssertionError(f"unexpected url {url}")

            crawler._request_http = fake_request_http
            crawler._request_url = fake_request_url

            bids = crawler._crawl_topology_from_url(
                "https://portal.example.com/",
                "",
                "2026-07-04T00:00:00",
                crawler._classify_url("https://portal.example.com/"),
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].url, "https://portal.example.com/detail/42")

    def test_topology_detail_regex_blocks_generic_html_fallback_on_same_topology_host(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.bidchance.test/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "bidchance-test",
                        "name": "招标网测试",
                        "entry_url": "https://www.bidchance.test/",
                        "allowed_hosts": ["www.bidchance.test", "chance.bidchance.test"],
                        "detail_url_regex": [r"^https://www\.bidchance\.test/info-gonggao-[A-Za-z0-9]+\.html$"],
                        "list_url_regex": [r"/outlinegonggao\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            self.assertEqual(
                crawler._classify_url("https://www.bidchance.test/info-gonggao-ABC.html")["page_type"],
                "detail",
            )
            self.assertNotEqual(
                crawler._classify_url("https://chance.bidchance.test/company-123.html")["page_type"],
                "detail",
            )

    def test_topology_strict_mode_keeps_unknown_external_hosts_generic(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertEqual(crawler._classify_url("https://unknown.example.com/news-1.html")["page_type"], "detail")

    @patch.object(UrlListCrawler, "_request_url")
    def test_candidate_scoring_prioritizes_detail_links_over_noisy_lists(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body>"
                    "<a href='/company-1.html'>上海测试招标代理有限公司</a>"
                    "<a href='/category/news.html'>政策法规新闻</a>"
                    "<a href='/notice/1.html'>上海安防工程公开招标公告 2026-07-02</a>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/notice/1.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/notice/\d+\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1, "max_follow_links_per_page": 1},
                config={"site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].url, "https://portal.example.com/notice/1.html")

    def test_rejects_known_non_announcement_urls(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        rejected = [
            "https://www.chinabidding.com/infoDetail/123-News.html",
            "https://www.plap.mil.cn/freecms/site/juncai/dishonesty.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/suspended.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/warning.html?id=1",
            "https://chance.bidchance.com/company-123.html",
        ]

        for url in rejected:
            with self.subTest(url=url):
                self.assertTrue(crawler._is_known_non_announcement_url(url))

    def test_known_non_announcement_url_patterns_do_not_match_unrelated_hosts_or_paths(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        accepted = [
            "https://notchinabidding.com/infoDetail/123-News.html",
            "https://fakeplap.mil.cn/freecms/site/juncai/dishonesty.html?id=1",
            "https://notbidchance.com/company-123.html",
            "https://www.chinabidding.com/other/123-News.html",
            "https://www.plap.mil.cn/freecms/site/juncai/dishonesty.html",
            "https://www.plap.mil.cn/anything/warning.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/nested/warning.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/extra/dishonesty.html?id=1",
            "https://chance.bidchance.com/company/123.html",
        ]

        for url in accepted:
            with self.subTest(url=url):
                self.assertFalse(crawler._is_known_non_announcement_url(url))

        self.assertNotEqual(
            crawler._classify_url("https://notchinabidding.com/infoDetail/123-News.html")["handling"],
            "non_announcement",
        )
        self.assertNotEqual(
            crawler._classify_url("https://www.plap.mil.cn/anything/warning.html?id=1")["handling"],
            "non_announcement",
        )
        self.assertNotEqual(
            crawler._classify_url(
                "https://www.plap.mil.cn/freecms/site/juncai/nested/warning.html?id=1"
            )["handling"],
            "non_announcement",
        )

    def test_rejects_platform_shell_title_without_structured_fields(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        detail_url = (
            "https://www.sdicc.com.cn/cgxx/ggDetail?"
            "gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d"
        )
        bid = type(
            "Bid",
            (),
            {
                "title": "国投集团电子采购平台",
                "content": "国投集团电子采购平台 招标公告 项目 服务",
            },
        )()

        self.assertEqual(crawler._classify_url(detail_url)["page_type"], "detail")
        self.assertFalse(
            crawler._is_admissible_detail_bid(
                bid,
                detail_url,
            )
        )

    def test_platform_shell_title_with_structured_fields_is_admissible_detail(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        detail_url = (
            "https://www.sdicc.com.cn/cgxx/ggDetail?"
            "gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d"
        )
        bid = type(
            "Bid",
            (),
            {
                "title": "国投集团电子采购平台",
                "content": "发布时间：2026-07-02 采购单位：上海测试单位 招标公告 项目 服务",
            },
        )()

        self.assertEqual(crawler._classify_url(detail_url)["page_type"], "detail")
        self.assertTrue(
            crawler._is_admissible_detail_bid(
                bid,
                detail_url,
            )
        )

    def test_minimal_detail_evidence_requires_structured_procurement_field(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertFalse(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 本项目采购安防监控系统服务",
                allow_minimal=True,
            )
        )
        self.assertTrue(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 发布时间：2026-07-02 本项目采购安防监控系统服务",
                allow_minimal=True,
            )
        )

    def test_full_detail_evidence_still_accepts_two_structured_fields(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertTrue(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 发布时间：2026-07-02 采购单位：上海测试单位",
                allow_minimal=False,
            )
        )

    def test_hash_fragment_login_url_classifies_as_login_and_requires_login_on_topology_host(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal-test",
                        "name": "Portal Test",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            rule = crawler._classify_url("https://portal.example.com/#/login")

            self.assertEqual(rule["page_type"], "login")
            self.assertEqual(rule["handling"], "requires_login")

    def test_hash_route_containing_sso_word_is_not_login(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal-test",
                        "name": "Portal Test",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )
            route_url = "https://portal.example.com/#/association/notices"

            rule = crawler._classify_url(route_url)

            self.assertNotEqual(rule["page_type"], "login")
            self.assertNotEqual(rule["handling"], "requires_login")
            self.assertTrue(crawler._should_follow_candidate("https://portal.example.com/", route_url, 0))

    def test_hash_login_near_matches_are_not_login_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal-test",
                        "name": "Portal Test",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            for route_url in [
                "https://portal.example.com/#/user/login-history",
                "https://portal.example.com/#/default/login-page",
            ]:
                with self.subTest(route_url=route_url):
                    rule = crawler._classify_url(route_url)

                    self.assertNotEqual(rule["page_type"], "login")
                    self.assertNotEqual(rule["handling"], "requires_login")

    def test_hash_login_near_matches_are_valid_traversal_urls(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )

        for route_url in [
            "https://portal.example.com/#/user/login-history",
            "https://portal.example.com/#/default/login-page",
        ]:
            with self.subTest(route_url=route_url):
                self.assertTrue(crawler._is_valid_traversal_url(route_url))

        self.assertFalse(crawler._is_valid_traversal_url("https://portal.example.com/#/user/login"))

    def test_topology_strict_detail_urls_false_allows_generic_detail_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal-test",
                        "name": "Portal Test",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/detail/\d+$"],
                        "strict_detail_urls": False,
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            self.assertEqual(
                crawler._classify_url("https://portal.example.com/news-1.html")["page_type"],
                "detail",
            )

    def test_txt_url_list_reading_deduplicates_and_skips_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n")
                f.write("https://example.com/list\n")
                f.write("not a url\n")
                f.write("https://example.com/list\n")
                f.write("http://example.org/detail?id=1\n")

            crawler = self.make_crawler(path)

            self.assertEqual(
                crawler.get_list_urls(),
                ["https://example.com/list", "http://example.org/detail?id=1"],
            )

    def test_csv_url_list_reads_url_column_or_url_like_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            direct_path = os.path.join(tmpdir, "direct.csv")
            with open(direct_path, "w", encoding="utf-8", newline="") as f:
                f.write("name,url\n")
                f.write("a,https://example.com/a\n")
                f.write("b,invalid\n")

            fallback_path = os.path.join(tmpdir, "fallback.csv")
            with open(fallback_path, "w", encoding="utf-8", newline="") as f:
                f.write("name,website\n")
                f.write("a,https://example.com/fallback\n")

            self.assertEqual(self.make_crawler(direct_path).get_list_urls(), ["https://example.com/a"])
            self.assertEqual(
                self.make_crawler(fallback_path).get_list_urls(),
                ["https://example.com/fallback"],
            )

    def test_json_url_source_reads_canonical_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "url_sources.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "version": 1,
                            "sources": [
                                {
                                    "id": "okcis",
                                    "name": "招标采购导航网",
                                    "url": "https://www.okcis.cn/",
                                    "enabled": True,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                )

            crawler = self.make_crawler_with_source_config(
                path,
                os.path.join(tmpdir, "diagnostics.jsonl"),
                {"source_type": "json"},
            )

            self.assertEqual(crawler.get_list_urls(), ["https://www.okcis.cn/"])

    def test_url_entries_can_run_concurrently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://a.example.com/\n")
                f.write("https://b.example.com/\n")
                f.write("https://c.example.com/\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {"concurrency": 3},
            )
            barrier = threading.Barrier(3)
            thread_names = set()

            def fake_crawl_one_entry(index, total, url, stop_event=None):
                thread_names.add(threading.current_thread().name)
                barrier.wait(timeout=2)
                return []

            with patch.object(crawler, "_crawl_one_entry", side_effect=fake_crawl_one_entry):
                bids = crawler.crawl()

            self.assertEqual(bids, [])
            self.assertEqual(len(thread_names), 3)

    def test_stale_project_url_sources_path_falls_back_to_repo_file(self):
        crawler = self.make_crawler_with_source_config(
            "/Users/cervine/Documents/Github/BidMonitor-AI/server/url_sources.json",
            None,
            {"source_type": "json"},
        )

        self.assertTrue(crawler.file_path.endswith("server/url_sources.json"))
        self.assertTrue(os.path.exists(crawler.file_path))
        self.assertGreater(len(crawler.get_list_urls()), 0)

    @patch.object(UrlListCrawler, "_request_url")
    def test_category_pages_are_not_saved_and_detail_links_are_verified(self, mock_request_url):
        def fake_request(url):
            if url == "https://example.com/":
                return (
                    "<html><body><a href='/security/'>安防工程</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://example.com/security/":
                return (
                    "<html><body><ul>"
                    "<li><a href='/notice/1.html'>上海安防工程公开招标公告</a><span>2026-07-02</span></li>"
                    "</ul></body></html>",
                    200,
                    "OK",
                )
            if url == "https://example.com/notice/1.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {"topology_max_depth": 3, "max_follow_links_per_page": 20},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].title, "上海安防工程公开招标公告")
            self.assertEqual(bids[0].url, "https://example.com/notice/1.html")
            self.assertNotEqual(bids[0].url, "https://example.com/security/")
            self.assertIn("original_url: https://example.com/notice/1.html", bids[0].content)

    @patch.object(UrlListCrawler, "_request_url")
    def test_index_style_list_pages_are_traversal_only_even_when_html_suffix_matches_detail(self, mock_request_url):
        list_url = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/index_1.htm"
        detail_url = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/202607/t20260702_12345678.htm"

        def fake_request(url):
            if url == list_url:
                return (
                    "<html><body><h1>公开招标公告_中国政府采购网</h1>"
                    "<nav>首页 高级搜索 上一页 下一页 共100条</nav>"
                    f"<a href='{detail_url}'>上海安防工程公开招标公告</a>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")

            crawler = self.make_crawler_with_source_config(path, diagnostics_path, {"topology_max_depth": 2})
            bids = crawler.crawl()

            self.assertEqual(crawler._classify_url(list_url)["page_type"], "list")
            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    @patch.object(UrlListCrawler, "_request_url")
    def test_generic_non_detail_page_is_not_saved_even_with_bid_keywords(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body><h1>安防工程招标公告</h1>"
            "<p>本栏目汇总安防工程、监控系统、弱电项目的招标公告。</p>"
            "<p>请进入具体公告查看采购单位、项目编号和预算金额。</p></body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/security/\n")

            bids = self.make_crawler_with_source_config(path, diagnostics_path, {"topology_max_depth": 1}).crawl()

            self.assertEqual(bids, [])

    def test_parse_does_not_emit_same_page_bid_for_traversal_page_without_detail_links(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {},
        )

        bids = crawler._parse_page(
            "<html><body><h1>安防工程招标公告</h1>"
            "<p>本栏目汇总安防工程、监控系统、弱电项目的招标公告。</p>"
            "<p>请进入具体公告查看采购单位、项目编号和预算金额。</p></body></html>",
            "https://example.com/security/",
            "2026-07-03T00:00:00",
        )

        self.assertEqual(bids, [])

    def test_rejects_download_static_template_and_hash_login_candidates(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )
        page_url = "https://portal.example.com/list"

        rejected = [
            "https://portal.example.com/file-web/downloadFile?id=abc",
            "https://portal.example.com/notice.docx",
            "https://portal.example.com/assets/app.css",
            "https://portal.example.com/${pingbiao.url}",
            "https://portal.example.com/#/login",
            "https://portal.example.com/login#/login",
        ]

        for candidate_url in rejected:
            with self.subTest(candidate_url=candidate_url):
                self.assertFalse(crawler._is_valid_traversal_url(candidate_url))
                self.assertFalse(crawler._should_follow_candidate(page_url, candidate_url, 0))

    def test_rejects_static_and_binary_extensions_in_query_values(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )
        page_url = "https://portal.example.com/list"

        rejected = [
            "https://portal.example.com/file?id=notice.pdf",
            "https://portal.example.com/resource?url=/assets/app.css",
            "https://portal.example.com/get?name=%E9%99%84%E4%BB%B6.docx",
        ]

        for candidate_url in rejected:
            with self.subTest(candidate_url=candidate_url):
                self.assertFalse(crawler._is_valid_traversal_url(candidate_url))
                self.assertFalse(crawler._should_follow_candidate(page_url, candidate_url, 0))

    def test_candidate_extraction_skips_invalid_url_shapes(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )
        html = (
            "<html><body>"
            "<a href='/file-web/downloadFile?id=abc'>招标文件下载</a>"
            "<a href='/assets/app.css'>采购样式</a>"
            "<a href='${pingbiao.url}'>采购公告模板</a>"
            "<a href='/#/login'>采购登录</a>"
            "<a href='/detail/1'>上海安防工程公开招标公告</a>"
            "</body></html>"
        )

        links = crawler._extract_candidate_links_from_html(html, "https://portal.example.com/list")

        self.assertEqual([link["url"] for link in links], ["https://portal.example.com/detail/1"])

    def test_embedded_topology_urls_skip_invalid_url_shapes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "示例公告门户",
                        "entry_url": "https://portal.example.com/list",
                        "allowed_hosts": ["portal.example.com"],
                        "list_url_regex": [r"/list$"],
                        "detail_url_regex": [r"/(?:detail/\d+|file-web/downloadFile)$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                "/tmp/missing.txt",
                None,
                {"topology_max_depth": 2},
                config={"site_topologies_path": topology_path},
            )
            html = (
                "<script>"
                "window.__DATA__ = {"
                "'url': 'https://portal.example.com/file-web/downloadFile?id=abc',"
                "'title': '上海安防工程公开招标公告',"
                "'detail': 'https://portal.example.com/detail/1'"
                "};"
                "</script>"
            )

            links = crawler._extract_candidate_links_from_html(html, "https://portal.example.com/list")

            self.assertEqual([link["url"] for link in links], ["https://portal.example.com/detail/1"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_entry_http_exception_without_browser_still_tries_topology_seeds(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                raise requests.exceptions.Timeout("entry slow")
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "入口测试",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "seed_urls": ["https://portal.example.com/notices/"],
                        "list_url_regex": [r"/notices/?$"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 2},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://portal.example.com/detail/42")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_seed_urls_are_crawled_even_when_home_has_no_links(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return ("<html><body><div id='app'></div></body></html>", 200, "OK")
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "示例公告门户",
                        "entry_url": "https://portal.example.com/",
                        "seed_urls": ["/notices/"],
                        "detail_url_regex": [r"/detail/\d+$"],
                        "list_url_regex": [r"/notices/?$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 2},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://portal.example.com/detail/42")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_seed_list_cannot_outrank_visible_detail_link(self, mock_request_url):
        requested = []

        def fake_request(url):
            requested.append(url)
            if url == "https://portal.example.com/":
                return (
                    "<html><body>"
                    "<a href='/notice/1.html'>查看详情</a>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/notice/1.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "示例公告门户",
                        "entry_url": "https://portal.example.com/",
                        "seed_urls": ["/notices/"],
                        "detail_url_regex": [r"/notice/\d+\.html$"],
                        "list_url_regex": [r"/notices/?$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1, "max_follow_links_per_page": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://portal.example.com/notice/1.html")
            self.assertNotIn("https://portal.example.com/notices/", requested)

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_seed_urls_are_prioritized_over_noisy_entry_links(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                noisy_links = "".join(
                    f"<a href='/category/{index}'>政策法规新闻栏目 {index}</a>" for index in range(5)
                )
                return (f"<html><body>{noisy_links}</body></html>", 200, "OK")
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            if "/category/" in url:
                return ("<html><body><p>空栏目</p></body></html>", 200, "OK")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "入口测试",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "seed_urls": ["https://portal.example.com/notices/"],
                        "list_url_regex": [r"/(?:notices|category/\d+)/?$"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 2, "max_follow_links_per_page": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://portal.example.com/detail/42")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_circuit_breaker_stops_repeated_521_domain_failures(self, mock_request_url):
        requested = []

        def fake_request(url):
            requested.append(url)
            return ("blocked", 521, "Origin Down")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://blocked.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "blocked",
                        "name": "Blocked Example",
                        "entry_url": "https://blocked.example.com/",
                        "allowed_hosts": ["blocked.example.com"],
                        "seed_urls": [
                            "https://blocked.example.com/list-1.html",
                            "https://blocked.example.com/list-2.html",
                            "https://blocked.example.com/list-3.html",
                            "https://blocked.example.com/list-4.html",
                        ],
                        "list_url_regex": [r"/list-\d+\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {
                    "topology_max_depth": 1,
                    "max_follow_links_per_page": 10,
                    "domain_failure_threshold": 2,
                },
                config={"site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

        self.assertEqual(bids, [])
        self.assertLessEqual(len(requested), 3)
        self.assertTrue(crawler._is_domain_circuit_open("blocked.example.com"))

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_circuit_breaker_serializes_concurrent_same_domain_failures(self, mock_request_url):
        requested = []
        requested_lock = threading.Lock()
        entry_barrier = threading.Barrier(5)
        seed_wave_ready = threading.Event()

        def fake_request(url):
            if url.startswith("https://blocked.example.com/entry-"):
                entry_barrier.wait(timeout=2)
                return ("entry down", 521, "Origin Down")
            if "/list-" in url:
                with requested_lock:
                    requested.append(url)
                    if len(requested) >= 5:
                        seed_wave_ready.set()
                seed_wave_ready.wait(timeout=0.2)
                return ("blocked", 521, "Origin Down")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                for index in range(5):
                    f.write(f"https://blocked.example.com/entry-{index}.html\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "blocked",
                        "name": "Blocked Example",
                        "entry_url": "https://blocked.example.com/",
                        "allowed_hosts": ["blocked.example.com"],
                        "seed_urls": ["https://blocked.example.com/list-1.html"],
                        "list_url_regex": [r"/(?:entry-\d+|list-\d+)\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {
                    "concurrency": 5,
                    "topology_max_depth": 1,
                    "domain_failure_threshold": 2,
                },
                config={"site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

        self.assertEqual(bids, [])
        self.assertLessEqual(len(requested), 2)
        self.assertTrue(crawler._is_domain_circuit_open("blocked.example.com"))

    def test_domain_circuit_open_log_callback_can_inspect_state_without_deadlock(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"domain_failure_threshold": 2},
        )

        def inspect_on_circuit_open(message):
            if "URL熔断" in message:
                crawler._is_domain_circuit_open("blocked.example.com")

        crawler.log_callback = inspect_on_circuit_open

        worker = threading.Thread(
            target=lambda: [
                crawler._record_domain_fetch_failure(
                    "https://blocked.example.com/list.html",
                    "HTTP 521: Origin Down",
                    status_code=521,
                )
                for _ in range(2)
            ]
        )
        worker.daemon = True
        worker.start()
        worker.join(timeout=1)

        self.assertFalse(worker.is_alive())
        self.assertTrue(crawler._is_domain_circuit_open("blocked.example.com"))

    def test_domain_fetch_failure_ignores_404_and_success_clears_blocked_count(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"domain_failure_threshold": 2},
        )

        crawler._record_domain_fetch_failure(
            "https://blocked.example.com/missing.html",
            "HTTP 404: Not Found",
            status_code=404,
        )
        self.assertFalse(crawler._is_domain_circuit_open("blocked.example.com"))
        self.assertNotIn("blocked.example.com", crawler._domain_failure_counts)

        crawler._record_domain_fetch_failure(
            "https://blocked.example.com/list.html",
            "HTTP 521: Origin Down",
            status_code=521,
        )
        self.assertEqual(crawler._domain_failure_counts.get("blocked.example.com"), 1)

        crawler._record_domain_fetch_success("https://blocked.example.com/list.html")
        self.assertNotIn("blocked.example.com", crawler._domain_failure_counts)
        self.assertFalse(crawler._is_domain_circuit_open("blocked.example.com"))

    def test_topology_template_seed_urls_are_not_requested_without_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "示例公告门户",
                        "entry_url": "https://portal.example.com/",
                        "seed_urls": ["https://portal.example.com/search?kw={kw}", "/notices/"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                os.path.join(tmpdir, "diagnostics.jsonl"),
                {},
                config={"site_topologies_path": topology_path},
            )

            links = crawler._topology_seed_links("https://portal.example.com/")

            self.assertEqual([link["url"] for link in links], ["https://portal.example.com/notices/"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_allowed_hosts_follow_cross_host_detail_links(self, mock_request_url):
        def fake_request(url):
            if url == "https://www.example.com/":
                return (
                    "<html><body><a href='https://bidding.example.com/notice-detail-7.html'>"
                    "上海智能化工程招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://bidding.example.com/notice-detail-7.html":
                return (
                    "<html><body><h1>上海智能化工程招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "cross-host",
                        "name": "跨域示例站",
                        "entry_url": "https://www.example.com/",
                        "allowed_hosts": ["www.example.com", "bidding.example.com"],
                        "detail_url_regex": [r"^https://bidding\.example\.com/notice-detail-\d+\.html$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://bidding.example.com/notice-detail-7.html")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_blocked_phrases_reject_masked_detail_pages(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body><h1>上海安防工程招标公告</h1>"
            "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
            "<p>登录即可免费查看完整信息，本项目采购安防监控系统。</p></body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://masked.example.com/detail/99\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "masked",
                        "name": "遮罩示例站",
                        "entry_url": "https://masked.example.com/",
                        "detail_url_regex": [r"/detail/\d+$"],
                        "blocked_phrases": ["登录即可免费查看完整信息"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(bids, [])
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostic = json.loads(f.readline())
            self.assertIn("登录即可免费查看完整信息", diagnostic["reason"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_generic_login_link_does_not_block_public_notice_list(self, mock_request_url):
        def fake_request(url):
            if url == "https://public.example.com/list":
                return (
                    "<html><body><a href='/login'>请登录</a>"
                    "<a href='/detail/1'>上海安防工程公开招标公告</a>"
                    "<span>发布时间：2026-07-02</span></body></html>",
                    200,
                    "OK",
                )
            if url == "https://public.example.com/detail/1":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://public.example.com/list\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "public",
                        "name": "公开示例站",
                        "entry_url": "https://public.example.com/list",
                        "allowed_hosts": ["public.example.com"],
                        "list_url_regex": [r"/list$"],
                        "detail_url_regex": [r"/detail/\d+$"],
                        "blocked_phrases": ["请登录"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://public.example.com/detail/1")

    @patch.object(UrlListCrawler, "_request_url")
    def test_security_script_tokens_do_not_block_visible_public_detail(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body><h1>上海监控设备改造招标公告</h1>"
            "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
            "<p>公告正文：本项目采购安防监控系统。</p>"
            "<script src='/assets/captcha-frontend.js'>AliyunCaptcha.init()</script>"
            "</body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.bidcenter.test/news-428272056-1.html\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "bidcenter-test",
                        "name": "采招测试",
                        "entry_url": "https://www.bidcenter.test/",
                        "allowed_hosts": ["www.bidcenter.test"],
                        "detail_url_regex": [r"/news-\d+-\d+\.html$"],
                        "blocked_phrases": ["AliyunCaptcha", "captcha-frontend"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].title, "上海监控设备改造招标公告")
            self.assertEqual(bids[0].url, "https://www.bidcenter.test/news-428272056-1.html")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_seeds_are_tried_when_entry_page_is_blocked(self, mock_request_url):
        def fake_request(url):
            if url == "https://blocked.example.com/":
                return ("anti bot shell", 521, "Origin Down")
            if url == "https://list.blocked.example.com/notices.html":
                return (
                    "<html><body><a href='https://detail.blocked.example.com/info-8.html'>"
                    "上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://detail.blocked.example.com/info-8.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://blocked.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "blocked-entry",
                        "name": "阻断入口示例",
                        "entry_url": "https://blocked.example.com/",
                        "allowed_hosts": [
                            "blocked.example.com",
                            "list.blocked.example.com",
                            "detail.blocked.example.com",
                        ],
                        "seed_urls": ["https://list.blocked.example.com/notices.html"],
                        "list_url_regex": [r"notices\.html$"],
                        "detail_url_regex": [r"/info-\d+\.html$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 2},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://detail.blocked.example.com/info-8.html")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_extracts_non_href_candidate_attributes(self, mock_request_url):
        detail_url = "https://www.okcis.test/20260702-n2-20260702010101010101.html"

        def fake_request(url):
            if url == "https://www.okcis.test/zbmf/":
                return (
                    "<html><body>"
                    "<b class='setwidth' rec_link='/20260702-n2-20260702010101010101.html' "
                    "rec_title='上海安防工程公开招标公告'></b>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.okcis.test/zbmf/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "okcis-test",
                        "name": "OKcis 测试",
                        "entry_url": "https://www.okcis.test/",
                        "allowed_hosts": ["www.okcis.test"],
                        "list_url_regex": [r"/zbmf/?$"],
                        "detail_url_regex": [r"^https://www\.okcis\.test/\d{8}-n\d-\d{20}\.html$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)
            self.assertEqual(bids[0].title, "上海安防工程公开招标公告")

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_extracts_sdicc_urlchange_detail_links(self, mock_request_url):
        list_url = "https://www.sdicc.test/"
        detail_url = "https://www.sdicc.test/cgxx/ggDetail?gcGuid=gc-123&ggGuid=gg-456"

        def fake_request(url):
            if url == list_url:
                return (
                    "<html><body><div onclick=\"urlChange('gg-456','gc-123')\">"
                    "上海智能化工程招标公告</div></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海智能化工程招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>招标人：上海测试单位</p>"
                    "<p>公告正文：本项目采购智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "sdicc-test",
                        "name": "国投测试",
                        "entry_url": list_url,
                        "allowed_hosts": ["www.sdicc.test"],
                        "detail_url_regex": [r"/cgxx/ggDetail\?gcGuid=[^&]+&ggGuid=[^&]+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_extracts_js_detail_even_when_page_has_regular_href_candidates(self, mock_request_url):
        list_url = "https://www.sdicc.test/"
        detail_url = "https://www.sdicc.test/cgxx/ggDetail?gcGuid=gc-123&ggGuid=gg-456"

        def fake_request(url):
            if url == list_url:
                return (
                    "<html><body>"
                    "<a href='/cgxx/cgxxList?page=2'>安防工程公告更多列表</a>"
                    "<div onclick=\"urlChange('gg-456','gc-123')\">上海智能化工程招标公告</div>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海智能化工程招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>招标人：上海测试单位</p>"
                    "<p>公告正文：本项目采购智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            if "page=2" in url:
                return ("<html><body><p>空列表</p></body></html>", 200, "OK")
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "sdicc-test",
                        "name": "国投测试",
                        "entry_url": list_url,
                        "allowed_hosts": ["www.sdicc.test"],
                        "list_url_regex": [r"/cgxx/cgxxList(?:\?.*)?$"],
                        "detail_url_regex": [r"/cgxx/ggDetail\?gcGuid=[^&]+&ggGuid=[^&]+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1, "max_follow_links_per_page": 10},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    @patch.object(UrlListCrawler, "_request_url")
    def test_sdicc_public_detail_action_button_does_not_block_admission(self, mock_request_url):
        list_url = "https://www.sdicc.com.cn/cgxx/cgxxList"
        detail_url = "https://www.sdicc.com.cn/cgxx/ggDetail?gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d"

        def fake_request(url):
            if url == list_url:
                return (
                    "<html><body><div onclick=\"urlChange('76cdd52c-8d91-4901-9a83-d28475fc5a6d','da97f2f1-64ca-4222-9d50-b976b16dbd2b')\">"
                    "上海安防工程招标公告</div></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><nav>用户登录</nav><button>我要投标</button>"
                    "<h1>上海安防工程招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>招标人：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    def test_sdicc_detail_regex_accepts_query_params_in_either_order(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        topology = crawler._topology_for_url("https://www.sdicc.com.cn/cgxx/cgxxList")
        self.assertIsNotNone(topology)

        self.assertEqual(
            crawler._classify_url_by_topology(
                "https://www.sdicc.com.cn/cgxx/ggDetail?gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d",
                topology,
            ),
            "detail",
        )
        self.assertEqual(
            crawler._classify_url_by_topology(
                "https://www.sdicc.com.cn/cgxx/ggDetail?gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d"
                "&tab=公告",
                topology,
            ),
            "detail",
        )
        self.assertEqual(
            crawler._classify_url_by_topology(
                "https://www.sdicc.com.cn/cgxx/ggDetail?ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d&gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b",
                topology,
            ),
            "detail",
        )

    @patch.object(UrlListCrawler, "_request_url")
    def test_title_only_detail_shell_is_rejected_until_body_evidence_exists(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body><h1>上海安防工程公开招标公告</h1>"
            "<p>登录后查看完整信息。</p></body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://example.com/detail/42\n")

            bids = self.make_crawler_with_source_config(urls_path, diagnostics_path, {}).crawl()

            self.assertEqual(bids, [])

    @patch.object(UrlListCrawler, "_request_url")
    def test_chnenergy_public_detail_ca_navigation_does_not_block_admission(self, mock_request_url):
        list_url = "https://www.chnenergybidding.com.cn/bidweb/001/001001/moreinfo.html"
        detail_url = "https://www.chnenergybidding.com.cn/bidweb/001/001001/001001001/20260702/abc.html"

        def fake_request(url):
            if url == list_url:
                return (
                    f"<html><body><a href='{detail_url}'>上海弱电系统采购招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><nav>CA办理 我要投标</nav>"
                    "<h1>上海弱电系统采购招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>招标人：上海测试单位</p>"
                    "<p>公告正文：本项目采购弱电系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_extracts_notice_detail_javascript_links(self, mock_request_url):
        list_url = "https://cg.95306.test/"
        detail_url = "https://cg.95306.test/baseinfor/notice/informationShow?id=abc123"

        def fake_request(url):
            if url == list_url:
                return (
                    "<html><body><a onclick=\"noticeDetail('abc123')\">"
                    "上海轨道弱电系统采购公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海轨道弱电系统采购公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购弱电系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write(f"{list_url}\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "gt95306-test",
                        "name": "国铁测试",
                        "entry_url": list_url,
                        "allowed_hosts": ["cg.95306.test"],
                        "detail_url_regex": [r"/baseinfor/notice/informationShow\?id=[A-Za-z0-9_-]+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)

    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_extracts_embedded_json_detail_urls(self, mock_request_url):
        detail_url = "https://www.qianlima.test/bid-610713231.html"

        def fake_request(url):
            if url == "https://www.qianlima.test/zbgg/":
                return (
                    "<html><body><script>window.__NUXT__={state:{bidding:{listData:["
                    "{\"pcUrl\":\"https://www.qianlima.test/bid-610713231.html\","
                    "\"title\":\"上海弱电智能化公开招标公告\"}]}}}</script></body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>上海弱电智能化公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购弱电智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.qianlima.test/zbgg/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "qianlima-test",
                        "name": "千里马测试",
                        "entry_url": "https://www.qianlima.test/",
                        "allowed_hosts": ["www.qianlima.test"],
                        "list_url_regex": [r"/zbgg/?$"],
                        "detail_url_regex": [r"^https://www\.qianlima\.test/bid-\d+\.html$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"site_topologies_path": topology_path},
            )
            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, detail_url)
            self.assertEqual(bids[0].title, "上海弱电智能化公开招标公告")

    @patch.object(UrlListCrawler, "_request_url")
    @patch.object(UrlListCrawler, "_request_url_with_browser")
    def test_browser_auto_does_not_preempt_http_preferred_topology(self, mock_browser, mock_http):
        def fake_http(url):
            if url == "https://example.com/list":
                return (
                    "<html><body><a href='/detail/1'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://example.com/detail/1":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_http.side_effect = fake_http

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/list\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "http-site",
                        "name": "HTTP 优先站",
                        "entry_url": "https://example.com/list",
                        "allowed_hosts": ["example.com"],
                        "preferred_fetch": "http",
                        "list_url_regex": [r"/list$"],
                        "detail_url_regex": [r"/detail/\d+$"],
                    }
                ],
            )

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"browser_backend": {"mode": "browser_auto"}, "site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://example.com/detail/1")
            mock_browser.assert_not_called()

    @patch.object(UrlListCrawler, "_request_url")
    @patch.object(UrlListCrawler, "_request_url_with_browser")
    def test_browser_mode_falls_back_during_topology_crawl_when_http_cannot_parse_links(self, mock_browser, mock_http):
        def fake_http(url):
            if url == "https://example.com/list":
                return ("<html><body><div id='app'></div></body></html>", 200, "OK")
            if url == "https://example.com/notice/1.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_http.side_effect = fake_http
        mock_browser.return_value = (
            "<html><body><a href='/notice/1.html'>上海安防工程公开招标公告</a></body></html>",
            200,
            "Browser",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/list\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"use_selenium": True},
            )

            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://example.com/notice/1.html")
            mock_browser.assert_called_once_with("https://example.com/list")

    @patch.object(UrlListCrawler, "_request_url")
    @patch.object(UrlListCrawler, "_request_url_with_browser")
    def test_browser_mode_falls_back_when_entry_http_raises(self, mock_browser, mock_http):
        mock_http.side_effect = requests.exceptions.Timeout("slow")
        mock_browser.return_value = (
            "<html><body><h1>上海安防工程公开招标公告</h1>"
            "<p>发布时间：2026-07-02</p>"
            "<p>采购单位：上海测试单位</p>"
            "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
            200,
            "Browser",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/detail\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {},
                config={"use_selenium": True},
            )

            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://example.com/detail")
            mock_browser.assert_called_once_with("https://example.com/detail")

    @patch.object(UrlListCrawler, "_request_url")
    @patch.object(UrlListCrawler, "_request_url_with_browser")
    def test_browser_mode_falls_back_when_child_detail_http_raises(self, mock_browser, mock_http):
        def fake_http(url):
            if url == "https://example.com/list":
                return (
                    "<html><body><a href='/detail/1'>上海安防工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://example.com/detail/1":
                raise requests.exceptions.Timeout("slow")
            raise AssertionError(f"unexpected url {url}")

        mock_http.side_effect = fake_http
        mock_browser.return_value = (
            "<html><body><h1>上海安防工程公开招标公告</h1>"
            "<p>发布时间：2026-07-02</p>"
            "<p>采购单位：上海测试单位</p>"
            "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
            200,
            "Browser",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/list\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {"topology_max_depth": 1},
                config={"use_selenium": True},
            )

            bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].url, "https://example.com/detail/1")
            mock_browser.assert_called_once_with("https://example.com/detail/1")

    @patch.object(UrlListCrawler, "_request_url")
    def test_accessible_html_generates_bid_info(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><head><title>上海弱电智能化采购公告</title></head>"
            "<body><h1>上海弱电智能化采购公告</h1><p>发布时间：2026-07-02</p>"
            "<p>本项目包含安防、监控、门禁系统。</p></body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/detail\n")

            bids = self.make_crawler(path, diagnostics_path).crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].title, "上海弱电智能化采购公告")
            self.assertEqual(bids[0].url, "https://example.com/detail")
            self.assertEqual(bids[0].source, "上海招投标URL清单")
            self.assertIn("安防", bids[0].content)
            self.assertIn("original_url: https://example.com/detail", bids[0].content)
            self.assertIn("crawl_timestamp:", bids[0].content)
            self.assertTrue(os.path.exists(diagnostics_path))

    @patch.object(UrlListCrawler, "_request_url")
    def test_failures_are_diagnosed_and_do_not_interrupt_other_urls(self, mock_request_url):
        def fake_request(url):
            if url.endswith("/403"):
                return "", 403, "Forbidden"
            if url.endswith("/timeout"):
                raise requests.exceptions.Timeout("slow")
            return (
                "<html><body><h1>上海信息化公开招标</h1><p>发布时间：2026-07-02</p>"
                "<p>综合布线项目。</p></body></html>",
                200,
                "OK",
            )

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/403\n")
                f.write("https://example.com/timeout\n")
                f.write("https://example.com/detail-ok\n")

            bids = self.make_crawler(path, diagnostics_path).crawl()

            self.assertEqual(len(bids), 1)
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostics = [json.loads(line) for line in f]

            self.assertEqual([d["status"] for d in diagnostics], ["failed", "failed", "success"])
            self.assertIn("HTTP 403/401", diagnostics[0]["reason"])
            self.assertIn("timeout/connection error", diagnostics[1]["reason"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_diagnostics_are_sent_to_log_callback(self, mock_request_url):
        mock_request_url.return_value = "", 403, "Forbidden"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            logs = []
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/403\n")

            self.make_crawler_with_logs(path, diagnostics_path, logs).crawl()

            diagnostic_logs = [line for line in logs if line.startswith("[URL诊断]")]
            self.assertEqual(len(diagnostic_logs), 1)
            self.assertIn("https://example.com/403", diagnostic_logs[0])
            self.assertIn("HTTP 403/401", diagnostic_logs[0])

    def test_cookie_header_is_applied_for_matching_domain_without_logging_secret(self):
        class FakeResponse:
            text = (
                "<html><body><h1>上海弱电公开招标公告</h1>"
                "<p>发布时间：2026-07-02</p></body></html>"
            )
            status_code = 200
            reason = "OK"
            apparent_encoding = "utf-8"
            encoding = "utf-8"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://secure.example.com/detail\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {
                    "auth_cookies": [
                        {
                            "domain": "example.com",
                            "cookie": "SESSION=secret-token",
                            "enabled": True,
                        }
                    ]
                },
            )

            captured_headers = {}

            def fake_get(url, headers, **kwargs):
                captured_headers.update(headers)
                return FakeResponse()

            with patch.object(crawler.session, "get", side_effect=fake_get):
                bids = crawler.crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(captured_headers["Cookie"], "SESSION=secret-token")
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostics_text = f.read()
            self.assertIn('"cookie_used": true', diagnostics_text)
            self.assertNotIn("secret-token", diagnostics_text)

    @patch.object(UrlListCrawler, "_request_url")
    def test_login_or_captcha_pages_get_manual_action_diagnostics(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body>请输入验证码后继续</body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/captcha\n")

            self.make_crawler(path, diagnostics_path).crawl()

            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostic = json.loads(f.readline())
            self.assertIn("验证码/安全验证", diagnostic["reason"])

    @patch.object(UrlListCrawler, "_request_url")
    def test_header_login_link_does_not_mark_public_page_as_blocked(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><body>"
            "<nav><a href='/login'>登录</a><a href='/register'>注册</a></nav>"
            "<ul><li><a href='/notice/1.html'>上海智能化公开招标公告</a>"
            "<span>发布时间：2026-07-01</span></li></ul>"
            "</body></html>",
            200,
            "OK",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/list\n")

            bids = self.make_crawler(path, diagnostics_path).crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].title, "上海智能化公开招标公告")
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostic = json.loads(f.readline())
            self.assertEqual(diagnostic["status"], "success")

    @patch.object(UrlListCrawler, "_request_url")
    def test_user_login_header_does_not_mark_public_portal_as_blocked(self, mock_request_url):
        detail_url = (
            "https://www.sdicc.com.cn/cgxx/ggDetail?"
            "gcGuid=da97f2f1-64ca-4222-9d50-b976b16dbd2b&ggGuid=76cdd52c-8d91-4901-9a83-d28475fc5a6d"
        )

        def fake_request(url):
            if url == "https://www.sdicc.com.cn/":
                return (
                    "<html><head><title>国投集团电子采购平台</title></head><body>"
                    "<header><a href='/login'><span>用户登录</span></a></header>"
                    f"<main><a href='{detail_url}'>智能化工程招标公告</a><span>2026-07-01</span></main>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == detail_url:
                return (
                    "<html><body><h1>智能化工程招标公告</h1>"
                    "<p>发布时间：2026-07-01</p>"
                    "<p>招标人：国投测试单位</p>"
                    "<p>项目编号：GT-2026-001</p>"
                    "<p>公告正文：本项目采购智能化工程服务。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://www.sdicc.com.cn/\n")

            bids = self.make_crawler(path, diagnostics_path).crawl()

            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].title, "智能化工程招标公告")
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostic = json.loads(f.readline())
            self.assertEqual(diagnostic["status"], "success")

    def test_domain_rate_limit_waits_before_revisiting_same_domain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://example.com/a\n")

            crawler = self.make_crawler_with_source_config(
                path,
                diagnostics_path,
                {},
                config={"domain_delay": 10},
            )
            crawler._last_domain_request_at["example.com"] = 100.0

            with patch("crawler.url_list.time.monotonic", return_value=106.0), patch(
                "crawler.url_list.time.sleep"
            ) as mock_sleep:
                crawler._respect_rate_limit("https://example.com/a")

            mock_sleep.assert_called_once_with(4.0)

    def test_classifies_representative_builtin_url_patterns(self):
        crawler = self.make_crawler("missing.txt")

        cases = {
            "http://www.zfcg.sh.gov.cn/": ("home", "public_crawl"),
            "http://www.zfcg.sh.gov.cn/site/detail?articleId=abc": ("detail", "public_crawl"),
            "http://www.ccgp.gov.cn/cggg/dfgg/gkzb/202207/t20220701_18188664.htm": (
                "detail",
                "public_crawl",
            ),
            "https://user.bidcenter.com.cn/v2023/#/des/customDesSearch/421706488": (
                "search",
                "js_rendered_limited",
            ),
            "http://www.sd-portygzc.com/TPBidder/memberLogin": ("login", "requires_login"),
            "https://biaoshu.xiaoxiaoai.cn/home?inviteCode=1": ("home", "low_value_reference"),
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                rule = crawler._classify_url(url)
                self.assertEqual((rule["page_type"], rule["handling"]), expected)
                self.assertTrue(rule["reason"])

    def test_detail_page_extracts_structured_fields_contacts_and_stage_metadata(self):
        html = """
        <html><head><title>旧标题</title></head><body>
          <div class="breadcrumb">首页 &gt; 政府采购 &gt; 中标公告</div>
          <article class="article-content">
            <h1>上海市弱电智能化系统中标公告</h1>
            <p>发布时间：2026年7月1日 来源：上海市政府采购中心</p>
            <p>采购人：上海市示范单位</p>
            <p>项目联系人：张三、李四 联系电话：021-12345678-801；13800138000</p>
            <p>项目负责人：王五 负责人电话：(021)87654321 邮箱：owner@example.com</p>
            <p>正文内容：本项目包含安防、监控、门禁和综合布线系统。</p>
          </article>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("http://www.zfcg.sh.gov.cn/site/detail?articleId=abc\n")

            crawler = self.make_crawler(path)
            bids = crawler._parse_page(
                html,
                "http://www.zfcg.sh.gov.cn/site/detail?articleId=abc",
                "2026-07-02T10:00:00",
            )

        self.assertEqual(len(bids), 1)
        bid = bids[0]
        self.assertEqual(bid.title, "上海市弱电智能化系统中标公告")
        self.assertEqual(bid.publish_date, "2026-07-01")
        self.assertEqual(bid.purchaser, "上海市示范单位")
        self.assertIn("publisher: 上海市政府采购中心", bid.content)
        self.assertIn("contact_person: 张三；李四", bid.content)
        self.assertIn("contact_phone: 021-12345678-801；13800138000", bid.content)
        self.assertIn("responsible_person: 王五", bid.content)
        self.assertIn("responsible_phone: (021)87654321；owner@example.com", bid.content)
        self.assertIn("project_stage: 中标公告", bid.content)
        self.assertIn("正文内容：本项目包含安防、监控、门禁和综合布线系统。", bid.content)

    def test_search_or_list_page_extracts_relevant_links_with_dates_and_stage(self):
        html = """
        <html><body>
          <nav><a href="/login">登录</a><a href="/help">帮助中心</a></nav>
          <ul class="list">
            <li><a href="/notice/1.html">上海弱电智能化公开招标公告</a><span>2026/07/01</span></li>
            <li><a href="/policy.html">政策法规下载中心</a><span>2026/07/01</span></li>
            <li><a href="javascript:void(0)">采购公告</a></li>
            <li><a href="/notice/2.html">综合布线项目更正公告</a><span>2026.07.02</span></li>
          </ul>
        </body></html>
        """

        crawler = self.make_crawler("missing.txt")
        bids = crawler._parse_page(html, "http://www.ccgp.gov.cn/cggg/dfgg/", "2026-07-02T10:00:00")

        self.assertEqual([bid.title for bid in bids], ["上海弱电智能化公开招标公告", "综合布线项目更正公告"])
        self.assertEqual(bids[0].url, "http://www.ccgp.gov.cn/notice/1.html")
        self.assertEqual(bids[0].publish_date, "2026-07-01")
        self.assertIn("project_stage: 招标公告", bids[0].content)
        self.assertIn("page_type: list", bids[0].content)
        self.assertEqual(bids[1].publish_date, "2026-07-02")
        self.assertIn("project_stage: 更正公告", bids[1].content)

    def test_policy_links_are_ignored_and_link_stage_prefers_title(self):
        html = """
        <html><body>
          <div class="home">
            <span>政府采购意向 采购计划</span>
            <a href="/news/1.html">《政府采购法》修订草案公布 即日起征求意见</a>
            <a href="/news/2.html">财政部：在政府采购活动中对供应商采取措施</a>
            <a href="/notice/2.html">上海智能化公开招标公告</a><span>2026-07-01</span>
          </div>
        </body></html>
        """

        crawler = self.make_crawler("missing.txt")
        bids = crawler._parse_page(html, "http://www.ccgp.gov.cn/", "2026-07-02T10:00:00")

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].title, "上海智能化公开招标公告")
        self.assertIn("project_stage: 招标公告", bids[0].content)
        self.assertNotIn("project_stage: 政府采购意向", bids[0].content)

    def test_masked_commercial_contact_values_are_not_saved_as_people(self):
        html = """
        <html><body>
          <h1>弱电工程（会议系统）</h1>
          <p>发布时间：2026-05-30</p>
          <p>采购人：上海某单位 采购项目名称：弱电工程（会议系统） 预算金额：491万元</p>
          <p>联系人：点击查看 代理联系人 报名截止时间 投标截止时间 标书代写 关键信息</p>
          <p>电话：点击查看</p>
        </body></html>
        """

        crawler = self.make_crawler("missing.txt")
        bids = crawler._parse_page(html, "https://www.qianlima.com/bid-601407680.html", "2026-07-02T10:00:00")

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].purchaser, "上海某单位")
        self.assertNotIn("contact_person:", bids[0].content)
        self.assertNotIn("contact_phone:", bids[0].content)

    def test_public_json_api_records_are_parsed_into_bid_info(self):
        payload = json.dumps(
            {
                "data": {
                    "records": [
                        {
                            "title": "上海智能化设备采购意向",
                            "url": "/api/detail/1",
                            "publishDate": "2026-07-01 10:30",
                            "purchaser": "上海采购人",
                            "content": "联系人：赵六 电话：021-11112222",
                            "noticeType": "政府采购意向",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        )

        crawler = self.make_crawler("missing.txt")
        bids = crawler._parse_page(payload, "https://example.com/api/list", "2026-07-02T10:00:00")

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].title, "上海智能化设备采购意向")
        self.assertEqual(bids[0].url, "https://example.com/api/detail/1")
        self.assertEqual(bids[0].publish_date, "2026-07-01")
        self.assertEqual(bids[0].purchaser, "上海采购人")
        self.assertIn("contact_person: 赵六", bids[0].content)
        self.assertIn("contact_phone: 021-11112222", bids[0].content)
        self.assertIn("project_stage: 政府采购意向", bids[0].content)

    @patch.object(UrlListCrawler, "_request_url")
    def test_requires_login_url_is_diagnosed_without_fetching(self, mock_request_url):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("https://cooperation.ceic.com/login/index\n")

            bids = self.make_crawler(path, diagnostics_path).crawl()

            self.assertEqual(bids, [])
            mock_request_url.assert_not_called()
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                diagnostic = json.loads(f.readline())
            self.assertEqual(diagnostic["status"], "skipped_with_reason")
            self.assertEqual(diagnostic["page_type"], "login")
            self.assertEqual(diagnostic["handling"], "requires_login")

    def test_builtin_url_list_all_have_processing_conclusions_when_available(self):
        real_list = "/Users/cervine/Documents/Rule-Project/projects/opportunity-collection/output/materials/bid_related_url_list.txt"
        if not os.path.exists(real_list):
            self.skipTest("built-in URL list is not available on this machine")

        crawler = self.make_crawler(real_list)
        urls = crawler.get_list_urls()
        self.assertGreater(len(urls), 0)
        self.assertEqual(len(urls), len(set(urls)))

        classifications = [crawler._classify_url(url) for url in urls]
        self.assertTrue(all(item["platform"] for item in classifications))
        self.assertTrue(all(item["page_type"] for item in classifications))
        self.assertTrue(all(item["handling"] for item in classifications))
        self.assertTrue(all(item["reason"] for item in classifications))
        self.assertIn("requires_login", {item["handling"] for item in classifications})
        self.assertIn("js_rendered_limited", {item["handling"] for item in classifications})
        self.assertIn("commercial_limited", {item["handling"] for item in classifications})
        self.assertIn("low_value_reference", {item["handling"] for item in classifications})


if __name__ == "__main__":
    unittest.main()
