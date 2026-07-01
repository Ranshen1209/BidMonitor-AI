Task 4 HTML shell refactor

Done:
- Replaced the embedded `<style>` and inline `<script>` blocks in `server/static/index.html` with external asset links to `/static/styles.css` and `/static/app.js`.
- Preserved the existing DOM IDs and kept inline event handlers for compatibility.
- Updated the bottom navigation buttons to use `data-page` and `showPage('name', this)`.
- Moved the requested inline layout styles to utility-class hooks in the shell: full-width buttons, split titles, progress layout, scroll region, modal action buttons, compact empty states, and action-link spans.

Verification:
- First run: `python3 -m unittest tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_index_uses_external_static_assets tests.test_static_frontend_assets.StaticFrontendAssetsTests.test_behavioral_dom_contract_is_preserved -v`
- Result after edit: both focused tests passed.

Notes:
- I did not edit `styles.css` or `app.js` in this task.
