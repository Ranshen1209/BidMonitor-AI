# Frontend Design Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the server frontend from a single inline HTML file into static HTML/CSS/JS assets that apply `DESIGN.md` while preserving existing API and DOM behavior.

**Architecture:** Keep the no-build FastAPI static asset model. `index.html` owns structure and stable IDs, `styles.css` owns the design-token system and component styling, and `app.js` owns the existing SPA behavior.

**Tech Stack:** Plain HTML, CSS, browser JavaScript, Python `unittest` static checks.

## Global Constraints

- Preserve all existing REST API calls and response expectations.
- Preserve all dynamic DOM IDs currently used by JavaScript.
- Preserve `.page.active`, `.nav-tab.active`, `.modal.active`, `.status-dot.running`, `.status-dot.stopped`, `.log-line.success`, and `.log-line.error` behavior.
- Use `DESIGN.md` tokens: primary `#f54e00`, primary active `#d04200`, ink `#26251e`, body `#5a5852`, canvas `#f7f7f4`, canvas soft `#fafaf7`, hairline `#e6e5e0`, surface card `#ffffff`, semantic success `#1f8a65`, semantic error `#cf2d56`.
- Use Inter/system fallback for normal UI and JetBrains Mono/Fira Code/monospace for logs and counters.
- Do not use negative letter spacing; keep `letter-spacing: 0` for app UI.
- Do not add a frontend build step or external CDN dependency.
- Do not use drop shadows; cards and panels use hairline borders.
- Keep timeline pastel colors out of semantic actions.

---

### Task 1: Static Frontend Guardrail Tests

**Files:**
- Create: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: `server/static/index.html`, `server/static/styles.css`, `server/static/app.js`
- Produces: static tests that verify the refactor contract.

- [ ] **Step 1: Write the failing tests**

```python
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
            "statusDot", "statusText", "nextRun", "todayNew", "todayRounds",
            "totalBids", "countdownBox", "countdownValue", "progressBox",
            "progressText", "progressBar", "progressSite", "btnStart",
            "btnStop", "logsContainer", "resultsList", "sitesList",
            "customSitesList", "contactsList", "cfgKeywords", "cfgExclude",
            "cfgMustContain", "cfgInterval", "cfgSelenium", "contactModal",
            "smsModal", "voiceModal", "aiModal", "customSiteModal",
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: FAIL because `styles.css` and `app.js` do not exist yet and `index.html` still embeds inline CSS/JS.

### Task 2: Design CSS Asset

**Files:**
- Create: `server/static/styles.css`

**Interfaces:**
- Consumes: class names and IDs already present in `index.html`.
- Produces: all visual styling for the app, including utility classes used by Task 4.

- [ ] **Step 1: Implement `styles.css`**

Create a plain CSS file that defines the required tokens, app typography, shell, cards, metrics, buttons, forms, modals, logs, result rows, list rows, empty states, bottom nav, and responsive behavior. Include these utility classes because Task 4 will use them: `.u-full`, `.u-full-mt-sm`, `.u-title-split`, `.progress-head`, `.progress-track`, `.sites-scroll`, `.modal-action`, `.empty-state-compact`, and `.action-link`.

- [ ] **Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_design_tokens_are_applied_without_shadows_or_negative_tracking -v`

Expected: PASS after the CSS exists and uses the required token values.

### Task 3: JavaScript Asset

**Files:**
- Create: `server/static/app.js`

**Interfaces:**
- Consumes: all existing DOM IDs and API endpoints.
- Produces: global functions referenced by existing inline handlers.

- [ ] **Step 1: Extract and preserve behavior**

Move the existing inline JavaScript into `server/static/app.js`. Preserve all global function names. Change `showPage` to `function showPage(name, tabElement)` and make it mark `tabElement` active when passed, otherwise find `.nav-tab[data-page="${name}"]`. Do not use `event.target`.

- [ ] **Step 2: Tighten result URL rendering**

Add:

```javascript
function safeResultUrl(url) {
    if (!url) return '#';
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return parsed.href;
    } catch (e) {
        console.warn('Invalid result URL', e);
    }
    return '#';
}
```

Use it in `loadResults()` for result anchors while preserving `escapeHtml` for text.

- [ ] **Step 3: Run focused tests**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_app_js_keeps_spa_behavior_without_global_event_dependency -v`

Expected: PASS after `app.js` exists, intervals/log scroll behavior remain, and `safeResultUrl` is present.

### Task 4: HTML Shell Asset

**Files:**
- Modify: `server/static/index.html`

**Interfaces:**
- Consumes: `/static/styles.css`, `/static/app.js`, utility classes from Task 2, global JS functions from Task 3.
- Produces: a slim HTML shell with stable IDs and no embedded style/script blocks.

- [ ] **Step 1: Link external assets**

Replace the embedded `<style>...</style>` block with:

```html
<link rel="stylesheet" href="/static/styles.css">
<script defer src="/static/app.js"></script>
```

Place the script in `<head>` or just before `</body>` with `defer`.

- [ ] **Step 2: Preserve and improve handlers**

Change bottom nav buttons to include `data-page` and pass `this`:

```html
<button class="nav-tab active" data-page="home" onclick="showPage('home', this)">
```

Repeat for `results`, `sites`, `contacts`, and `config`.

- [ ] **Step 3: Move inline styles to classes**

Use the utility classes from Task 2 for full-width buttons, split titles, progress layout, scroll regions, modal action buttons, compact empty states, and action links. Keep every existing DOM ID.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_index_uses_external_static_assets tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_behavioral_dom_contract_is_preserved -v`

Expected: PASS after the HTML references external assets and preserves IDs.

### Task 5: Integration Verification

**Files:**
- Verify: `server/static/index.html`
- Verify: `server/static/styles.css`
- Verify: `server/static/app.js`
- Verify: `tests/test_static_frontend_assets.py`

- [ ] **Step 1: Run static frontend tests**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: all tests pass.

- [ ] **Step 2: Run existing Python tests**

Run: `python3 -m unittest discover tests -v`

Expected: all tests pass.

- [ ] **Step 3: Serve the frontend locally**

Run: `python3 -m http.server 8765 --directory server/static`

Expected: static files load from `http://127.0.0.1:8765/`.

- [ ] **Step 4: Browser smoke check**

Open `http://127.0.0.1:8765/`, verify the page renders on desktop and mobile widths, tabs switch, no JS console syntax errors appear, and the visual style uses cream canvas, ink text, orange primary actions, hairline cards, and no shadows.
