# Source Adapter Crawl Run Design

## Context

BidMonitor-AI currently mixes several concepts in the crawl path:

- `enabled_sites` is presented as site enablement, but the default crawl path reads `csv_url_sources` from `server/url_sources.json`.
- `url_sources.json` and `site_topologies.json` are separate runtime inputs, with no single source object that owns enablement, entry URLs, topology, state, and health.
- Some crawlers emit list-page links directly as `BidInfo`, which lets raw candidates enter storage before detail validation.
- `MonitorCore.run_once()` saves new `BidInfo` rows before keyword, AI, detail, and quality gates have enough evidence.
- Deduplication is URL-only, so query variants, mirrored sources, and equivalent notices can duplicate.

The research document recommends a data pipeline rather than a link crawler:

`SourceRegistry -> Scheduler -> CrawlerRunner -> SourceAdapter -> Fetcher -> Parser -> Normalizer -> Deduplicator -> Storage -> Notifier/API/Exporter`

This design implements the first production-safe slice of that architecture while keeping existing UI and result-center behavior working.

## Goals

1. Make `Source` the single crawl unit for configured sites.
2. Make `enabled_sites` actually control which configured sources run.
3. Introduce `CrawlRun` records so each source run has observable status, counts, and errors.
4. Introduce `Notice` as the validated announcement model before converting to legacy `BidInfo`.
5. Introduce `SourceAdapter` so list candidates, detail pages, and structured API records have separate responsibilities.
6. Prevent generic list links or navigation pages from being inserted as final results.
7. Preserve backward compatibility for existing `bids` storage, result center, and notification code during this phase.

## Non-Goals

1. Do not rewrite every site into a bespoke adapter in one pass.
2. Do not remove the existing `bids` table or result-center APIs in this phase.
3. Do not add OCR, attachment parsing, or enterprise search in this phase.
4. Do not bypass login, CAPTCHA, paywalls, or non-public data gates.
5. Do not change the visual UI beyond behavior needed to make site enablement real.

## Architecture

### Source Registry

Create a runtime `Source` model that merges `url_sources.json`, `site_topologies.json`, and server config enablement.

Fields:

- `id`
- `name`
- `url`
- `enabled`
- `topology`
- `metadata`
- `rate_limit`
- `auth_cookies`

The registry loader accepts:

- URL source path
- topology path
- enabled site ids
- site metadata
- source-level defaults from `csv_url_sources`

Rules:

- If `enabled_sites` is non-empty, only matching source ids run.
- If `enabled_sites` is empty, default behavior remains compatible: all enabled records in `url_sources.json` run.
- Disabled records in `url_sources.json` never run.
- A source id missing topology can still run with generic rules, but the run records a warning.

### Crawl Runner

Create `CrawlRunner` to own per-source execution.

Responsibilities:

- Create a `CrawlRun` before each source starts.
- Call the source adapter.
- Count candidates, parsed notices, inserted rows, updated rows, skipped rows, and errors.
- Finish the run with `success`, `partial`, `failed`, or `skipped`.
- Return legacy-compatible `BidInfo` objects to `MonitorCore` only for validated notices.

### Source Adapter

Introduce a small adapter interface:

```python
class SourceAdapter:
    def collect(self, source: Source, stop_event=None) -> CrawlResult:
        ...
```

Phase 1 implements `TopologySourceAdapter`, which reuses the reliable parts of `UrlListCrawler`:

- Fetch source entry and topology seed URLs.
- Treat list/search/home pages as traversal only.
- Treat extracted links as candidates only.
- Fetch detail pages before emitting a notice.
- Parse structured JSON records into notices when enough fields exist.
- Emit diagnostics when pages are blocked, empty, or not admissible.

The existing `UrlListCrawler` can delegate to this adapter or remain as a compatibility wrapper. New behavior should be tested through the new runner/adapter path.

### Notice Model

Create a `Notice` dataclass before storage conversion.

Fields:

- `source_id`
- `source_name`
- `source_item_id`
- `title`
- `detail_url`
- `publish_date`
- `notice_type`
- `purchaser`
- `region`
- `content`
- `content_hash`
- `raw`
- `quality_flags`

Admission rules:

- A notice must have a title and detail URL.
- A notice must come from a detail page or structured API record.
- A list row alone is not a notice.
- If publish date is missing, keep it empty rather than fabricating today's date.
- If detail content is blocked or masked, emit a diagnostic and skip final notice insertion unless the public structured record is sufficient.

### Deduplication

Phase 1 keeps the existing `bids.unique_id` behavior for compatibility but introduces a canonical notice key used before insertion:

Primary:

`source_id + source_item_id`

Fallback:

`source_id + normalized_detail_url`

Weak fallback:

`hash(normalized_title + purchaser + publish_date + region)`

The fallback key is used to avoid duplicate insertions during the same run and to prepare for a later database schema migration. Existing `Storage.save()` still writes rows through `BidInfo`.

### Storage

Add a `crawl_runs` table through `Storage` migration.

Columns:

- `id`
- `source_id`
- `source_name`
- `started_at`
- `finished_at`
- `status`
- `fetched_count`
- `candidate_count`
- `parsed_count`
- `inserted_count`
- `updated_count`
- `skipped_count`
- `error_count`
- `error_message`

No new `notices` table is required in phase 1. Validated `Notice` objects convert to existing `BidInfo` for current result center compatibility.

### MonitorCore Integration

`MonitorCore._init_crawlers()` should stop treating default sites as crawlers in the normal path.

New flow:

1. Build configured sources from registry paths and server config.
2. Create one source-backed crawler/runner for the configured source set.
3. Run the source-backed crawler.
4. Receive validated `BidInfo` rows only.
5. Apply keyword and AI decisions for notification/review.
6. Insert rows only after the source adapter has validated that the item is a notice.

The first phase does not require changing the result-center API shape.

## Data Flow

```text
server config
  -> SourceRegistry.load()
  -> Source(id, topology, enabled, metadata)
  -> CrawlRunner.run_source()
  -> TopologySourceAdapter.collect()
  -> Candidate links / API records
  -> Detail fetch and parse
  -> Notice
  -> NoticeDeduplicator
  -> BidInfo conversion
  -> MonitorCore keyword / AI notification flow
  -> Storage.save()
  -> crawl_runs status update
```

## Error Handling

- Missing source file: no sources, log a warning, create no crawl runs.
- Missing topology for a source: run generic traversal with a warning on the run.
- HTTP 401/403/login/CAPTCHA: mark source run partial or failed depending on whether other notices were collected.
- Detail fetch failure: skip that candidate and increment `skipped_count` and `error_count`.
- Parser failure on one candidate: record candidate-level diagnostic and continue the source.
- All source attempts fail: finish run as `failed`.
- Stop event: finish active run as `skipped` if no notices were parsed, otherwise `partial`.

## Testing

Use TDD for each behavior.

Required tests:

1. Source registry filters by `enabled_sites`.
2. Empty `enabled_sites` preserves current default of running enabled URL sources.
3. Disabled URL source records never run.
4. Crawl runner creates and finishes a `crawl_runs` row.
5. List page links are candidates, not inserted notices.
6. Detail page with evidence becomes a `Notice` and then a `BidInfo`.
7. Missing publish date remains empty instead of becoming today's date.
8. Duplicate detail URL variants dedupe within a run.
9. `MonitorCore` uses source-backed crawling and does not instantiate metadata-only default-site crawlers.
10. Existing result center and server config tests still pass.

## Migration Plan

Phase 1:

- Add Source, Notice, CrawlRun, runner, adapter, and crawl run storage.
- Wire server config and `MonitorCore` to source-backed crawling.
- Preserve old storage and result APIs.

Phase 2:

- Add a real `notices` table and migrate result-center reads.
- Move AI extraction to operate on `Notice` detail text and evidence.
- Add stronger cross-source deduplication.

Phase 3:

- Add attachment records and parser status.
- Add source health dashboard.
- Add site-specific adapters for high-value sources.

## Acceptance Criteria

1. A disabled site in `/api/sites` is not crawled by the default URL source path.
2. A homepage or list page with bid-related links is not stored unless a detail page or structured API record validates it.
3. A crawl run record exists for each executed source and reports success/failure counts.
4. Unknown publish dates are not replaced with today's date in the new source-backed path.
5. Full test suite passes.
6. Existing user-facing result-center rows still load from the current `bids` table.
