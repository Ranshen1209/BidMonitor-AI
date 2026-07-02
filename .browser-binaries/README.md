# Browser Binaries

This directory is the project-local cache for browser runtimes used by browser mode.

- CloakBrowser patched Chromium: `.browser-binaries/cloakbrowser/`
- Playwright browsers: `.browser-binaries/playwright/`
- Local Selenium Chrome and ChromeDriver: `.browser-binaries/selenium/`
- webdriver-manager cache: `.browser-binaries/webdriver-manager/`

The application sets `BIDMONITOR_BROWSER_BINARIES`, `CLOAKBROWSER_CACHE_DIR`,
and `PLAYWRIGHT_BROWSERS_PATH` to this directory by default. Docker copies this
directory into the image, so any locally downloaded browser binaries placed here
are available at runtime.

Large binary files under this directory are intentionally ignored by git.
