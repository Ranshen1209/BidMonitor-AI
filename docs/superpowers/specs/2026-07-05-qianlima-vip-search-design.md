# Qianlima VIP Search Design

## Goal

Optimize the Qianlima integration so daily crawls discover notices through the authenticated VIP search API first, then enrich candidates by fetching detail pages through the existing topology crawler.

The implementation must use an authorized company VIP session cookie, avoid storing credentials, reduce duplicate daily results, and expose the Qianlima membership expiration date in the Web UI when the account allows it.

## Confirmed Discovery

Playwright probing of an authenticated session identified these public-in-session endpoints:

- Search API: `POST https://search.vip.qianlima.com/rest/service/website/search/solr`
- Search result detail URL shape: `http://www.qianlima.com/zb/detail/<date>_<id>.html`
- Membership info API: `GET https://vip.qianlima.com/rest/u/company/getCompanyInfo`
- Membership fields: `memberLevelName`, `expireDate`, `showExpireDate`

The search API request body includes:

- `keywords`
- `currentPage`
- `numPerPage`
- `timeType`
- `sortType`
- `filtermode`
- `tab`
- `types`
- region and category filter strings

The response returns notice records under `data.data`. Useful fields include:

- `contentid`
- `progName`
- `showTitle`
- `popTitle`
- `updateTime`
- `url`
- `areaName`
- `progressStageName`
- `noticeSegmentTypeName`
- `tenderees`
- `agent`
- `bidder`
- `budgetAmountNumber`
- `tenderAmountNumber`
- `biddingAmountNumber`

The screenshots showed homepage advertising, registration, and guidance modals. These should not be part of the daily crawl path. Browser automation remains a diagnostic and discovery tool only.

## Chosen Approach

Use HTTP API first with Cookie-authenticated requests.

The daily Qianlima flow is:

1. Build search keywords from the existing keyword library or legacy keyword list.
2. For each keyword, call the VIP search API with authorized Cookie headers.
3. Parse search results into candidate notices.
4. Deduplicate by `contentid` and normalized detail URL before detail fetching.
5. Fetch candidate detail URLs through the existing `UrlListCrawler` detail parsing path.
6. Save valid results. If detail pages are masked or blocked, retain safe search-result metadata but do not infer hidden fields.
7. Query membership info and expose the expiration status in the Web configuration/status surface.

## Non-Goals

- Do not automate login, CAPTCHA, QR-code scanning, or password submission.
- Do not store account passwords, phone numbers, or full browser HAR files.
- Do not use Playwright as the normal daily crawler.
- Do not bypass member-only access controls. Authorized Cookie usage is allowed; automatic challenge circumvention is not.
- Do not replace the generic topology crawler for all sites.

## Configuration

Add Qianlima-specific options under crawler configuration or source metadata:

- `qianlima_vip_search_enabled`: default `true` when `qianlima` is enabled and a matching Cookie exists.
- `qianlima_search_endpoint`: default `https://search.vip.qianlima.com/rest/service/website/search/solr`.
- `qianlima_member_info_endpoint`: default `https://vip.qianlima.com/rest/u/company/getCompanyInfo`.
- `qianlima_num_per_page`: default `20`.
- `qianlima_max_pages_per_keyword`: default `30`.
- `qianlima_backfill_max_pages_per_keyword`: default `100`.
- `qianlima_stop_after_duplicate_pages`: default `3`.
- `qianlima_max_results_per_run`: default `1000`.
- `qianlima_time_type`: default `8` because the observed search page used it for the current broad time window.
- `qianlima_sort_type`: default `6`.
- `qianlima_domain_delay`: inherited from source `domain_delay`, default `2s`.

Cookie input stays in the existing `csv_url_sources[].auth_cookies` shape:

```json
{
  "domain": "qianlima.com",
  "cookie": "SESSION=...",
  "enabled": true
}
```

The same cookie must be sent to `search.vip.qianlima.com`, `vip.qianlima.com`, and `www.qianlima.com` when the domain rule matches `qianlima.com`.

## Search Request Template

Use the observed template as a baseline:

```json
{
  "allType": -1,
  "beginAmount": "",
  "currentPage": 1,
  "endAmount": "",
  "filtermode": "8",
  "fourLevelCategoryIdListStr": "",
  "hasChooseSortType": 1,
  "hasTenderTransferProject": 1,
  "keywords": "<keyword>",
  "levelId": "",
  "newAreas": "",
  "noticeSegmentTypeStr": "",
  "numPerPage": 20,
  "purchasingUnitIdList": "",
  "searchDataType": 0,
  "searchMode": 0,
  "showContent": 1,
  "sortType": 6,
  "summaryType": 0,
  "tab": 0,
  "threeClassifyTagStr": "",
  "threeLevelCategoryIdListStr": "",
  "timeType": 8,
  "types": "-1"
}
```

Only `keywords`, `currentPage`, `numPerPage`, `timeType`, and `sortType` need to be varied in the first implementation.

## Pagination

Use adaptive pagination instead of a small fixed page count.

Daily mode:

- Start at page `1`.
- Continue until one of these stop conditions is met:
  - `currentPage > qianlima_max_pages_per_keyword`.
  - `qianlima_max_results_per_run` has been reached.
  - The API returns no records.
  - `qianlima_stop_after_duplicate_pages` consecutive pages contain only already-seen `contentid` or normalized URL values.
  - All records on a page are older than the incremental cutoff, when a reliable last-success timestamp is available.

Backfill mode:

- Uses the same logic but applies `qianlima_backfill_max_pages_per_keyword`.
- Backfill is an explicit manual run mode, not the default daily schedule.

## Candidate Mapping

Each Qianlima search record maps to a candidate with:

- `source_id`: `qianlima`
- `source_name`: `千里马`
- `source_item_id`: `contentid`
- `title`: first non-empty value from `progName`, `showTitle`, `popTitle`
- `detail_url`: normalized `url`
- `publish_date`: normalized `updateTime`
- `region`: `areaName`
- `notice_type` or stage: `progressStageName` or `noticeSegmentTypeName`
- `purchaser`: first non-empty value from `tenderees`, `agent`, `bidder`
- `content`: compact metadata summary from search fields
- `raw`: sanitized JSON subset for traceability

If a detail fetch succeeds, detail content and extracted fields may enrich this candidate. If the detail page is masked, login-only, VIP-only, or CAPTCHA-protected, the system keeps the search candidate only when it has enough public metadata for a meaningful notice. It must not fill hidden purchaser, contact, amount, or deadline fields by guessing.

## Detail Fetching

Detail URLs discovered from search results should be passed through the existing `UrlListCrawler` detail parsing path where possible. This keeps current blocked-page detection and metadata formatting behavior.

The Qianlima topology should also recognize:

- `https://search.vip.qianlima.com/rest/service/website/search/solr` as a search API endpoint.
- `https?://www.qianlima.com/zb/detail/<date>_<id>.html` as detail URLs.
- `https?://www.qianlima.com/bid-<id>.html` as existing detail URLs.

HTTP detail fetching should send matching authorized Cookie headers. Browser rendering is only a fallback for diagnostics or manually triggered verification.

## Deduplication

Deduplication happens at three layers:

1. In-memory per run:
   - Skip candidates already seen by `contentid`.
   - Skip candidates already seen by normalized `detail_url`.

2. Database insertion:
   - Prefer existing `url` uniqueness behavior if present.
   - Add source-aware duplicate checks using `source_id + contentid` when the storage model supports it.

3. Pagination stop:
   - Count a page as duplicate-only when every candidate on that page already exists in either current run memory or persistent storage.
   - Stop after `qianlima_stop_after_duplicate_pages` duplicate-only pages.

This avoids daily repeats while still allowing old search pages to be scanned when new records are interleaved.

## Membership Status

Add a lightweight membership status fetch:

```http
GET https://vip.qianlima.com/rest/u/company/getCompanyInfo
```

Parse:

- `memberLevelName`
- `expireDate`
- `showExpireDate`
- `isExpired`

Expose this in the Web UI near source configuration/status as:

- membership level
- expiration date when `showExpireDate` is true or `expireDate` is non-empty
- status warning when the request returns `401`, `403`, or an expired/empty response

Do not persist sensitive company profile details such as phone number, email, username, contact name, or customer-service contact fields.

## Security and Logging

Rules:

- Never log Cookie values.
- Never log username, phone, password, authorization token, or full HAR content.
- Log only request method, endpoint path, HTTP status, item count, pagination summary, and `cookie_used=true/false`.
- Store diagnostics with sanitized URL bases and parameter names only.
- Treat login/CAPTCHA/access-denied responses as diagnostics.

The Playwright probe may stay as a developer-only tool, but it must remain outside the production crawl path and must redact sensitive URL parameters and request bodies.

## Error Handling

Search API failures:

- `401` or `403`: record diagnostic `qianlima_cookie_invalid_or_expired`; do not fallback to unauthenticated scraping for VIP search.
- `429` or frequent-block phrases: stop Qianlima crawl for the run and recommend increasing delay.
- `5xx` or network timeout: retry within existing retry limits, then record partial failure.
- JSON parse failure: record response diagnostics without body content.

Detail failures:

- Masked or member-only detail pages are not fatal when the search result has sufficient public metadata.
- CAPTCHA or human-verification pages are diagnostics only.

Membership info failures:

- Do not fail the crawl. Surface warning in source status.

## Tests

Add focused tests:

- Qianlima search request template builds correct JSON for keyword/page overrides.
- Auth cookie for `qianlima.com` applies to `search.vip.qianlima.com`, `vip.qianlima.com`, and `www.qianlima.com`.
- Search response records map to candidates with `contentid`, title, date, region, stage, purchaser, and detail URL.
- Duplicate `contentid` and normalized URL are skipped.
- Adaptive pagination stops after configured duplicate-only pages.
- Backfill mode uses the backfill page cap.
- Search API `401/403` produces a safe diagnostic without logging cookies.
- Membership info parses `memberLevelName` and `expireDate` while dropping sensitive company fields.
- Web API or config response includes Qianlima membership status when available.
- Existing generic URL topology tests continue to pass.

## Rollout

Implementation should be incremental:

1. Add the Qianlima VIP search client and unit tests.
2. Integrate it into source-backed Qianlima crawling behind `qianlima_vip_search_enabled`.
3. Add membership status fetch and API/UI surface.
4. Keep existing public topology seeds as fallback only when VIP search is unavailable or disabled.
5. Document how operators paste authorized Cookie values into configuration.

The first production run should use conservative limits:

- `qianlima_max_pages_per_keyword = 30`
- `qianlima_stop_after_duplicate_pages = 3`
- `qianlima_max_results_per_run = 1000`
- source `domain_delay >= 2`

After observing diagnostics for a few daily runs, these values can be tuned upward if the account remains stable and duplicate-only pages are not reached too early.
