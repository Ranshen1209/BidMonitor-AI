# BidMonitor-AI Production Notes

## Docker

```bash
cd /Users/cervine/Documents/Github/BidMonitor-AI
BIDMONITOR_ADMIN_USER=Admin BIDMONITOR_ADMIN_PASSWORD='123654' docker compose up -d --build
```

Open `http://localhost:8080`.

The container keeps runtime files in mounted `data/` and `logs/`. The external URL material is mounted read-only at `/materials`; update `server/server_config.json` so the URL source uses:

```json
{
  "csv_url_sources": [
    {
      "name": "上海招投标URL清单",
      "file_path": "/materials/bid_related_url_list.txt",
      "enabled": true,
      "domain_delay": 2,
      "auth_cookies": []
    }
  ]
}
```

## Auth

The old HTTP Basic Auth browser prompt has been removed. The app now uses an in-page login form and an HttpOnly session cookie.

Defaults are `Admin / 123654` for fast local adoption. For production, set `BIDMONITOR_ADMIN_USER` and `BIDMONITOR_ADMIN_PASSWORD` before first startup, then create team users in the Web UI.

## Anti-Crawler Boundary

The production-safe controls are:

- authorized cookies configured per domain in `csv_url_sources[].auth_cookies`
- manual handling when diagnostics report login/captcha/access-denied pages
- conservative `domain_delay` per source
- optional browser rendering for pages that need JavaScript
- CloakBrowser patched Chromium cached under `.browser-binaries/cloakbrowser/`
- Playwright binaries cached under `.browser-binaries/playwright/`
- Selenium Chrome and ChromeDriver binaries may be placed under `.browser-binaries/selenium/`

Docker copies `.browser-binaries/` into the image and also prewarms CloakBrowser during build when dependencies can be downloaded. Automatic captcha solving, proxy rotation, and access-control bypass are intentionally not bundled.
