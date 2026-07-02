import unittest
from unittest.mock import Mock, patch

from src.results.detail_fetcher import fetch_detail_text


class DetailFetcherTests(unittest.TestCase):
    @patch("src.results.detail_fetcher.requests.get")
    def test_http_blocked_detail_body_is_rejected(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.apparent_encoding = "utf-8"
        response.encoding = "utf-8"
        response.text = (
            "<html><body><h1>上海安防工程招标公告</h1>"
            "<p>请输入验证码后继续访问，算数结果 doVerify.php。</p>"
            "<p>这是一段足够长的受限页面文本，用来证明不能只凭长度就进入 AI 抽取流程。</p>"
            "</body></html>"
        )
        mock_get.return_value = response

        ok, text, error = fetch_detail_text("https://example.com/detail")

        self.assertFalse(ok)
        self.assertEqual(text, "")
        self.assertIn("blocked", error)

    @patch("src.results.detail_fetcher._fetch_detail_html_with_browser")
    @patch("src.results.detail_fetcher.requests.get")
    def test_browser_blocked_detail_body_is_rejected(self, mock_get, mock_browser):
        response = Mock()
        response.status_code = 500
        response.reason = "Server Error"
        mock_get.return_value = response
        mock_browser.return_value = (
            True,
            "<html><body><h1>上海安防工程招标公告</h1>"
            "<p>登录即可免费查看完整信息，请先登录。</p>"
            "<p>这是一段足够长的会员遮蔽页面文本，不能进入 AI 抽取流程。</p>"
            "</body></html>",
            None,
        )

        ok, text, error = fetch_detail_text(
            "https://example.com/detail",
            fetch_config={"use_selenium": True, "browser_backend": {"mode": "browser_auto"}},
        )

        self.assertFalse(ok)
        self.assertEqual(text, "")
        self.assertIn("blocked", error)

    @patch("src.results.detail_fetcher.requests.get")
    def test_public_detail_body_is_accepted(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.apparent_encoding = "utf-8"
        response.encoding = "utf-8"
        response.text = (
            "<html><body><h1>上海安防工程公开招标公告</h1>"
            "<p>项目编号：ABC-001</p><p>采购单位：上海测试单位</p>"
            "<p>公告正文：本项目采购安防监控系统，预算金额 120 万元。"
            "投标人应按招标文件要求提交响应文件，项目包含视频监控、门禁、综合布线和平台集成服务。</p>"
            "</body></html>"
        )
        mock_get.return_value = response

        ok, text, error = fetch_detail_text("https://example.com/detail")

        self.assertTrue(ok)
        self.assertIn("上海安防工程公开招标公告", text)
        self.assertIsNone(error)

    @patch("src.results.detail_fetcher._fetch_detail_html_with_browser")
    @patch("src.results.detail_fetcher.requests.get")
    def test_browser_auto_prefers_browser_before_http(self, mock_get, mock_browser):
        mock_browser.return_value = (
            True,
            "<html><body><h1>上海安防工程公开招标公告</h1>"
            "<p>项目编号：ABC-001</p><p>采购单位：上海测试单位</p>"
            "<p>公告正文：本项目采购安防监控系统，预算金额 120 万元。"
            "投标人应按招标文件要求提交响应文件，项目包含视频监控、门禁、综合布线和平台集成服务。</p>"
            "</body></html>",
            None,
        )

        ok, text, error = fetch_detail_text(
            "https://example.com/detail",
            fetch_config={"browser_backend": {"mode": "browser_auto"}},
        )

        self.assertTrue(ok)
        self.assertIn("上海安防工程公开招标公告", text)
        self.assertIsNone(error)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
