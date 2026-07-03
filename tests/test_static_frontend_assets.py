import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "server" / "static"
UI_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")


class StaticFrontendAssetsTests(unittest.TestCase):
    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def css_block_after(self, css, marker, stop_marker):
        start = css.index(marker)
        stop = css.index(stop_marker, start)
        return css[start:stop]

    def test_index_uses_external_static_assets(self):
        html = self.read("index.html")

        self.assertRegex(html, r'<link rel="stylesheet" href="/static/styles\.css\?v=[^"]+">')
        self.assertRegex(html, r'<script defer src="/static/app\.js\?v=[^"]+"></script>')
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
        self.assertNotIn("linear-gradient", css)
        self.assertNotIn("radial-gradient", css)
        self.assertNotRegex(css, r"letter-spacing:\s*-")
        self.assertRegex(css, r"--font-mono:\s*'JetBrains Mono'")

    def test_action_buttons_keep_orange_as_the_only_filled_cta_color(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn('class="btn btn-primary" id="btnStart"', html)
        self.assertIn('class="btn btn-outline btn-stop" id="btnStop"', html)
        self.assertNotIn("btn btn-success", html)
        self.assertNotIn("btn btn-danger", html)
        self.assertNotIn("btn btn-success", js)
        self.assertNotIn("btn btn-sm btn-danger", js)
        self.assertNotRegex(css, r"\.btn-success\s*\{")
        self.assertNotRegex(css, r"\.btn-danger\s*\{")
        self.assertNotRegex(css, r"\.btn-stop\s*\{[^}]*var\(--semantic-error\)")
        self.assertNotRegex(css, r"\.btn-stop\s*\{[^}]*var\(--error-border\)")

    def test_cards_use_design_card_radius_while_controls_stay_compact(self):
        css = self.read("styles.css")

        self.assertRegex(css, r"\.card\s*\{[^}]*border-radius:\s*var\(--radius-lg\)")
        self.assertRegex(css, r"\.login-panel\s*\{[^}]*border-radius:\s*var\(--radius-lg\)")
        self.assertRegex(css, r"\.btn\s*\{[^}]*border-radius:\s*var\(--radius-md\)")
        self.assertRegex(css, r"\.config-input\s*\{[^}]*border-radius:\s*var\(--radius-md\)")

    def test_desktop_nav_padding_does_not_shift_login_and_mobile_nav_uses_safe_area(self):
        css = self.read("styles.css")

        desktop_css = self.css_block_after(
            css,
            "@media (min-width: 900px)",
            "@media (max-width: 1100px)",
        )
        self.assertNotRegex(desktop_css, r"body\s*\{[^}]*padding-left:\s*var\(--nav-rail-width\)")
        self.assertRegex(desktop_css, r"\.app-shell\.active\s*\{[^}]*padding-left:\s*var\(--nav-rail-width\)")

        mobile_query = re.search(r"@media\s*\(max-width:\s*720px\)\s*\{(?P<body>.*?)(?:\n\}\n\n@media|\Z)", css, re.S)
        self.assertIsNotNone(mobile_query)
        mobile_css = mobile_query.group("body")
        self.assertRegex(mobile_css, r"\.nav-tabs\s*\{[^}]*padding-bottom:\s*env\(safe-area-inset-bottom\)")

        narrow_query = re.search(r"@media\s*\(max-width:\s*520px\)\s*\{(?P<body>.*?)(?:\n\}\n\n@media|\Z)", css, re.S)
        self.assertIsNotNone(narrow_query)
        narrow_css = narrow_query.group("body")
        self.assertRegex(narrow_css, r"body\s*\{[^}]*padding-bottom:\s*calc\(70px \+ env\(safe-area-inset-bottom\)\)")

    def test_desktop_sidebar_has_brand_and_collapsed_state_contract(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn('class="nav-brand"', html)
        self.assertIn('class="nav-brand-title"', html)
        self.assertIn('class="nav-brand-subtitle"', html)
        self.assertIn('id="sidebarCollapseButton"', html)
        self.assertIn('onclick="toggleSidebarCollapse()"', html)
        for label in ["BidMonitor", "招标信息监控系统"]:
            self.assertIn(label, html)

        self.assertIn("SIDEBAR_COLLAPSED_KEY", js)
        self.assertIn("function applySidebarCollapsedState", js)
        self.assertIn("function toggleSidebarCollapse", js)
        self.assertIn("localStorage.getItem(SIDEBAR_COLLAPSED_KEY)", js)
        self.assertIn("localStorage.setItem(SIDEBAR_COLLAPSED_KEY", js)
        self.assertIn("checkAuth()", js)

        self.assertRegex(css, r"--nav-sidebar-width:\s*184px")
        self.assertRegex(css, r"--nav-sidebar-collapsed-width:\s*72px")
        self.assertRegex(css, r"\.app-shell\.nav-collapsed\.active\s*\{[^}]*padding-left:\s*var\(--nav-sidebar-collapsed-width\)")
        self.assertRegex(css, r"\.app-shell\.nav-collapsed\s+\.nav-tabs\s*\{[^}]*width:\s*var\(--nav-sidebar-collapsed-width\)")
        self.assertRegex(css, r"\.app-shell\.nav-collapsed\s+\.nav-label")
        self.assertRegex(css, r"\.nav-brand\s*\{")
        self.assertRegex(css, r"\.nav-list\s*\{")

    def test_results_layout_wraps_filters_without_page_overflow(self):
        css = self.read("styles.css")

        self.assertRegex(css, r"\.result-filter-bar\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(140px,\s*1fr\)\)")
        self.assertRegex(css, r"\.filter-search\s*\{[^}]*grid-column:\s*span\s+2")
        self.assertRegex(css, r"\.result-filter-action\s*\{[^}]*width:\s*100%")
        self.assertRegex(css, r"\.results-shell\s*\{[^}]*width:\s*100%")
        self.assertRegex(css, r"\.results-shell\s*\{[^}]*min-width:\s*0")
        self.assertRegex(css, r"\.results-table-wrap\s*\{[^}]*width:\s*100%")
        self.assertRegex(css, r"\.results-table-wrap\s*\{[^}]*min-width:\s*0")
        self.assertRegex(css, r"\.result-detail-modal\s*\{[^}]*align-items:\s*center")
        self.assertRegex(css, r"\.result-detail-panel\s*\{[^}]*max-height:\s*calc\(100vh - 48px\)")

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
            "copyLogsButton",
            "logsContainer",
            "resultFilterBar",
            "resultsTableBody",
            "resultDetailModal",
            "resultDetailPanel",
            "bulkReviewModal",
            "bulkFitStatus",
            "bulkFollowDecision",
            "bulkUrgency",
            "bulkProjectStage",
            "bulkNonFollowReasons",
            "sitesList",
            "cfgKeywords",
            "cfgExclude",
            "cfgMustContain",
            "cfgInterval",
            "cfgSelenium",
            "smsModal",
            "voiceModal",
            "aiModal",
            "aiEndpointType",
            "loginView",
            "appShell",
            "loginForm",
            "loginUsername",
            "loginPassword",
            "loginError",
            "currentUserLabel",
            "usersList",
            "userModal",
        ]:
            self.assertIn(f'id="{element_id}"', html)

    def test_app_js_keeps_spa_behavior_without_global_event_dependency(self):
        js = self.read("app.js")

        self.assertIn("function showPage", js)
        self.assertNotIn("event.target", js)
        self.assertIn("loadResults()", js)
        self.assertIn("loadConfig()", js)
        self.assertIn("loadSites()", js)
        self.assertIn("setInterval(refreshStatus, 5000)", js)
        self.assertIn("setInterval(loadLogs, 5000)", js)
        self.assertIn("isNearBottom", js)
        self.assertIn("safeResultUrl", js)
        self.assertIn("checkAuth()", js)
        self.assertIn("/api/auth/me", js)
        self.assertIn("/api/auth/login", js)
        self.assertIn("/api/auth/logout", js)

    def test_logs_panel_can_copy_visible_logs(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn('id="copyLogsButton"', html)
        self.assertIn('onclick="copyLogs()"', html)
        self.assertIn('<use href="#icon-copy"></use>', html)
        self.assertIn("function getLogTextForCopy", js)
        self.assertIn("document.querySelectorAll('#logsContainer .log-line')", js)
        self.assertIn("navigator.clipboard.writeText", js)
        self.assertIn("function copyLogs", js)
        self.assertIn("const LOG_FETCH_LIMIT = 2000", js)
        self.assertIn("lastLogsSignature", js)
        self.assertIn(".log-actions", css)
        self.assertIn(".clipboard-buffer", css)

    def test_frontend_has_in_app_login_and_lightweight_user_management(self):
        html = self.read("index.html")
        js = self.read("app.js")

        self.assertIn('id="loginView"', html)
        self.assertIn('id="appShell"', html)
        self.assertIn('onsubmit="login(event)"', html)
        self.assertIn('data-admin-only', html)
        self.assertIn('id="page-users"', html)
        self.assertIn('onclick="logout()"', html)
        self.assertIn("function renderUsers", js)
        self.assertIn("function showAppShell", js)
        self.assertIn("currentUser && currentUser.role === 'admin'", js)

    def test_inline_style_and_selenium_toggle_regressions_stay_out(self):
        html = self.read("index.html")
        js = self.read("app.js")

        self.assertNotIn('style="', html)
        self.assertNotIn('style="', js)
        self.assertIn('<div class="toggle-switch"><span>浏览器模式</span>', html)
        self.assertIn("CloakBrowser", html)
        self.assertNotIn('onclick="showSmsConfig()"><span>浏览器模式</span>', html)
        self.assertIn("empty-state-compact", js)

    def test_builtin_sites_support_metadata_management_contract(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        self.assertIn("site-management-list", html)
        self.assertIn("siteAccessStatus", js)
        self.assertIn("site-note", js)
        self.assertIn("ACCESS_STATUS_OPTIONS", js)
        self.assertIn("function renderSiteAccessOptions", js)
        self.assertIn("const canManageSites = currentUser && currentUser.role === 'admin'", js)
        self.assertIn("disabledAttr", js)
        self.assertIn('data-admin-only onclick="saveSites()"', html)
        self.assertIn("JSON.stringify({ sites: currentSites.map", js)
        for field in [
            "key",
            "enabled",
            "display_name",
            "access_status",
            "requires_login",
            "has_antibot",
            "note",
            "last_checked_at",
            "last_diagnostic",
        ]:
            self.assertIn(field, js)
        self.assertNotIn("const enabledSites = currentSites.filter", js)

        for selector in [
            ".site-management-list",
            ".site-row",
            ".site-field",
            ".site-note",
        ]:
            self.assertIn(selector, css)

    def test_search_config_lives_above_builtin_sites(self):
        html = self.read("index.html")

        page_sites_start = html.index('<div id="page-sites" class="page">')
        page_config_start = html.index('<div id="page-config" class="page">')
        page_sites_html = html[page_sites_start:page_config_start]

        self.assertIn('<span>搜索配置</span>', page_sites_html)
        self.assertIn('<span>内置网站</span>', page_sites_html)
        self.assertLess(
            page_sites_html.index('<span>搜索配置</span>'),
            page_sites_html.index('<span>内置网站</span>'),
        )
        self.assertIn('id="cfgKeywords"', page_sites_html)
        self.assertIn('id="cfgExclude"', page_sites_html)
        self.assertIn('id="cfgMustContain"', page_sites_html)
        self.assertIn('id="cfgInterval"', page_sites_html)
        self.assertIn('id="cfgSelenium"', page_sites_html)
        self.assertNotIn('id="cfgKeywords"', html[page_config_start:])

    def test_site_access_status_options_match_backend_contract(self):
        js = self.read("app.js")

        for value in [
            "public_no_antibot",
            "login_no_antibot",
            "login_with_antibot",
            "js_limited",
            "commercial_limited",
            "unavailable",
            "unknown",
        ]:
            self.assertIn(value, js)
        for stale_value in ["value: 'ok'", "value: 'limited'", "value: 'blocked'"]:
            self.assertNotIn(stale_value, js)

    def test_results_center_table_contract(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        for header in [
            "项目名称",
            "适合性",
            "跟进决策",
            "紧急度",
            "项目阶段",
            "单位",
            "金额",
            "地区",
            "分类",
            "报名/文件截止",
            "投标截止",
            "开标时间",
            "AI状态",
            "来源",
        ]:
            self.assertIn(header, html)
        for hook in ["resultsTableBody", "resultDetailModal", "resultDetailPanel", "bulkReviewModal", "resultFilterBar"]:
            self.assertIn(f'id="{hook}"', html)
        for fn in [
            "loadResultSettings",
            "loadResults",
            "renderResultsTable",
            "openResultDetail",
            "closeResultDetail",
            "saveResultReview",
            "openBulkReview",
            "saveBulkReview",
        ]:
            self.assertIn(f"function {fn}", js)
        for endpoint in ["/api/result-settings", "/api/results/bulk-review", "/api/results/"]:
            self.assertIn(endpoint, js)
        self.assertIn('onclick="openResultDetail(${item.id})"', js)
        self.assertIn('onclick="event.stopPropagation()"', js)
        self.assertIn('onclick="event.stopPropagation(); openResultDetail(${item.id})"', js)
        self.assertIn('rel="noopener noreferrer" onclick="event.stopPropagation()"', js)
        for selector in [".results-table", ".result-detail-panel", ".bulk-review-grid", ".result-filter-bar"]:
            self.assertIn(selector, css)

    def test_detail_panel_compares_ai_manual_and_resolved_values(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        for hook in [
            "detailFieldComparison",
            "detailResolvedFields",
            "detailManualFields",
        ]:
            self.assertIn(hook, html + js)

        for label in ["字段", "AI原始值", "人工修正值", "最终值"]:
            self.assertIn(label, html + js)

        for key in [
            "organization",
            "amount",
            "amount_unit",
            "region",
            "category",
            "registration_deadline",
            "submission_deadline",
            "bid_opening_time",
        ]:
            self.assertIn(key, js)

        self.assertIn("manual_overrides", js)
        self.assertIn("ai_extracted_data", js)
        self.assertIn("detail.deadlines", js)
        self.assertIn(".detail-field-comparison", css)

    def test_detail_panel_reads_array_shaped_ai_deadlines_by_type(self):
        js = self.read("app.js")

        self.assertIn("Array.isArray(deadlines)", js)
        self.assertRegex(
            js,
            r"registration_deadline[\s\S]*registration[\s\S]*document_deadline[\s\S]*file_deadline",
        )
        self.assertRegex(
            js,
            r"submission_deadline[\s\S]*submission[\s\S]*bid_submission_deadline",
        )
        self.assertRegex(
            js,
            r"bid_opening_time[\s\S]*bid_opening[\s\S]*opening_time",
        )
        self.assertRegex(js, r"\.type\s*===\s*deadlineType")
        self.assertRegex(js, r"\.end_at\s*\|\|\s*[^;]+\.start_at\s*\|\|\s*[^;]+\.raw_text")

    def test_manual_field_save_only_patches_changed_manual_overrides(self):
        js = self.read("app.js")

        self.assertIn("activeDetailManualOverrides", js)
        self.assertIn("collectChangedManualOverrides", js)
        self.assertRegex(js, r"manualOverrides\s*=\s*detail\.manual_overrides\s*\|\|\s*\{\}")
        self.assertRegex(js, r"if\s*\(\s*value\s*!==\s*originalValue\s*\)")
        self.assertRegex(js, r"if\s*\(\s*!Object\.keys\(payload\)\.length\s*\)")

        save_match = re.search(
            r"async function saveResultFields\(id\)\s*\{(?P<body>.*?)\n\}",
            js,
            re.S,
        )
        self.assertIsNotNone(save_match)
        save_body = save_match.group("body")
        self.assertIn("collectChangedManualOverrides()", save_body)
        self.assertNotIn("organization: document.getElementById('detailOrganization')", save_body)
        self.assertNotIn("amount: document.getElementById('detailAmount')", save_body)

    def test_bulk_review_can_explicitly_clear_non_follow_reasons(self):
        html = self.read("index.html")
        js = self.read("app.js")

        self.assertIn('id="bulkApplyReasons"', html)
        self.assertIn("bulkApplyReasons", js)
        self.assertIn("payload.update.non_follow_reasons = reasons", js)
        self.assertRegex(js, r"if\s*\(\s*applyReasons\s*\)\s*\{[^}]*payload\.update\.non_follow_reasons\s*=\s*reasons", re.S)
        self.assertRegex(js, r"follow_decision'\)\.value\s*===\s*'not_follow'|payload\.update\.follow_decision\s*===\s*'not_follow'")

    def test_removed_colleague_entry_points_are_not_visible(self):
        html = self.read("index.html")
        js = self.read("app.js")

        self.assertNotIn('data-page="contacts"', html)
        self.assertNotIn('id="page-contacts"', html)
        self.assertNotIn('id="contactModal"', html)
        self.assertNotIn('id="customSiteModal"', html)
        self.assertNotIn("showAddCustomSite", js)
        self.assertNotIn("/api/custom-sites", js)
        self.assertNotIn("loadContacts()", js)
        self.assertNotIn("showSmsConfig()", html)
        self.assertNotIn("showVoiceConfig()", html)

    def test_frontend_uses_svg_icons_instead_of_emoji(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        for filename, source in {"index.html": html, "app.js": js}.items():
            with self.subTest(filename=filename):
                self.assertIsNone(UI_EMOJI_RE.search(source))

        self.assertIn('class="icon-sprite"', html)
        self.assertIn("<symbol id=\"icon-search\"", html)
        self.assertIn("<use href=\"#icon-", html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn(".icon {", css)
        self.assertIn(".status-badge", css)

    def test_index_links_svg_favicon_with_search_artwork(self):
        html = self.read("index.html")

        self.assertIn('<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">', html)

        favicon = self.read("favicon.svg")
        self.assertIn("<svg", favicon)
        self.assertRegex(favicon, r"<svg[^>]+viewBox=\"0 0 32 32\"")
        self.assertIn("<circle", favicon)
        self.assertIn("<path", favicon)
        self.assertNotIn("<script", favicon)
        self.assertIsNone(UI_EMOJI_RE.search(favicon))

    def test_frontend_has_desktop_and_mobile_responsive_layout_contracts(self):
        html = self.read("index.html")
        css = self.read("styles.css")
        js = self.read("app.js")

        self.assertIn('class="container dashboard-grid"', html)
        self.assertIn('class="container content-grid sites-layout"', html)
        self.assertIn('class="container content-grid config-layout"', html)
        self.assertIn('class="config-column config-main-column"', html)
        self.assertIn('class="config-column config-side-column"', html)
        self.assertRegex(html, r'class="[^"]*\bsites-save-fab\b[^"]*"')
        self.assertRegex(html, r'<button class="sites-save-fab btn btn-primary"[^>]+aria-label="保存网站配置"')
        self.assertIn('<span class="fab-label">保存</span>', html)
        self.assertNotIn("<span>保存网站配置</span>", html)
        self.assertNotIn('保存网站配置</span></button>\n            </div>', html)
        self.assertNotIn('empty-state empty-state-compact', js)
        for panel_class in ["panel-stats", "panel-control", "panel-logs"]:
            self.assertIn(panel_class, html)

        self.assertRegex(css, r"@media\s*\(min-width:\s*900px\)")
        desktop_css = self.css_block_after(
            css,
            "@media (min-width: 900px)",
            "@media (max-width: 1100px)",
        )

        self.assertRegex(desktop_css, r"\.dashboard-grid\s*\{[^}]*display:\s*grid")
        self.assertRegex(desktop_css, r"\.dashboard-grid\s*\{[^}]*grid-template-columns:")
        self.assertRegex(desktop_css, r"\.panel-stats\s*\{[^}]*grid-column:")
        self.assertRegex(desktop_css, r"\.panel-logs\s*\{[^}]*grid-column:")
        self.assertRegex(desktop_css, r"\.app-shell\.active\s*\{[^}]*padding-left:\s*var\(--nav-rail-width\)")
        self.assertRegex(desktop_css, r"\.nav-tabs\s*\{[^}]*top:\s*0")
        self.assertRegex(desktop_css, r"\.nav-tabs\s*\{[^}]*left:\s*0")
        self.assertRegex(desktop_css, r"\.nav-tabs\s*\{[^}]*width:\s*var\(--nav-rail-width\)")
        self.assertRegex(desktop_css, r"\.nav-tabs\s*\{[^}]*flex-direction:\s*column")
        self.assertRegex(desktop_css, r"\.nav-tab\s*\{[^}]*flex-direction:\s*row")
        self.assertRegex(desktop_css, r"#page-sites\.active\s*\{[^}]*min-height:\s*calc\(100vh - var\(--app-chrome-height\)\)")
        self.assertRegex(desktop_css, r"\.content-grid\s*\{[^}]*grid-template-columns:\s*1fr")
        self.assertRegex(desktop_css, r"\.sites-layout\s*\{[^}]*grid-template-columns:\s*1fr")
        self.assertRegex(desktop_css, r"#page-sites\s*>\s*\.sites-layout\s*\{[^}]*width:\s*min\(100%,\s*var\(--content-wide-max\)\)")
        self.assertRegex(desktop_css, r"#page-sites\s*>\s*\.sites-layout\s*\{[^}]*min-height:\s*calc\(100vh - var\(--app-chrome-height\)\)")
        self.assertRegex(desktop_css, r"#page-sites\s*>\s*\.sites-layout\s*\{[^}]*align-items:\s*start")
        self.assertRegex(desktop_css, r"\.sites-layout\s*>\s*\.card\s*\{[^}]*display:\s*flex")
        self.assertRegex(desktop_css, r"\.sites-layout\s*>\s*\.card\s*\{[^}]*min-height:\s*0")
        self.assertRegex(desktop_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*flex:\s*1\s+1\s+auto")
        self.assertRegex(desktop_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*max-height:\s*none")
        self.assertRegex(desktop_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*min-height:\s*0")
        self.assertRegex(desktop_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*overflow-y:\s*visible")
        self.assertRegex(desktop_css, r"\.config-layout\s*\{[^}]*grid-template-columns:\s*1fr")
        self.assertRegex(desktop_css, r"\.config-layout\s*\{[^}]*align-items:\s*start")
        self.assertRegex(desktop_css, r"\.config-column\s*\{[^}]*display:\s*grid")
        self.assertRegex(desktop_css, r"\.config-column\s*\{[^}]*gap:\s*var\(--space-base\)")
        self.assertRegex(desktop_css, r"\.config-column\s+>\s+\.card\s*\{[^}]*margin-bottom:\s*0")
        self.assertRegex(desktop_css, r"\.sites-save-fab\s*\{[^}]*right:\s*var\(--space-xl\)")
        self.assertRegex(desktop_css, r"\.sites-save-fab\s*\{[^}]*bottom:\s*var\(--space-xl\)")
        self.assertRegex(desktop_css, r"\.custom-site-entry\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(desktop_css, r"\.custom-site-entry-button\s*\{[^}]*width:\s*auto")
        self.assertRegex(css, r"\.sites-save-fab\s*\{[^}]*position:\s*fixed")
        self.assertRegex(css, r"\.sites-save-fab\s*\{[^}]*z-index:\s*130")
        self.assertRegex(css, r"\.sites-save-fab\s*\{[^}]*width:\s*auto")
        self.assertRegex(css, r"\.sites-save-fab\s*\{[^}]*border-radius:\s*999px")
        self.assertRegex(css, r"#page-sites\.active\s*\{[^}]*padding-bottom:\s*calc\(112px \+ env\(safe-area-inset-bottom\)\)")
        self.assertNotRegex(css, r"\.custom-site-entry\s*\{[^}]*background:\s*var\(--surface-card\)")
        self.assertNotRegex(css, r"\.custom-site-entry\s*\{[^}]*border:\s*1px\s+solid\s+var\(--hairline\)")

        self.assertRegex(css, r"@media\s*\(max-width:\s*1100px\)")
        tablet_query = re.search(r"@media\s*\(max-width:\s*1100px\)\s*\{(?P<body>.*?)(?:\n\}\n\n@media|\Z)", css, re.S)
        self.assertIsNotNone(tablet_query)
        tablet_css = tablet_query.group("body")
        self.assertRegex(tablet_css, r"\.sites-layout\s*\{[^}]*grid-template-columns:\s*1fr")
        self.assertRegex(tablet_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*min-height:\s*0")
        self.assertRegex(tablet_css, r"\.sites-layout\s+\.sites-scroll\s*\{[^}]*overflow-y:\s*visible")

        self.assertRegex(css, r"@media\s*\(max-width:\s*899px\)")
        compact_query = re.search(r"@media\s*\(max-width:\s*899px\)\s*\{(?P<body>.*?)(?:\n\}\n\n@media|\Z)", css, re.S)
        self.assertIsNotNone(compact_query)
        compact_css = compact_query.group("body")
        self.assertRegex(compact_css, r"\.site-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)")
        self.assertRegex(compact_css, r"\.site-url,\s*\n\s*\.site-diagnostic\s*\{[^}]*white-space:\s*normal")

        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)")
        self.assertRegex(css, r"\.dashboard-grid\s*\{[^}]*grid-template-columns:\s*1fr")
        mobile_query = re.search(r"@media\s*\(max-width:\s*720px\)\s*\{(?P<body>.*?)(?:\n\}\n\n@media|\Z)", css, re.S)
        self.assertIsNotNone(mobile_query)
        mobile_css = mobile_query.group("body")
        self.assertRegex(mobile_css, r"\.nav-tabs\s*\{[^}]*right:\s*0")
        self.assertRegex(mobile_css, r"\.nav-tabs\s*\{[^}]*bottom:\s*0")
        self.assertRegex(mobile_css, r"\.nav-tabs\s*\{[^}]*left:\s*0")
        self.assertRegex(mobile_css, r"\.nav-tabs\s*\{[^}]*flex-direction:\s*row")
        self.assertRegex(mobile_css, r"\.config-layout\s*\{[^}]*grid-template-columns:\s*1fr")
        self.assertRegex(mobile_css, r"\.sites-save-fab\s*\{[^}]*right:\s*12px")
        self.assertRegex(mobile_css, r"\.sites-save-fab\s*\{[^}]*bottom:\s*calc\(82px \+ env\(safe-area-inset-bottom\)\)")

        self.assertRegex(mobile_css, r"\.sites-scroll\s*\{[^}]*max-height:\s*none")
        self.assertRegex(mobile_css, r"\.nav-tab\s*\{[^}]*flex-direction:\s*column")

    def test_frontend_supports_automatic_dark_mode_tokens(self):
        css = self.read("styles.css")

        self.assertIn("color-scheme: light dark", css)
        self.assertRegex(css, r"@media\s*\(prefers-color-scheme:\s*dark\)")

        dark_query = re.search(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(?P<body>.*)\n\}", css, re.S)
        self.assertIsNotNone(dark_query)
        dark_css = dark_query.group("body")

        for token in [
            "--ink",
            "--body",
            "--canvas",
            "--canvas-soft",
            "--surface-card",
            "--hairline",
            "--scrollbar-thumb",
            "--scrollbar-track",
        ]:
            self.assertRegex(dark_css, rf"{re.escape(token)}:\s*#[0-9a-fA-F]{{6}}\b")

        self.assertIn("rgba(18, 18, 15, 0.96)", dark_css)

    def test_frontend_styles_scrollbars_for_global_and_nested_scrollers(self):
        css = self.read("styles.css")

        for token in [
            "--scrollbar-track",
            "--scrollbar-thumb",
            "--scrollbar-thumb-hover",
        ]:
            self.assertRegex(css, rf"{re.escape(token)}:\s*#[0-9a-fA-F]{{6}}\b")

        self.assertRegex(css, r"scrollbar-color:\s*var\(--scrollbar-thumb\)\s+var\(--scrollbar-track\)")
        self.assertRegex(css, r"scrollbar-width:\s*thin")
        self.assertRegex(css, r"html\s*\{[^}]*scrollbar-gutter:\s*stable")
        self.assertIn("::-webkit-scrollbar", css)
        self.assertIn("::-webkit-scrollbar-thumb", css)
        self.assertIn("::-webkit-scrollbar-track", css)
        self.assertRegex(css, r"\.logs-container,\s*\n\.sites-scroll,\s*\n\.modal-body\s*\{[^}]*scrollbar-gutter:\s*stable")

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
