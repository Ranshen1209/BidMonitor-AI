# Site Metadata Management Design

## Goal

Add administrator-managed metadata for the built-in URL list so each URL can have a readable name, access classification, login/anti-crawler flags, and notes without changing the existing crawl pipeline.

## Scope

- Keep the built-in URL list and `csv_url_sources -> UrlListCrawler` flow intact.
- Extend `/api/sites` so built-in sites expose metadata used by the frontend.
- Persist administrator edits in `site_metadata`, keyed by site key.
- Upgrade the Sites page from a checkbox-only list to a compact management surface for built-in URLs.
- Leave custom site management functionally unchanged for this iteration.

## Site Metadata

Each built-in site may store:

- `display_name`
- `access_status`
- `requires_login`
- `has_antibot`
- `note`
- `last_checked_at`
- `last_diagnostic`

Allowed `access_status` values:

- `public_no_antibot`
- `login_no_antibot`
- `login_with_antibot`
- `js_limited`
- `commercial_limited`
- `unavailable`
- `unknown`

When no metadata exists, the backend returns conservative defaults and the original site name.

## API Behavior

`GET /api/sites` remains available to authenticated users and returns each built-in site with metadata fields merged from defaults and saved configuration.

`POST /api/sites` becomes admin-only and accepts both legacy and new payloads:

- Legacy: `["site_key"]`
- New: `{ "sites": [{ ...site fields }] }`
- Compatibility: direct list of site dictionaries

The backend saves only the allowed metadata fields and filters unknown keys.

## Frontend Behavior

The Sites page shows a dense built-in URL management list. Each row includes enable, display name, URL/domain, access status, login flag, anti-crawler flag, and note. Saving sends the new `{ sites: [...] }` payload. Select all and deselect all continue to update `enabled`.

## Testing

Backend tests cover default config, metadata merge, legacy payload compatibility, and metadata sanitization.

Frontend static tests cover the new DOM hooks, JavaScript save payload, access status options, and CSS layout classes.
