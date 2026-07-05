## Task 5: Web UI Membership Status Display

Status: completed

### RED Evidence

- `.venv/bin/python -m pytest tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_qianlima_membership_status_contract_exists -q`
  - `1 failed in 0.03s`
  - Failed because `/api/sites/qianlima/membership` and the membership UI contract were not present in `app.js` or `styles.css`.

### GREEN Evidence

- `server/static/app.js`
  - Adds `qianlimaMembership` state.
  - Loads `/api/sites/qianlima/membership` after `/api/sites`.
  - Renders a Qianlima-only membership line for detecting, missing Cookie, failed, success, and expired states.
- `server/static/styles.css`
  - Adds compact `.site-membership` styling with warning and muted variants.
- `tests/test_static_frontend_assets.py`
  - Adds the membership contract test for endpoint, loader, state, and CSS hook.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_qianlima_membership_status_contract_exists -q`
  - GREEN: `1 passed in 0.01s`
- `.venv/bin/python -m pytest tests/test_static_frontend_assets.py -q`
  - `28 passed, 2 subtests passed in 0.03s`

### Files Changed

- `server/static/app.js`
- `server/static/styles.css`
- `tests/test_static_frontend_assets.py`
- `.superpowers/sdd/task-5-report.md`

### Concerns

- None.
