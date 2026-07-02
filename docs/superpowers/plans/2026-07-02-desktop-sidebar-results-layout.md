# Desktop Sidebar Results Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the results page overflow and add a desktop-only collapsible sidebar with brand content while preserving mobile bottom navigation.

**Architecture:** Keep the no-build static frontend split: `index.html` owns stable DOM structure, `styles.css` owns responsive layout, and `app.js` owns small UI state. Add static guardrail tests before modifying production assets.

**Tech Stack:** Plain HTML, CSS, browser JavaScript, Python `unittest` static checks.

## Global Constraints

- Desktop navigation uses an expanded left sidebar with Logo, `BidMonitor`, product subtitle, lower nav button placement, and an icon-only collapsed state.
- Mobile navigation keeps the existing bottom tab bar behavior.
- Results filter/action controls must remain inside the results card and wrap instead of overflowing.
- Preserve existing API calls, page IDs, inline handler names, auth behavior, and static asset architecture.
- Do not add a frontend build step or external dependency.
- Do not introduce box shadows, gradients, emoji, or negative letter spacing.
- Keep the existing design tokens and orange primary action color.

---

### Task 1: Static Guardrail Tests

**Files:**
- Modify: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: `server/static/index.html`, `server/static/styles.css`, `server/static/app.js`
- Produces: tests that fail until sidebar and results layout contracts exist.

- [ ] **Step 1: Add failing sidebar and results layout tests**

Add these test methods to `StaticFrontendAssetsTests`:

```python
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
        self.assertRegex(css, r"\.results-shell\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(340px,\s*520px\)")
        self.assertRegex(css, r"\.results-table-wrap\s*\{[^}]*min-width:\s*0")
        self.assertRegex(css, r"\.result-detail-panel\s*\{[^}]*min-width:\s*0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_desktop_sidebar_has_brand_and_collapsed_state_contract tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_results_layout_wraps_filters_without_page_overflow -v`

Expected: FAIL because the new sidebar brand, collapse JS, and revised results layout CSS are not implemented yet.

---

### Task 2: Sidebar Markup and JavaScript State

**Files:**
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`

**Interfaces:**
- Consumes: existing `.nav-tabs`, `.nav-tab`, `showPage(name, tabElement)`, `showAppShell()`, and `checkAuth()`.
- Produces: `SIDEBAR_COLLAPSED_KEY`, `applySidebarCollapsedState(collapsed: boolean)`, `initSidebarState(): void`, `toggleSidebarCollapse(): void`.

- [ ] **Step 1: Update nav HTML**

Replace the existing `<nav class="nav-tabs">...</nav>` block with:

```html
    <nav class="nav-tabs" aria-label="主导航">
        <div class="nav-brand">
            <div class="nav-brand-main">
                <svg class="icon brand-mark" aria-hidden="true"><use href="#icon-search"></use></svg>
                <div class="nav-brand-copy">
                    <span class="nav-brand-title">BidMonitor</span>
                    <span class="nav-brand-subtitle">招标信息监控系统</span>
                </div>
            </div>
            <button class="nav-collapse-btn" id="sidebarCollapseButton" type="button" onclick="toggleSidebarCollapse()" aria-label="折叠导航" title="折叠导航">
                <svg class="icon icon-sm" aria-hidden="true"><use href="#icon-chevron-right"></use></svg>
            </button>
        </div>
        <div class="nav-list">
            <button class="nav-tab active" data-page="home" onclick="showPage('home', this)" aria-label="控制台" title="控制台"><span class="nav-tab-icon"><svg class="icon" aria-hidden="true"><use href="#icon-home"></use></svg></span><span class="nav-label">控制台</span></button>
            <button class="nav-tab" data-page="results" onclick="showPage('results', this)" aria-label="结果" title="结果"><span class="nav-tab-icon"><svg class="icon" aria-hidden="true"><use href="#icon-list"></use></svg></span><span class="nav-label">结果</span></button>
            <button class="nav-tab" data-page="sites" onclick="showPage('sites', this)" aria-label="网站" title="网站"><span class="nav-tab-icon"><svg class="icon" aria-hidden="true"><use href="#icon-globe"></use></svg></span><span class="nav-label">网站</span></button>
            <button class="nav-tab" data-page="users" data-admin-only onclick="showPage('users', this)" aria-label="用户" title="用户"><span class="nav-tab-icon"><svg class="icon" aria-hidden="true"><use href="#icon-users"></use></svg></span><span class="nav-label">用户</span></button>
            <button class="nav-tab" data-page="config" onclick="showPage('config', this)" aria-label="配置" title="配置"><span class="nav-tab-icon"><svg class="icon" aria-hidden="true"><use href="#icon-settings"></use></svg></span><span class="nav-label">配置</span></button>
        </div>
    </nav>
```

- [ ] **Step 2: Mark filter buttons as grid actions**

In `server/static/index.html`, add `result-filter-action` to the two filter bar buttons:

```html
<button class="btn btn-outline result-filter-action" onclick="loadResults()">
<button class="btn btn-primary result-filter-action" onclick="openBulkReview()">
```

- [ ] **Step 3: Add sidebar state JavaScript**

Near the other top-level constants in `server/static/app.js`, add:

```javascript
const SIDEBAR_COLLAPSED_KEY = 'bidmonitor.sidebarCollapsed';
```

After `syncNavTabs()`, add:

```javascript
function applySidebarCollapsedState(collapsed) {
    const shell = document.getElementById('appShell');
    if (!shell) return;
    shell.classList.toggle('nav-collapsed', Boolean(collapsed));
    const button = document.getElementById('sidebarCollapseButton');
    if (button) {
        const label = collapsed ? '展开导航' : '折叠导航';
        button.setAttribute('aria-label', label);
        button.setAttribute('title', label);
        button.setAttribute('aria-expanded', String(!collapsed));
    }
}

function initSidebarState() {
    const collapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
    applySidebarCollapsedState(collapsed);
}

function toggleSidebarCollapse() {
    const shell = document.getElementById('appShell');
    const collapsed = !(shell && shell.classList.contains('nav-collapsed'));
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    applySidebarCollapsedState(collapsed);
}
```

In `showAppShell()`, call `initSidebarState();` after `appShell` is activated.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_desktop_sidebar_has_brand_and_collapsed_state_contract -v`

Expected: still FAIL until CSS is added in Task 3, but failures should only mention missing CSS contracts.

---

### Task 3: Sidebar and Results CSS

**Files:**
- Modify: `server/static/styles.css`

**Interfaces:**
- Consumes: `.nav-brand`, `.nav-list`, `.nav-label`, `.nav-collapse-btn`, `.result-filter-action`, and existing responsive breakpoints.
- Produces: desktop expanded/collapsed sidebar behavior and wrapping results layout.

- [ ] **Step 1: Add sidebar width tokens**

In `:root`, replace `--nav-rail-width: 104px;` with:

```css
    --nav-sidebar-width: 184px;
    --nav-sidebar-collapsed-width: 72px;
    --nav-rail-width: var(--nav-sidebar-width);
```

- [ ] **Step 2: Add base nav structure styles**

Near existing `.nav-tabs` styles, add:

```css
.nav-brand {
    display: none;
}

.nav-list {
    display: contents;
}

.nav-label {
    min-width: 0;
}

.nav-collapse-btn {
    display: none;
}
```

- [ ] **Step 3: Replace results layout rules**

Update the existing results rules to:

```css
.results-shell {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(340px, 520px);
    gap: 16px;
    align-items: start;
    min-width: 0;
}

.result-filter-bar {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin: 16px 0;
    align-items: stretch;
}

.filter-search {
    position: relative;
    display: flex;
    align-items: center;
    grid-column: span 2;
    min-width: 0;
}

.result-filter-action {
    width: 100%;
    min-width: 0;
}

.results-table-wrap {
    min-width: 0;
    overflow: auto;
    border: 1px solid var(--hairline);
    border-radius: var(--radius-md);
    background: var(--surface-card);
}

.result-detail-panel {
    min-width: 0;
    min-height: 720px;
    padding: 16px;
    border: 1px solid var(--hairline);
    border-radius: var(--radius-md);
    background: var(--canvas-soft);
}
```

- [ ] **Step 4: Add desktop sidebar CSS**

Inside `@media (min-width: 900px)`, update sidebar styles to:

```css
    .app-shell.active {
        padding-left: var(--nav-sidebar-width);
    }

    .app-shell.nav-collapsed.active {
        padding-left: var(--nav-sidebar-collapsed-width);
    }

    .nav-tabs {
        top: 0;
        right: auto;
        bottom: 0;
        left: 0;
        width: var(--nav-sidebar-width);
        flex-direction: column;
        align-items: stretch;
        gap: 0;
        padding: 0 10px;
        border-top: 0;
        border-right: 1px solid var(--hairline);
    }

    .app-shell.nav-collapsed .nav-tabs {
        width: var(--nav-sidebar-collapsed-width);
        padding-right: 8px;
        padding-left: 8px;
    }

    .nav-brand {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        min-height: 96px;
        padding: 18px 4px 14px;
        border-bottom: 1px solid var(--hairline-soft);
    }

    .nav-brand-main {
        display: flex;
        min-width: 0;
        align-items: center;
        gap: 10px;
    }

    .nav-brand-copy {
        display: grid;
        min-width: 0;
        gap: 2px;
    }

    .nav-brand-title {
        color: var(--ink);
        font-size: 16px;
        font-weight: 700;
        line-height: 1.2;
    }

    .nav-brand-subtitle {
        color: var(--body);
        font-size: 11px;
        line-height: 1.35;
        white-space: nowrap;
    }

    .nav-collapse-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
        width: 32px;
        height: 32px;
        border: 1px solid var(--hairline);
        border-radius: var(--radius-md);
        background: var(--surface-card);
        color: var(--body);
    }

    .nav-collapse-btn:hover {
        border-color: var(--hairline-strong);
        color: var(--ink);
        background: var(--canvas-soft);
    }

    .nav-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding-top: 22px;
    }

    .nav-tab {
        flex: 0 0 auto;
        flex-direction: row;
        justify-content: flex-start;
        gap: 10px;
        min-height: 44px;
        padding: 0 12px;
        border-radius: var(--radius-md);
        font-size: 13px;
    }

    .app-shell.nav-collapsed .nav-brand {
        justify-content: center;
        min-height: 88px;
        padding-right: 0;
        padding-left: 0;
    }

    .app-shell.nav-collapsed .nav-brand-copy,
    .app-shell.nav-collapsed .nav-label {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip: rect(0 0 0 0);
        white-space: nowrap;
    }

    .app-shell.nav-collapsed .nav-collapse-btn {
        position: absolute;
        top: 58px;
        left: 50%;
        transform: translateX(-50%);
    }

    .app-shell.nav-collapsed .nav-collapse-btn .icon {
        transform: rotate(180deg);
    }

    .app-shell.nav-collapsed .nav-list {
        padding-top: 28px;
    }

    .app-shell.nav-collapsed .nav-tab {
        justify-content: center;
        padding-right: 0;
        padding-left: 0;
    }
```

- [ ] **Step 5: Update responsive overrides**

Inside `@media (max-width: 899px)`, keep results stacked:

```css
    .filter-search {
        grid-column: 1 / -1;
    }
```

Inside `@media (max-width: 720px)`, ensure bottom nav still works:

```css
    .nav-brand {
        display: none;
    }

    .nav-list {
        display: contents;
    }
```

- [ ] **Step 6: Run focused tests**

Run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_desktop_sidebar_has_brand_and_collapsed_state_contract tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_results_layout_wraps_filters_without_page_overflow -v`

Expected: PASS.

---

### Task 4: Full Verification, Commit, and Merge

**Files:**
- Verify: `server/static/index.html`
- Verify: `server/static/styles.css`
- Verify: `server/static/app.js`
- Verify: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: tasks 1-3 complete.
- Produces: committed branch `codex/sidebar-results-layout` ready to merge into `main`.

- [ ] **Step 1: Run the static frontend suite**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: all tests PASS.

- [ ] **Step 2: Run broader relevant server static/API tests**

Run: `python3 -m unittest tests.test_static_frontend_assets tests.test_server_results_api -v`

Expected: all tests PASS.

- [ ] **Step 3: Inspect final diff**

Run: `git diff -- server/static/index.html server/static/styles.css server/static/app.js tests/test_static_frontend_assets.py`

Expected: diff only contains sidebar, results layout, JS collapse state, and matching tests.

- [ ] **Step 4: Commit implementation in worktree**

Run:

```bash
git add docs/superpowers/plans/2026-07-02-desktop-sidebar-results-layout.md server/static/index.html server/static/styles.css server/static/app.js tests/test_static_frontend_assets.py
git commit -m "fix: add collapsible sidebar and stabilize results layout"
```

Expected: commit succeeds on `codex/sidebar-results-layout`.

- [ ] **Step 5: Merge back to main checkout**

From `/Users/cervine/Documents/Github/BidMonitor-AI`, run:

```bash
git merge --no-ff codex/sidebar-results-layout
```

Expected: merge succeeds without touching unrelated uncommitted user changes.

- [ ] **Step 6: Verify merged checkout**

From `/Users/cervine/Documents/Github/BidMonitor-AI`, run:

```bash
python3 -m unittest tests.test_static_frontend_assets -v
```

Expected: all tests PASS in the main checkout.
