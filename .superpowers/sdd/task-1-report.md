# Task 1 Report: Qianlima VIP Payloads, Mapping, and Membership Parsing

Status: DONE

## Summary

Implemented `src/crawler/qianlima_vip.py` with:

- Qianlima VIP search endpoint constants and observed default search payload template.
- `build_search_payload()` with keyword/page normalization and config overrides.
- `has_qianlima_cookie()` enabled-cookie detection for `qianlima.com` and subdomains.
- `map_search_record_to_notice()` for Qianlima search result records.
- `parse_membership_payload()` returning only safe membership status fields.

Added focused tests in `tests/test_qianlima_vip.py`.

## TDD Evidence

RED 1:

```text
.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_build_search_payload_uses_observed_defaults_and_overrides tests/test_qianlima_vip.py::QianlimaVipTests::test_has_qianlima_cookie_matches_parent_domain -q
ModuleNotFoundError: No module named 'crawler.qianlima_vip'
```

GREEN 1:

```text
.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_build_search_payload_uses_observed_defaults_and_overrides tests/test_qianlima_vip.py::QianlimaVipTests::test_has_qianlima_cookie_matches_parent_domain -q
2 passed in 0.02s
```

RED 2:

```text
.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipTests::test_map_search_record_to_notice_uses_qianlima_fields tests/test_qianlima_vip.py::QianlimaVipTests::test_map_search_record_to_notice_skips_missing_title_or_url tests/test_qianlima_vip.py::QianlimaVipTests::test_parse_membership_payload_keeps_only_safe_fields -q
3 failed with NotImplementedError
```

GREEN 2:

```text
.venv/bin/python -m pytest tests/test_qianlima_vip.py -q
5 passed in 0.02s
```

Full verification:

```text
.venv/bin/python -m pytest -q
324 passed, 55 warnings, 82 subtests passed in 5.04s
```

## Self-Review

- Write scope kept to `src/crawler/qianlima_vip.py`, `tests/test_qianlima_vip.py`, and this required report file.
- Membership parsing deliberately omits account identifiers and contact fields.
- No live Cookie values or account data were added to logs or output beyond dummy test strings from the brief.
- Warnings in full test run are pre-existing deprecation/TLS warnings outside Task 1 scope.

## Concerns

None.
