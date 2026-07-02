Status: completed

Commits:
- pending

Files changed:
- server/app.py
- tests/test_server_config_defaults.py
- tests/test_server_results_api.py

Tests run/results:
- `python3 -m unittest tests.test_server_results_api tests.test_server_config_defaults -v` -> PASS (17 tests)

Concerns:
- `server/app.py` already had unrelated in-progress modifications in the working tree before Task 3 started; Task 3 changes were layered onto that file without reverting concurrent work.
- `/api/test/ai` now imports `results.ai_extractor.AIExtractor` lazily and returns `503` if Task 2 has not landed that module yet.

Fix addendum (review findings):
- Masked all config secret-bearing values exposed by `GET /api/config`, including `sms_config.access_key_secret`, `voice_config.access_key_secret`, and `ai_config.api_key`, while preserving existing secret values when `POST /api/config/full` receives masked or empty placeholders.
- Kept `GET /api/results?q=...` from forwarding unsupported `q` into storage; the API now applies a current-page text filter after storage returns the requested page so the endpoint does not crash on search.
- Hardened `PATCH /api/results/{id}/fields` to return `404` for missing results, reject unsupported manual override keys with `400`, and merge allowed incoming overrides over existing `manual_overrides` before saving.

Addendum tests/results:
- Added config masking coverage for SMS and voice secrets plus secret-preservation coverage for full-config updates in `tests/test_server_config_defaults.py`.
- Added results API coverage for `q` search behavior, nonexistent result handling, unsupported override keys, and override merge semantics in `tests/test_server_results_api.py`.
- `python3 -m unittest tests.test_server_results_api tests.test_server_config_defaults -v` -> PASS (23 tests)

Fix addendum (config secret masking review):
- RED: Added regression coverage for `GET /api/config` masking of `wechat_config.token`, `email_configs[*].password`, `contacts[*].email_password`, `contacts[*].wechat_token`, and nested `token`/`api_key` fields while preserving display fields such as sender, contact name, email, and `access_key_id`.
- RED: Added preservation coverage for `POST /api/config/full` keeping existing notification secrets when the browser submits masked or empty placeholders, including `email_configs[*].password`.
- RED result: `python3 -m unittest tests.test_server_config_defaults -v` failed as expected with plaintext `wechat_config.token` returned and masked `wechat_config.token` stored.
- GREEN: Replaced the fixed three-field secret list with recursive config masking/preservation for keys containing `password`, `token`, `secret`, or `api_key`, with `access_key_id` explicitly left visible.
- GREEN result: `python3 -m unittest tests.test_server_config_defaults tests.test_server_results_api -v` -> PASS (23 tests).
