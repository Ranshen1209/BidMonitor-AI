Task 3 report

- Extracted the existing inline SPA behavior into `server/static/app.js`.
- Preserved the existing global handler names and kept the refresh cadence at 5s for status and logs.
- Updated `showPage` to accept `showPage(name, tabElement)` and avoid the global `event` dependency.
- Added `safeResultUrl(url)` and used it when rendering result links, while keeping `escapeHtml` for displayed text.
- Kept the log near-bottom autoscroll check and the secret-preservation logic in the config save flows.
- Focused test run before the file existed failed as expected with `FileNotFoundError` for `server/static/app.js`.
- Focused test run after creating `app.js` still needs to be rerun in this session.
