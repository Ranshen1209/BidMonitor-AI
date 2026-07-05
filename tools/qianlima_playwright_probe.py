#!/usr/bin/env python3
"""One-off Playwright probe for Qianlima authenticated search.

This script opens an existing local Chrome executable with a temporary profile,
lets an operator log in manually, and records sanitized network metadata only.
It intentionally avoids storing passwords, cookies, auth headers, or full HAR.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright


DEFAULT_URL = "https://search.vip.qianlima.com/index.html#/"
DEFAULT_OUTPUT_DIR = "/private/tmp/qianlima_playwright_probe"
DEFAULT_CHROME = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)

SENSITIVE_HEADER_RE = re.compile(
    r"(cookie|authorization|token|session|secret|password|credential)",
    re.IGNORECASE,
)
CANDIDATE_URL_RE = re.compile(
    r"(search|query|bid|zb|tender|vip|member|user|ajax|api)",
    re.IGNORECASE,
)
EXPIRY_TEXT_RE = re.compile(
    r".{0,30}(会员|VIP|有效期|到期|过期|套餐|企业套餐|服务期限).{0,50}",
    re.IGNORECASE,
)


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed = {"accept", "content-type", "origin", "user-agent", "x-requested-with"}
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in allowed and not SENSITIVE_HEADER_RE.search(key)
    }


def sanitize_url(url: str) -> dict[str, Any]:
    parts = urlsplit(url)
    query_keys = [key for key, _value in parse_qsl(parts.query, keep_blank_values=True)]
    return {
        "url_base": urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")),
        "query_keys": sorted(set(query_keys)),
    }


def sanitize_template_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(term in key_lower for term in ["password", "username", "phone", "mobile", "token", "user", "uid"]):
        return "<redacted>"
    if key_lower in {"keyword", "keywords", "key_word", "keywordstr"}:
        return "<keyword>"
    if isinstance(value, dict):
        return {str(item_key): sanitize_template_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize_template_value(key, item) for item in value[:3]]
    return value


def should_save_request_template(url_base: str) -> bool:
    return url_base.endswith(
        (
            "/rest/service/website/search/solr",
            "/rest/service/website/search/classInfo/searchClassInfo",
        )
    )


def request_body_metadata(post_data: str | None, url_base: str = "") -> dict[str, Any]:
    if not post_data:
        return {}
    stripped = post_data.strip()
    if not stripped:
        return {}
    if stripped[0] in "[{":
        try:
            parsed = json.loads(stripped)
        except Exception:
            return {"post_data_kind": "json_unparsed", "post_data_length": len(post_data)}
        return {
            "post_data_kind": "json",
            "post_data_shape": shape_json(parsed),
            "post_data_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
            **(
                {
                    "post_data_template": {
                        str(key): sanitize_template_value(str(key), value)
                        for key, value in parsed.items()
                    }
                }
                if isinstance(parsed, dict) and should_save_request_template(url_base)
                else {}
            ),
        }
    pairs = parse_qsl(stripped, keep_blank_values=True)
    if pairs:
        return {
            "post_data_kind": "form",
            "post_data_keys": sorted({key for key, _value in pairs}),
        }
    return {"post_data_kind": "raw", "post_data_length": len(post_data)}


def first_json_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("records", "list", "rows", "data", "result", "items"):
            if key in value:
                record = first_json_record(value[key])
                if record:
                    return record
        for item in value.values():
            record = first_json_record(item)
            if record:
                return record
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
            record = first_json_record(item)
            if record:
                return record
    return None


def redacted_url_pattern(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"\d{4,}", "<num>", text)
    text = re.sub(r"(?<=/)[A-Za-z0-9_-]{16,}(?=[/?#.]|$)", "<id>", text)
    return text[:220]


def shape_json(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {
            str(key): shape_json(item, depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, list):
        if not value:
            return []
        return [shape_json(value[0], depth + 1)]
    if value is None:
        return None
    return type(value).__name__


def first_record_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("records", "list", "rows", "data", "result", "items"):
            if key in value:
                keys = first_record_keys(value[key])
                if keys:
                    return keys
        for item in value.values():
            keys = first_record_keys(item)
            if keys:
                return keys
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return list(item.keys())[:80]
            keys = first_record_keys(item)
            if keys:
                return keys
    return []


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def visible_expiry_hints(page) -> list[str]:
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return []
    hints = []
    seen = set()
    for match in EXPIRY_TEXT_RE.finditer(text):
        hint = " ".join(match.group(0).split())
        if hint and hint not in seen:
            seen.add(hint)
            hints.append(hint)
        if len(hints) >= 20:
            break
    return hints


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--user-data-dir", default="/private/tmp/qianlima-playwright-profile")
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "events.jsonl"
    summary_path = output_dir / "summary.json"
    screenshot_path = output_dir / "last-page.png"
    if events_path.exists():
        events_path.unlink()

    candidate_events: list[dict[str, Any]] = []
    print(f"[probe] output_dir={output_dir}", flush=True)
    print("[probe] A Chrome window will open. Log in manually, run searches, open details, and visit member center.", flush=True)
    print(f"[probe] The probe will run for {args.seconds}s or until you close the browser.", flush=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=args.user_data_dir,
            executable_path=args.chrome,
            headless=False,
            viewport={"width": 1440, "height": 950},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        def on_response(response) -> None:
            request = response.request
            url = response.url
            resource_type = request.resource_type
            content_type = response.headers.get("content-type", "")
            if resource_type not in {"xhr", "fetch", "document"} and "json" not in content_type.lower():
                return
            if not CANDIDATE_URL_RE.search(url):
                return
            url_metadata = sanitize_url(url)
            event: dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "method": request.method,
                **url_metadata,
                "resource_type": resource_type,
                "status": response.status,
                "content_type": content_type,
                "request_headers": safe_headers(request.headers),
            }
            try:
                post_data = request.post_data
            except Exception:
                post_data = None
            event.update(request_body_metadata(post_data, url_metadata["url_base"]))
            if "json" in content_type.lower():
                try:
                    data = response.json()
                    event["json_shape"] = shape_json(data)
                    keys = first_record_keys(data)
                    if keys:
                        event["first_record_keys"] = keys
                    record = first_json_record(data)
                    if record and should_save_request_template(url_metadata["url_base"]):
                        event["first_record_url_pattern"] = redacted_url_pattern(record.get("url"))
                except Exception as exc:
                    event["json_error"] = f"{exc.__class__.__name__}: {exc}"
            append_jsonl(events_path, event)
            candidate_events.append(event)
            query_suffix = f" ?{','.join(url_metadata['query_keys'])}" if url_metadata["query_keys"] else ""
            print(f"[probe] {event['method']} {response.status} {url_metadata['url_base']}{query_suffix}", flush=True)

        attached_pages = set()

        def attach_page(page_to_attach) -> None:
            if page_to_attach in attached_pages:
                return
            attached_pages.add(page_to_attach)
            page_to_attach.on("response", on_response)

        for existing_page in context.pages:
            attach_page(existing_page)
        context.on("page", attach_page)
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)

        deadline = time.monotonic() + max(args.seconds, 30)
        while time.monotonic() < deadline:
            if not context.pages:
                break
            try:
                page = context.pages[-1]
                hints = visible_expiry_hints(page)
                if hints:
                    summary_path.write_text(
                        json.dumps(
                            {
                                "last_url": page.url,
                                "expiry_hints": hints,
                                "candidate_event_count": len(candidate_events),
                                "events_path": str(events_path),
                                "screenshot_path": str(screenshot_path),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                time.sleep(5)
            except KeyboardInterrupt:
                break
            except Exception:
                time.sleep(2)

        final_summary_written = False
        try:
            page = context.pages[-1]
            page.screenshot(path=str(screenshot_path), full_page=False)
            hints = visible_expiry_hints(page)
            summary_path.write_text(
                json.dumps(
                    {
                        "last_url": page.url,
                        "expiry_hints": hints,
                        "candidate_event_count": len(candidate_events),
                        "events_path": str(events_path),
                        "screenshot_path": str(screenshot_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            final_summary_written = True
        except Exception as exc:
            print(f"[probe] final capture warning: {exc}", flush=True)
        finally:
            try:
                context.close()
            except Exception as exc:
                print(f"[probe] context close warning: {exc}", flush=True)

    print(f"[probe] wrote {events_path}", flush=True)
    if summary_path.exists() or final_summary_written:
        print(f"[probe] wrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
