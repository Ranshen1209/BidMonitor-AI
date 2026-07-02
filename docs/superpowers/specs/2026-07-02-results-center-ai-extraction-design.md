# Results Center and AI Extraction Design

## Goal

Build the first-stage results center for BidMonitor so colleagues can review crawled bidding opportunities in a spreadsheet-like workflow. New results fetch the full detail page, run AI field extraction automatically, show business-critical fields in a table, and support manual review decisions that can later improve search and AI filtering.

This stage intentionally does not implement per-site login, membership status, or site-specific search algorithms. Those will be handled in later site adapter work.

## Scope

Included:

- Replace the current result card list with a dense result table and detail side panel.
- Fetch the full detail page for each new result before AI extraction.
- Automatically extract structured bidding fields with AI when a new result is saved.
- Store both AI original values and human-corrected values.
- Add review workflow fields: suitability, follow decision, urgency, project stage, non-follow reasons, and review notes.
- Support full bulk editing for suitability, follow decision, urgency, project stage, non-follow reasons, and notes.
- Support configurable non-follow reason tags.
- Support AI endpoint types for `responses` and `chat_completions`.
- Remove the custom URL feature from the Web UI, API, and config.
- Hide the contacts page and notification configuration from the Web UI while keeping notification modules in code for now.

Excluded:

- Per-site login adaptation.
- Membership level and remaining membership time display.
- Site-specific search algorithms.
- A full CRM-style multi-table workflow.
- Final cleanup of notification modules.

## Chosen Approach

Use a hybrid storage model:

- Keep high-frequency business and table fields as database columns.
- Store full AI extraction data and human corrections as JSON.
- Resolve display values by preferring human corrections, then AI values, then original crawler values.

This keeps table filtering fast while preserving enough structured history for future AI prompt and search optimization.

## Data Model

The existing `bids` storage remains the base record for a bidding opportunity. Existing fields such as title, URL, publish date, source, content, purchaser, notified state, and created time remain.

Add column-backed review and table fields:

- `fit_status`: `pending`, `fit`, `not_fit`
- `follow_decision`: `pending`, `follow`, `not_follow`
- `urgency`: `low`, `medium`, `high`, `urgent`
- `urgency_source`: `auto`, `manual`
- `project_stage`: `lead`, `screening`, `following`, `submitted`, `ended`
- `amount`
- `amount_unit`
- `region`
- `category`
- `project_type`
- `nature`
- `registration_deadline`
- `submission_deadline`
- `bid_opening_time`
- `deadline_source`: `ai`, `manual`, `crawler`
- `urgency_reference_time`
- `urgency_reference_type`
- `ai_extract_status`: `pending`, `detail_fetch_failed`, `extract_failed`, `extracted`
- `detail_fetch_status`: `pending`, `success`, `failed`
- `detail_fetched_at`
- `updated_at`

Add JSON-backed fields:

- `ai_extracted_data`: original AI extraction result.
- `manual_overrides`: human corrections to extracted fields.
- `non_follow_reasons`: selected reason tag list.
- `review_notes`: human notes for follow or non-follow decisions.
- `ai_recommendation`: AI suitability recommendation, reason, and risk points.

Resolved display values are computed at read time from `manual_overrides`, `ai_extracted_data`, and original crawler fields. Do not add a `final_data_snapshot` cache in the first implementation.

### Deadline Model

The first table screen must show at least three separate bidding deadlines:

- `registration_deadline`: registration or document-fetch deadline.
- `submission_deadline`: bid, response, or proposal submission deadline.
- `bid_opening_time`: bid opening, response opening, or evaluation time.

The full AI extraction JSON preserves a complete timeline under `ai_extracted_data.deadlines`. Each item includes:

- `type`
- `label`
- `start_at`
- `end_at`
- `raw_text`
- `confidence`

Allowed deadline types:

- `announcement_published`
- `registration_start`
- `registration_deadline`
- `document_fetch_start`
- `document_fetch_deadline`
- `deposit_deadline`
- `clarification_deadline`
- `site_visit_time`
- `submission_deadline`
- `bid_opening_time`
- `contract_period`
- `service_period`
- `other`

Urgency auto-suggestion prioritizes `submission_deadline`, then `registration_deadline`, then other action-oriented deadlines such as deposit and clarification deadlines. `bid_opening_time` is displayed but is not the primary urgency driver.

## Review Workflow

Every new result starts with:

- `fit_status=pending`
- `follow_decision=pending`
- `project_stage=lead`
- `ai_extract_status=pending`

Suitability, follow decision, and project stage are separate fields:

- Suitability: pending, fit, not fit.
- Follow decision: pending, follow, not follow.
- Project stage: lead, screening, following, submitted, ended.

If a user chooses `not_follow`, at least one non-follow reason must be selected. Reason tags have defaults and are administrator-configurable:

- 地域问题
- 金额不合适
- 项目类型不匹配
- 资质不满足
- 时间太紧
- 信息不完整
- 重复项目
- 已过期
- 其它

Users can also add review notes. Bulk editing must support all review fields: suitability, follow decision, urgency, stage, non-follow reasons, and notes.

Urgency values are:

- low
- medium
- high
- urgent

The system suggests urgency from deadlines. Once a user manually changes urgency, future automatic extraction must not overwrite it.

## Detail Fetch and AI Extraction Flow

After a crawler finds a new matching result:

1. Save the result to storage immediately with pending review and extraction statuses.
2. Fetch the result URL as a detail page.
3. Clean the detail HTML into readable text by removing scripts, styles, navigation noise, and repeated whitespace.
4. If detail fetch fails, keep the result visible and set `detail_fetch_status=failed` and `ai_extract_status=detail_fetch_failed`.
5. If detail fetch succeeds, send title, URL, source, publish date, list-page summary, and detail-page text to AI.
6. Require AI to return strict JSON with bidding fields, deadlines, recommendation, and risk points.
7. Validate and store the JSON in `ai_extracted_data`.
8. Sync high-frequency fields to columns for table filtering and sorting.
9. Compute automatic urgency unless urgency has already been manually set.
10. If AI fails or returns invalid JSON, keep the result visible and set `ai_extract_status=extract_failed` with a short error summary.

## AI Configuration

AI settings must support both endpoint styles:

- `responses`
- `chat_completions`

Configuration fields:

- `base_url`
- `api_key`
- `model`
- `endpoint_type`

For OpenAI-compatible Grok access, `base_url` can be a `/v1` base URL and `endpoint_type=responses`. Existing DeepSeek/OpenAI-style chat completion setups can use `endpoint_type=chat_completions`.

API keys remain local configuration values and must be masked when returned to the browser.

## Results Center UI

The results page becomes a spreadsheet-like table.

Default table columns:

- Project name
- Suitability
- Follow decision
- Urgency
- Project stage
- Organization
- Amount
- Region
- Category
- Registration/document deadline
- Submission deadline
- Bid opening time
- AI extraction status
- Source
- Actions

Table controls:

- Search by project name, organization, summary, and URL.
- Filter by new or pending results, suitability, follow decision, urgency, stage, AI status, source, region, category, and deadline range.
- Bulk edit selected rows for suitability, follow decision, urgency, project stage, non-follow reasons, and notes.

Clicking a row opens a detail side panel. The side panel shows:

- Original title, URL, source, and detail-fetch status.
- AI recommendation, recommendation reason, and risk points.
- Full structured fields, including organization, amount, nature, category, region, contacts, and all deadlines.
- Manual correction controls for key extracted fields.
- Review controls for suitability, follow decision, urgency, stage, non-follow reasons, and review notes.

Display values resolve in this order:

1. Human correction from `manual_overrides`.
2. AI value from `ai_extracted_data`.
3. Original crawler value.

Status changes save immediately.

## Configuration and Removed Entry Points

The Web UI no longer exposes colleague-facing URL or contact management:

- Remove custom URL page entry, modal, JavaScript, `/api/custom-sites`, and `custom_sites` config.
- Keep built-in or URL-list sources maintained by the developer.
- Hide contacts navigation, contacts page, contact modals, and contact JavaScript.
- Hide notification API configuration entry points in the Web UI.
- Keep existing notification modules and old notification config fields in code for now to avoid broad cleanup risk.
- Keep user management, search config, AI config, and site metadata configuration.

Add result settings:

- `non_follow_reason_tags`, editable by administrators.
- Result enum values can be backend constants in the first version.

## API Design

Add or update backend routes:

- `GET /api/results`: pagination, filters, search, table fields, and detail summaries.
- `GET /api/results/{id}`: full result detail, AI extraction JSON, manual overrides, and resolved fields.
- `PATCH /api/results/{id}/review`: update one result's review workflow fields.
- `PATCH /api/results/bulk-review`: bulk update review fields.
- `PATCH /api/results/{id}/fields`: save human corrections to `manual_overrides`.
- `GET /api/result-settings`: return review enums and non-follow reason tags.
- `POST /api/result-settings/reasons`: admin-only update for non-follow reason tags.
- `POST /api/test/ai`: test either `responses` or `chat_completions` according to config.

Deprecate `/api/contacts` for Web use but do not require notification module cleanup in this stage.

Remove `/api/custom-sites` with the custom URL feature.

## Validation and Error Handling

- Invalid review enum values reject the request.
- `not_follow` requires at least one non-follow reason.
- Bulk edits are atomic: if one item or value is invalid, reject the batch.
- Detail fetch failure does not remove or hide a result.
- AI extraction failure does not remove or hide a result.
- Invalid AI JSON stores a short error summary and marks extraction failed.
- Manual urgency prevents later automatic urgency overwrites.
- API keys are never returned in plaintext.

## Testing

Backend tests:

- Storage migration adds new columns to old databases without losing old results.
- Result list supports pagination, filters, and search.
- Result detail resolves manual overrides over AI values.
- Single review update validates enums and non-follow reasons.
- Bulk review update applies atomically.
- Manual field corrections save to `manual_overrides`.
- Detail fetch failure sets the correct statuses.
- AI client builds and parses `responses` payloads.
- AI client builds and parses `chat_completions` payloads.
- Result settings return defaults and allow admin reason-tag updates.
- Custom-sites API is removed or no longer routed.

Frontend/static tests:

- Results page includes the table columns, including the three deadline columns.
- Detail side panel hooks exist.
- Bulk edit controls exist.
- Contacts navigation and contact page hooks are absent or hidden.
- Notification config entry points are hidden.
- Custom URL modal and JS entry points are removed.
- AI config includes endpoint type selection.

## Rollout Notes

Existing results remain visible after migration, with default pending review and extraction statuses. Existing records have no AI data until they are reprocessed or newly discovered again. The implementation plan must keep changes focused and avoid touching unrelated crawler or notification internals beyond what is needed for this first-stage result center.
