import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "server" / "static"


class StaticFrontendAssetsTests(unittest.TestCase):
    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def test_index_uses_external_static_assets(self):
        html = self.read("index.html")

        self.assertIn('<link rel="stylesheet" href="/static/styles.css">', html)
        self.assertIn('<script defer src="/static/app.js"></script>', html)
        self.assertNotIn("<style>", html)
        self.assertNotIn("</style>", html)
        self.assertNotIn("<script>\n        const API", html)

    def test_design_tokens_are_applied_without_shadows_or_negative_tracking(self):
        css = self.read("styles.css")

        required_tokens = {
            "--primary": "#f54e00",
            "--primary-active": "#d04200",
            "--ink": "#26251e",
            "--body": "#5a5852",
            "--canvas": "#f7f7f4",
            "--canvas-soft": "#fafaf7",
            "--surface-card": "#ffffff",
            "--hairline": "#e6e5e0",
            "--semantic-success": "#1f8a65",
            "--semantic-error": "#cf2d56",
        }
        for token, value in required_tokens.items():
            self.assertRegex(css, rf"{re.escape(token)}:\s*{re.escape(value)}\b")

        self.assertNotIn("box-shadow", css)
        self.assertNotRegex(css, r"letter-spacing:\s*-")
        self.assertRegex(css, r"--font-mono:\s*'JetBrains Mono'")

    def test_behavioral_dom_contract_is_preserved(self):
        html = self.read("index.html")

        for element_id in [
            "statusDot",
            "statusText",
            "nextRun",
            "todayNew",
            "todayRounds",
            "totalBids",
            "countdownBox",
            "countdownValue",
            "progressBox",
            "progressText",
            "progressBar",
            "progressSite",
            "btnStart",
            "btnStop",
            "logsContainer",
            "resultsList",
            "sitesList",
            "customSitesList",
            "contactsList",
            "cfgKeywords",
            "cfgExclude",
            "cfgMustContain",
            "cfgInterval",
            "cfgSelenium",
            "contactModal",
            "smsModal",
            "voiceModal",
            "aiModal",
            "customSiteModal",
        ]:
            self.assertIn(f'id="{element_id}"', html)

    def test_app_js_keeps_spa_behavior_without_global_event_dependency(self):
        js = self.read("app.js")

        self.assertIn("function showPage", js)
        self.assertNotIn("event.target", js)
        self.assertIn("loadResults()", js)
        self.assertIn("loadConfig()", js)
        self.assertIn("loadSites()", js)
        self.assertIn("loadContacts()", js)
        self.assertIn("setInterval(refreshStatus, 5000)", js)
        self.assertIn("setInterval(loadLogs, 5000)", js)
        self.assertIn("isNearBottom", js)
        self.assertIn("safeResultUrl", js)

    def test_inline_style_and_selenium_toggle_regressions_stay_out(self):
        html = self.read("index.html")
        js = self.read("app.js")

        self.assertNotIn('style="', html)
        self.assertNotIn('style="', js)
        self.assertIn('<div class="toggle-switch"><span>🌐 Selenium浏览器模式</span>', html)
        self.assertNotIn('onclick="showSmsConfig()"><span>🌐 Selenium浏览器模式</span>', html)
        self.assertIn("empty-state-compact", js)

    def test_html_and_script_contracts_match_mechanically(self):
        html = self.read("index.html")
        js = self.read("app.js")

        defined_functions = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", js))
        onclick_handlers = re.findall(r'onclick="([^"]+)"', html)
        called_handlers = {
            name
            for handler in onclick_handlers
            for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", handler)
        }

        self.assertTrue(called_handlers)
        self.assertFalse(called_handlers - defined_functions)

        html_ids = set(re.findall(r'id="([^"]+)"', html))
        looked_up_ids = set(re.findall(r"getElementById\('([^']+)'\)", js))

        self.assertTrue(looked_up_ids)
        self.assertFalse(looked_up_ids - html_ids)


if __name__ == "__main__":
    unittest.main()
