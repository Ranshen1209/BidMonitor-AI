# Task 2 Report: Qianlima VIP Search Client and Adaptive Pagination

Status: DONE

Summary:
- Added RED tests for Qianlima VIP search pagination, duplicate-only page stopping, and safe membership fetch parsing.
- Implemented `QianlimaVipSearchClient` in `src/crawler/qianlima_vip.py`.
- Added `_extract_records` and `_safe_int` helpers for response extraction and config defaults.
- Preserved safe output behavior: diagnostics and errors include status/reason fields only, with no cookie values or account data.

TDD Evidence:
- RED: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_pages_until_empty_and_maps_notices tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_after_duplicate_only_pages tests/test_qianlima_vip.py::QianlimaVipClientTests::test_fetch_membership_status_uses_safe_parser -q`
  - Result: 3 failed with `ImportError` for missing `QianlimaVipSearchClient`.
- GREEN focused: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests -q`
  - Result: 3 passed.
- GREEN full Task 2 file: `.venv/bin/python -m pytest tests/test_qianlima_vip.py -q`
  - Result: 8 passed.
- Self-review verification: `git diff --check`
  - Result: passed with no output.

Files Changed:
- `src/crawler/qianlima_vip.py`
- `tests/test_qianlima_vip.py`
- `.superpowers/sdd/task-2-report.md`

Concerns:
- None.

## Review Fix: Max Results and Candidate Counting

Fix summary:
- Added a regression test proving `collect()` stops within a page when `qianlima_max_results_per_run` is reached.
- Changed `collect()` to emit a `max-results` diagnostic and return immediately after appending the notice that reaches the cap.
- Moved `candidate_count` to count every valid mapped notice before duplicate filtering, matching existing crawler semantics.
- Updated the duplicate-only page test to assert mapped duplicate candidates are counted.

RED/GREEN evidence for the new cap test:
- RED: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_inside_page_when_max_results_reached tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_after_duplicate_only_pages -q`
  - Result: 2 failed.
  - Cap failure: expected `["21"]`, got `["21", "22"]`.
  - Candidate-count failure: expected `2`, got `0`.
- GREEN focused: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_inside_page_when_max_results_reached tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_stops_after_duplicate_only_pages -q`
  - Result: `2 passed in 0.02s`.

Test commands and outputs:
- `.venv/bin/python -m pytest tests/test_qianlima_vip.py -q`
  - Result: `9 passed in 0.02s`.

Files changed:
- `src/crawler/qianlima_vip.py`
- `tests/test_qianlima_vip.py`
- `.superpowers/sdd/task-2-report.md`

## Re-review Fix: Early Return Counts and Invalid-Only Pages

Fix summary:
- Added regression coverage for `collect()` returning after page 2 HTTP 500 with one page 1 notice already parsed.
- Synced `parsed_count` through all `collect()` early-return paths via `_sync_result_counts()`.
- Changed duplicate-only stopping to require at least one mapped candidate on the page and all mapped candidates being duplicates.
- Added regression coverage proving invalid-only pages increment `skipped_count` without emitting duplicate-only diagnostics.
- Changed `collect()` return annotation from `Any` to `CrawlResult` and imported `CrawlResult` with the other source models.

RED/GREEN evidence for new tests:
- RED: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_syncs_parsed_count_before_http_error_return tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_does_not_treat_invalid_only_pages_as_duplicate_only -q`
  - Result: 2 failed.
  - Parsed-count failure: expected `1`, got `0`.
  - Invalid-only failure: expected `skipped_count == 3`, got `2`.
- GREEN focused: `.venv/bin/python -m pytest tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_syncs_parsed_count_before_http_error_return tests/test_qianlima_vip.py::QianlimaVipClientTests::test_collect_does_not_treat_invalid_only_pages_as_duplicate_only -q`
  - Result: `2 passed in 0.02s`.

Test commands and outputs:
- `.venv/bin/python -m pytest tests/test_qianlima_vip.py -q`
  - Result: `11 passed in 0.02s`.
- `git diff --check`
  - Result: passed with no output.

Files changed:
- `src/crawler/qianlima_vip.py`
- `tests/test_qianlima_vip.py`
- `.superpowers/sdd/task-2-report.md`
