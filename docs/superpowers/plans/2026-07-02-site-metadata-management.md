# Site Metadata Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin-managed metadata for the built-in URL list and expose it in the Sites page.

**Architecture:** Store metadata in `server_config.json` under `site_metadata`, keyed by built-in site key. `/api/sites` merges defaults, saved metadata, and enabled state. The frontend renders the merged fields and saves a sanitized site list payload.

**Tech Stack:** FastAPI-style async route functions, Pydantic fallback model support, vanilla HTML/CSS/JavaScript, Python `unittest`.

## Global Constraints

- Keep `csv_url_sources -> UrlListCrawler` intact.
- Do not remove or replace the built-in URL list.
- Do not bypass login, CAPTCHA, or anti-crawler controls.
- Use `site_metadata` as a dictionary keyed by site key.
- `POST /api/sites` must remain compatible with the legacy list-of-keys payload.
- The new admin metadata fields are `display_name`, `access_status`, `requires_login`, `has_antibot`, `note`, `last_checked_at`, and `last_diagnostic`.
- Allowed `access_status` values are `public_no_antibot`, `login_no_antibot`, `login_with_antibot`, `js_limited`, `commercial_limited`, `unavailable`, and `unknown`.

---

### Task 1: Backend Site Metadata API

**Files:**
- Modify: `server/app.py`
- Modify: `tests/test_server_config_defaults.py`

**Interfaces:**
- Produces: `/api/sites` GET rows with metadata fields.
- Produces: `/api/sites` POST compatibility for legacy `List[str]`, `{ "sites": [...] }`, and direct `List[Dict]`.

- [ ] Write failing backend tests for config default, metadata merge, legacy payload, and new payload sanitization.
- [ ] Run `python3 -m unittest tests.test_server_config_defaults -v` and confirm the new tests fail for missing behavior.
- [ ] Add `site_metadata` default and normalization.
- [ ] Add metadata default/merge/sanitize helpers.
- [ ] Update `get_sites` and `update_sites`.
- [ ] Run `python3 -m unittest tests.test_server_config_defaults -v` and confirm it passes.

### Task 2: Frontend Site Management UI

**Files:**
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`
- Modify: `server/static/styles.css`
- Modify: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: `/api/sites` rows with `display_name`, `access_status`, `requires_login`, `has_antibot`, `note`, `last_checked_at`, and `last_diagnostic`.
- Produces: `{ "sites": [...] }` payload from `saveSites()`.

- [ ] Write failing frontend static tests for DOM hooks, JS access status options, save payload, and CSS classes.
- [ ] Run `python3 -m unittest tests.test_static_frontend_assets -v` and confirm the new tests fail for missing behavior.
- [ ] Render a compact built-in URL management list.
- [ ] Add edit bindings for display name, access status, login flag, anti-crawler flag, and note.
- [ ] Update `saveSites()` to send the new payload.
- [ ] Add compact responsive styles.
- [ ] Run `python3 -m unittest tests.test_static_frontend_assets -v` and confirm it passes.

### Task 3: Integration Verification

**Files:**
- Read/verify only unless tests reveal integration gaps.

**Interfaces:**
- Confirms backend and frontend payloads match.

- [ ] Run backend and frontend tests together.
- [ ] Run URL list crawler regression test if dependencies allow.
- [ ] Inspect diffs for unrelated changes.
- [ ] Report any dependency or environment limits honestly.
