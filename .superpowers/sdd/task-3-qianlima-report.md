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
