## Task 4: Membership Status Backend API and Config Defaults

Status: completed

### RED Evidence

- `.venv/bin/python -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_default_config_backfills_qianlima_vip_search_options -q`
  - `1 failed in 0.17s`
  - Failed with `KeyError: 'qianlima_vip_search_enabled'`.
- `.venv/bin/python -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_returns_safe_status tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_reports_missing_cookie -q`
  - `2 failed in 0.21s`
  - Failed because `app.UrlListCrawler` and `app.get_qianlima_membership` were not present.

### GREEN Evidence

- `server/app.py`
  - Backfills Qianlima VIP search defaults in `normalize_config()`.
  - Extends `ConfigModel` with Qianlima VIP options so `/api/config` can persist updates.
  - Adds `qianlima_auth_cookies_from_config()` and `build_qianlima_membership_crawler()`.
  - Adds `GET /api/sites/qianlima/membership`, returning `missing_cookie`, invalid/failed HTTP states, or the sanitized `parse_membership_payload()` result.
- `tests/test_server_config_defaults.py`
  - Covers default backfill values.
  - Covers safe membership status mapping without leaking username or phone fields.
  - Covers the no-Cookie path without requiring any network call.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_default_config_backfills_qianlima_vip_search_options tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_returns_safe_status tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_qianlima_membership_endpoint_reports_missing_cookie -q`
  - `3 passed in 0.13s`
- `.venv/bin/python -m pytest tests/test_server_config_defaults.py -q`
  - `24 passed in 0.19s`

### Files Changed

- `server/app.py`
- `tests/test_server_config_defaults.py`
- `.superpowers/sdd/task-4-report.md`

### Concerns

- None.
