Status: completed

Commits:
- Pending commit for frontend/results cleanup slice in owned files only.

Files changed:
- server/static/index.html
- server/static/app.js
- server/static/styles.css
- tests/test_static_frontend_assets.py

Tests run/results:
- `python3 -m unittest tests.test_static_frontend_assets -v` -> FAIL first as expected after test updates, then PASS (19 tests).

Concerns:
- Frontend is wired to the Task 3 backend routes and payload shape, but full runtime behavior still depends on those endpoints being present and returning the expected result detail/review structures.
- I left backend-owned cleanup in `server/app.py`, `src/monitor_core.py`, and config tests untouched per ownership boundaries; removal of hidden SMS/voice modals is deferred because only visible UI entry points were in scope.

## Task 5 Backend Fix - custom-sites compatibility gate

Status: completed

RED evidence:
- `python3 -m unittest tests.test_monitor_core_browser_mode -v` -> FAIL: `test_custom_sites_ignored_without_compatibility_flag` showed `create_browser_crawler` was called once for `IgnoredSite` without `enable_custom_sites`.

GREEN evidence:
- `python3 -m unittest tests.test_monitor_core_browser_mode tests.test_monitor_core_url_sources -v` -> PASS, 9 tests.

Changes:
- `MonitorCore._apply_crawler_overrides` now copies `custom_sites` only when `enable_custom_sites` is truthy.
- `MonitorCore._init_crawlers` ignores configured `custom_sites` unless `enable_custom_sites` is truthy.
- Legacy browser-mode custom-site tests opt into compatibility with `enable_custom_sites`.

## Task 4/5 Frontend Fix - detail comparison and bulk reason clearing

Status: completed

RED evidence:
- `python3 -m unittest tests.test_static_frontend_assets -v` -> FAIL, 22 tests run, 3 failures: missing detail AI/manual/final comparison hooks, missing changed-manual-only PATCH logic, and missing bulk clear-reasons control.

GREEN evidence:
- `python3 -m unittest tests.test_static_frontend_assets -v` -> PASS, 22 tests.

Changes:
- Detail panel now renders core fields side by side as 字段 / AI原始值 / 人工修正值 / 最终值.
- Manual correction inputs initialize from `detail.manual_overrides`; `saveResultFields()` PATCHes only changed manual fields and alerts without an API call when unchanged.
- Bulk review now has an explicit `bulkApplyReasons` checkbox, allowing `non_follow_reasons: []` to clear reasons while still requiring a reason when setting 不跟进.
