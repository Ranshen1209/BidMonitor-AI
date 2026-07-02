import json
import os
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

    @patch.object(UrlListCrawler, "_request_url")
    def test_accessible_html_generates_bid_info(self, mock_request_url):
        mock_request_url.return_value = (
            "<html><head><title>上海弱电智能化采购公告</title></head>"
            "<body><h1>上海弱电智能化采购公告</h1><p>本项目包含安防、监控、门禁系统。</p></body></html>",
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
                "<html><body><h1>上海信息化公开招标</h1><p>综合布线项目。</p></body></html>",
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
                f.write("https://example.com/ok\n")

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

            self.assertEqual(len(logs), 1)
            self.assertIn("https://example.com/403", logs[0])
            self.assertIn("HTTP 403/401", logs[0])

    def test_cookie_header_is_applied_for_matching_domain_without_logging_secret(self):
        class FakeResponse:
            text = "<html><body><h1>上海弱电公开招标公告</h1></body></html>"
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
            "<ul><li><a href='/notice/1.html'>上海智能化公开招标公告</a><span>2026-07-01</span></li></ul>"
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
        mock_request_url.return_value = (
            "<html><head><title>国投集团电子采购平台</title></head><body>"
            "<header><a href='/login'><span>用户登录</span></a></header>"
            "<main><a href='/notice/1.html'>智能化工程招标公告</a><span>2026-07-01</span></main>"
            "</body></html>",
            200,
            "OK",
        )

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
