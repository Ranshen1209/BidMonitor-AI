# Task 3 Qianlima Report

## Scope

- `src/crawler/source_adapter.py`
- `src/crawler/source_crawler.py`
- `server/site_topologies.json`
- `tests/test_source_adapter.py`
- `tests/test_source_crawler.py`
- `tests/test_url_list_crawler.py`

## RED Evidence

- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details`
  - Failed with `AssertionError: 0 != 1`
  - Showed `TopologySourceAdapter.collect()` was not using the VIP path or enriching detail notices yet.
- `tests/test_source_crawler.py::CrawlRunnerTests::test_run_source_passes_notice_exists_callback`
  - Failed with `AssertionError: False is not true`
  - Showed `CrawlRunner.run_source()` was not passing a `notice_exists` callback into the adapter.
- `tests/test_url_list_crawler.py::UrlListCrawlerTests::test_qianlima_vip_search_endpoint_is_classified_as_search`
  - Failed with `AssertionError: '' != 'qianlima'`
  - Showed the built-in Qianlima topology did not yet recognize the VIP search host/endpoint.
- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_post_json_attaches_cookie_without_logging_body`
  - Failed with `AttributeError: 'UrlListCrawler' object has no attribute 'post_json'`
  - Showed adapter-built crawlers did not yet expose JSON helpers for VIP search.

## GREEN Evidence

- Added VIP-first branch in `TopologySourceAdapter.collect()` gated by source id, enable flag, and enabled Qianlima cookie presence.
- Added adapter-built crawler `post_json()` and `get_json()` helpers.
  - `post_json()` attaches the scoped cookie via `_get_cookie_for_url()`.
  - Logging includes only method and shortened URL, not cookie values or full payload bodies.
- Added Qianlima VIP detail enrichment that reuses existing detail parsing and falls back to the search notice when detail fetch/parsing fails.
- Preserved generic topology fallback when VIP search returns no notices and no VIP errors.
- Returned VIP result directly when VIP search reports errors and no notices.
- Updated `CrawlRunner` to pass `notice_exists=lambda notice: storage.exists(notice.to_bid_info())`.
- Expanded built-in Qianlima topology to allow `search.vip.qianlima.com`, `vip.qianlima.com`, and `home.qianlima.com`, and classified the VIP search endpoint as `search`.

## Tests Run

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details -q`
- `.venv/bin/python -m pytest tests/test_source_crawler.py::CrawlRunnerTests::test_run_source_passes_notice_exists_callback -q`
- `.venv/bin/python -m pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_qianlima_vip_search_endpoint_is_classified_as_search -q`
- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_post_json_attaches_cookie_without_logging_body -q`
- `.venv/bin/python -m pytest tests/test_qianlima_vip.py tests/test_source_adapter.py tests/test_source_crawler.py::CrawlRunnerTests tests/test_url_list_crawler.py::UrlListCrawlerTests::test_qianlima_vip_search_endpoint_is_classified_as_search -q`
- `git diff --check`

## Files Changed

- `src/crawler/source_adapter.py`
- `src/crawler/source_crawler.py`
- `server/site_topologies.json`
- `tests/test_source_adapter.py`
- `tests/test_source_crawler.py`
- `tests/test_url_list_crawler.py`

## Concerns

- Detail enrichment counts a detail fetch only when the detail request yields a parsed matching notice; fallback-to-search cases intentionally keep the search result without adding a new error.
- The broader suite still emits existing `datetime.utcnow()` deprecation warnings from `src/database/storage.py`, outside this task’s allowed scope.

## Review Fix Follow-up

### Fix Summary

- Restored the generic Qianlima topology `search` stanza to the public GET endpoint so topology fallback no longer enqueues the VIP POST endpoint.
- Added an adapter regression that keeps VIP search classification via `search_url_regex` while proving generic fallback does not call `search.vip.qianlima.com`.
- Updated VIP detail enrichment accounting so attempted detail fetches count even when detail fetch/parsing fails and the adapter falls back to the search notice.
- Added sanitized enrichment diagnostics for failed/skipped detail attempts without echoing raw VIP payload fields.

### RED Evidence

- Review diff/package showed `server/site_topologies.json` had changed the generic Qianlima `search` block to `POST https://search.vip.qianlima.com/rest/service/website/search/solr`, which would enqueue the VIP endpoint from generic topology fallback.
- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_reports_failed_detail_enrichment_attempt`
  - Failed with `AssertionError: 1 != 2`
  - Showed `TopologySourceAdapter` only counted successful detail parses, not attempted detail fetches that fall back to the search notice.

### GREEN Evidence

- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search`
  - Passed with generic fallback issuing only `GET https://search.qianlima.com/` and never requesting the VIP endpoint.
- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_reports_failed_detail_enrichment_attempt`
  - Passed with the fallback search notice preserved, `fetched_count == 2`, and a sanitized detail-enrichment diagnostic recorded for the failed detail attempt.
- `src/crawler/source_adapter.py`
  - `_enrich_qianlima_vip_result()` now records attempted detail fetches, promotes enrichment failures/skips into diagnostics and counters, and marks the summary as `partial` when fallback notices hide a detail-enrichment issue.
  - `_fetch_qianlima_detail_notice()` now returns `(notice, diagnostic, attempted_fetch)` so HTTP 4xx/5xx, blocked pages, request exceptions, and parse misses are surfaced without leaking raw payload data.
- `server/site_topologies.json`
  - Qianlima generic `search` reverted to public GET search while retaining VIP endpoint classification through `search_url_regex`.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search -q`
  - `1 passed in 0.12s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_reports_failed_detail_enrichment_attempt -q`
  - RED: `1 failed in 0.14s` (`AssertionError: 1 != 2`)
  - GREEN: `1 passed in 0.12s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py -q`
  - `40 passed, 11 subtests passed in 0.22s`
- `.venv/bin/python -m pytest tests/test_qianlima_vip.py tests/test_source_adapter.py tests/test_source_crawler.py::CrawlRunnerTests tests/test_url_list_crawler.py::UrlListCrawlerTests::test_qianlima_vip_search_endpoint_is_classified_as_search -q`
  - `61 passed, 4 warnings, 11 subtests passed in 0.26s`
- `git diff --check`
  - clean

### Files Changed

- `src/crawler/source_adapter.py`
- `server/site_topologies.json`
- `tests/test_source_adapter.py`
- `.superpowers/sdd/task-3-qianlima-report.md`

### Concerns

- The required suite is clean, but the broader repo still emits the pre-existing `datetime.utcnow()` deprecation warnings in `src/database/storage.py`, which remains outside this task’s allowed write scope.

## Review Fix Addendum

### RED Evidence

- `tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details`
  - Review concern: the enriched notice was still exposing merged detail payload under `raw["legacy"]` instead of a public `raw["detail"]` key.
- `tests/test_source_crawler.py::CrawlRunnerTests::test_run_source_passes_notice_exists_callback`
  - Review concern: the callback path was only being exercised after `run_source()` completed, so the test did not prove the storage `exists()` lookup happened during adapter collection.

### GREEN Evidence

- `src/crawler/source_adapter.py`
  - `_merge_qianlima_detail_notice()` now publishes the parsed detail payload under `raw["detail"]`.
- `tests/test_source_adapter.py`
  - The qianlima enrichment regression now asserts `raw["qianlima_search"]` and `raw["detail"]` exist and that `raw["legacy"]` is not the public merged-detail key.
- `tests/test_source_crawler.py`
  - The callback regression now makes the fake adapter call `notice_exists()` inside `collect()`, so `storage.exists()` is exercised through the normal run flow.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details tests/test_source_crawler.py::CrawlRunnerTests::test_run_source_passes_notice_exists_callback -q`
  - `2 passed in 0.14s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py tests/test_source_crawler.py::CrawlRunnerTests -q`
  - `48 passed, 4 warnings, 11 subtests passed in 0.24s`
- `git diff --check`
  - clean

## Remaining Review Fixes

### RED Evidence

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details -q`
  - `FF [100%]`
  - `test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search`
    - Failed with `AssertionError: 1 != 0`
    - Showed the generic fallback still surfaced a discovered VIP search endpoint path as an adapter error instead of refusing to follow it.
  - `test_collect_qianlima_uses_vip_search_then_enriches_details`
    - Failed with `AssertionError: 'qianlima' unexpectedly found in {...}`
    - Showed `_merge_qianlima_detail_notice()` was still exposing the legacy top-level `raw["qianlima"]` payload after enrichment.

### GREEN Evidence

- `src/crawler/source_adapter.py`
  - `should_follow_unadmitted_candidate()` now rejects `https://search.vip.qianlima.com/rest/service/website/search/solr` before generic topology traversal can enqueue it.
  - `_merge_qianlima_detail_notice()` now publishes a sanitized raw payload with only `raw["qianlima_search"]` and `raw["detail"]` for the merged Qianlima notice.
- `tests/test_source_adapter.py`
  - The empty-VIP fallback regression now injects a discovered VIP endpoint link into public HTML and asserts generic fallback never requests that URL.
  - The enrichment regression now asserts the merged raw payload omits both top-level `qianlima` and `legacy` keys.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_generic_vip_search tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details -q`
  - `2 passed in 0.13s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py -q`
  - `40 passed, 11 subtests passed in 0.23s`
- `git diff --check`
  - clean

### Files Changed

- `src/crawler/source_adapter.py`
- `tests/test_source_adapter.py`
- `.superpowers/sdd/task-3-qianlima-report.md`

### Concerns

- The scoped adapter suite is clean. Existing repo-level deprecation warnings in `src/database/storage.py` remain outside this task’s allowed write scope.

## HTTP-Only Fallback Review Fix

### RED Evidence

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_browser_auto -q`
  - `1 failed in 0.15s`
  - Failed with `AssertionError: 1 != 0`
  - Showed that after an empty/no-error VIP result, the adapter dropped into generic topology with browser mode still active and surfaced a browser-path failure instead of staying on HTTP.

### GREEN Evidence

- `tests/test_source_adapter.py`
  - Added `test_collect_qianlima_empty_vip_result_falls_back_without_browser_auto` using the real Qianlima topology, an enabled cookie, empty VIP `CrawlResult`, and browser-enabled adapter config.
  - Patched `UrlListCrawler._request_url_with_browser` to fail if called and verified the fallback stays on HTTP, does not hit the VIP endpoint, and still performs the public GET search traversal.
- `src/crawler/source_adapter.py`
  - When Qianlima VIP mode is attempted and returns empty/no-error, `TopologySourceAdapter.collect()` now scopes the adapter-built crawler's generic fallback to HTTP-only by temporarily disabling browser-first fetch and browser retry hooks, then restoring the crawler immediately after the fallback completes.
  - This keeps Task 3's earlier behavior intact: VIP-first, cookie-backed `post_json`, generic no-VIP-endpoint traversal, and merged raw keys limited to `qianlima_search` and `detail`.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_empty_vip_result_falls_back_without_browser_auto -q`
  - RED: `1 failed in 0.15s` (`AssertionError: 1 != 0`)
  - GREEN: `1 passed in 0.11s`
  - Final verification rerun: `1 passed in 0.12s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py -q`
  - `41 passed, 11 subtests passed in 0.22s`
- `git diff --check`
  - clean

### Files Changed

- `src/crawler/source_adapter.py`
- `tests/test_source_adapter.py`
- `.superpowers/sdd/task-3-qianlima-report.md`

### Concerns

- This fix is intentionally narrow: it only forces HTTP-only behavior for the adapter-built crawler during the empty/no-error Qianlima VIP fallback path, so other sites and normal browser-assisted diagnostics remain unchanged.

## HTTP-Only JSON Helper Hardening

### RED Evidence

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_get_json_uses_http_without_browser_auto tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_post_json_returns_sanitized_error_on_request_exception -q`
  - `..F [100%]`
  - `test_build_crawler_post_json_returns_sanitized_error_on_request_exception`
    - Failed with `requests.exceptions.RequestException: request failed for payload=secret`
    - Showed `post_json()` was still letting request exceptions escape instead of returning a sanitized non-2xx tuple.

### GREEN Evidence

- `tests/test_source_adapter.py`
  - Strengthened `test_collect_qianlima_uses_vip_search_then_enriches_details` with browser mode enabled and `_request_url_with_browser()` patched to fail, proving VIP detail enrichment still goes through `_request_url()` and stays HTTP-only.
  - Added `test_build_crawler_get_json_uses_http_without_browser_auto`, patching `_request_url_with_browser()` to fail and verifying `get_json()` uses `_request_http("GET", url)` directly and parses JSON successfully.
  - Added `test_build_crawler_post_json_returns_sanitized_error_on_request_exception`, verifying `post_json()` returns `({}, 599, "RequestException: request failed")` without leaking cookie or payload values.
- `src/crawler/source_adapter.py`
  - `_build_crawler().get_json()` now calls `crawler._request_http("GET", url)` directly, making the helper explicitly HTTP API oriented.
  - `get_json()` and `post_json()` now catch request/transport exceptions and return sanitized `599` tuples instead of raising, while preserving existing invalid-JSON fallback behavior.
  - Exception status text now strips likely sensitive request content such as cookies, payloads, tokens, or authorization fragments.

### Test Outputs

- `.venv/bin/python -m pytest tests/test_source_adapter.py::TopologySourceAdapterTests::test_collect_qianlima_uses_vip_search_then_enriches_details tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_get_json_uses_http_without_browser_auto tests/test_source_adapter.py::TopologySourceAdapterTests::test_build_crawler_post_json_returns_sanitized_error_on_request_exception -q`
  - RED: `..F [100%]` (`requests.exceptions.RequestException: request failed for payload=secret`)
  - GREEN: `3 passed in 0.13s`
  - Final verification rerun: `3 passed in 0.12s`
- `.venv/bin/python -m pytest tests/test_source_adapter.py -q`
  - `43 passed, 11 subtests passed in 0.21s`
- `git diff --check`
  - clean

### Files Changed

- `src/crawler/source_adapter.py`
- `tests/test_source_adapter.py`
- `.superpowers/sdd/task-3-qianlima-report.md`

### Concerns

- `get_json()` exception hardening is covered indirectly through the new explicit `_request_http("GET", ...)` helper path, but this pass only adds a focused transport-exception regression for `post_json()` because that was the user-requested non-2xx tuple test.
