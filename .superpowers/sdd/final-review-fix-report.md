## Final Review Fixes

Status: completed

### Findings Addressed

- Important: `qianlima_backfill_max_pages_per_keyword` existed as config but was not selected by any backfill mode.
- Important: frontend rendered `expire_date` without checking `show_expire_date`.
- Additional controller audit: Web config values needed to flow through `run_monitor_task()` and `MonitorCore._apply_crawler_overrides()` into source-backed crawler config.

### RED Evidence

- `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_backfill_mode_uses_backfill_page_limit -q`
  - `1 failed in 0.03s`
  - Only page 1 was collected when `qianlima_backfill_enabled` was true and the backfill page limit was 3.
- `.venv/bin/python -m pytest tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_qianlima_membership_expiry_respects_display_flag -q`
  - Failed before the UI checked `qianlimaMembership.show_expire_date`.
- `.venv/bin/python -m pytest tests/test_monitor_core_url_sources.py::MonitorCoreUrlSourcesTests::test_qianlima_options_flow_into_source_backed_crawler_config -q`
  - `1 failed in 0.12s`
  - `qianlima_backfill_enabled` was missing from `monitor.config["crawler"]`.

### GREEN Evidence

- `src/crawler/qianlima_vip.py`
  - Adds `qianlima_backfill_enabled` handling and selects `qianlima_backfill_max_pages_per_keyword` when enabled.
- `server/app.py`
  - Backfills `qianlima_backfill_enabled = False`.
  - Adds the field to `ConfigModel`.
  - Adds `build_crawler_overrides_from_config()` so Qianlima crawler options flow from Web config into monitor crawler overrides.
- `src/monitor_core.py`
  - Allows Qianlima VIP options through `_apply_crawler_overrides()`.
- `server/static/app.js`
  - Renders the membership expiry date only when `show_expire_date` is true.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_backfill_mode_uses_backfill_page_limit tests/test_monitor_core_url_sources.py::MonitorCoreUrlSourcesTests::test_qianlima_options_flow_into_source_backed_crawler_config tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_options_flow_into_monitor_crawler_overrides tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_qianlima_membership_expiry_respects_display_flag -q`
  - `4 passed in 0.16s`
- `.venv/bin/python -m pytest tests/test_qianlima_vip.py tests/test_monitor_core_url_sources.py tests/test_server_config_defaults.py tests/test_static_frontend_assets.py -q`
  - `77 passed, 9 warnings, 2 subtests passed in 0.66s`

### Concerns

- None.
