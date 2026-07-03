# Source Adapter Crawl Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the first phase of the SourceAdapter / Notice / CrawlRun architecture so configured sources are the real crawl unit and only validated notices reach the existing result pipeline.

**Architecture:** Add a source registry layer that merges URL sources, topology rules, and enabled-site config into `Source` objects. A source-backed crawler runs each source through `CrawlRunner` and `TopologySourceAdapter`, converts validated `Notice` objects to legacy `BidInfo`, and records observable crawl runs in SQLite while preserving existing result-center storage.

**Tech Stack:** Python 3, unittest/pytest, SQLite, existing `UrlListCrawler` parsing/fetching internals, existing `MonitorCore` and `Storage`.

---

## File Structure

- Create: `src/crawler/source_models.py`
  - Defines `Source`, `Notice`, `CrawlResult`, and `NoticeDeduplicator`.
  - Owns notice-to-`BidInfo` conversion and canonical notice key logic.
- Modify: `src/crawler/source_registry.py`
  - Keeps existing `UrlSource` / `load_url_sources`.
  - Adds topology loading and `build_sources()`.
- Modify: `src/database/storage.py`
  - Adds `crawl_runs` table migration and helper methods.
- Modify: `src/crawler/url_list.py`
  - Adds a config flag to preserve missing publish dates in the new source-backed path.
- Create: `src/crawler/source_adapter.py`
  - Adds `TopologySourceAdapter`, delegating fetch/traversal to `UrlListCrawler`.
- Create: `src/crawler/source_crawler.py`
  - Adds `CrawlRunner` and `SourceBackedCrawler`.
- Modify: `src/monitor_core.py`
  - Creates source-backed crawler for JSON URL sources.
  - Keeps txt/csv URL list compatibility.
  - Updates crawl-run inserted/skipped counts after save decisions.
- Modify: `tests/test_url_source_registry.py`
  - Adds `build_sources()` source filtering and topology merge tests.
- Create: `tests/test_crawl_run_storage.py`
  - Tests crawl-run table and helper methods.
- Create: `tests/test_source_adapter.py`
  - Tests detail validation, missing-date preservation, and notice dedupe.
- Create: `tests/test_source_crawler.py`
  - Tests runner/crawler run records and `BidInfo` conversion.
- Modify: `tests/test_monitor_core_url_sources.py`
  - Tests source-backed crawler construction and inserted counts.

---

### Task 1: Source Models And Registry

**Files:**
- Create: `src/crawler/source_models.py`
- Modify: `src/crawler/source_registry.py`
- Test: `tests/test_url_source_registry.py`

- [ ] **Step 1: Write failing source registry tests**

Append these tests to `tests/test_url_source_registry.py`:

```python
    def test_build_sources_filters_by_enabled_sites_and_merges_topology(self):
        from crawler.source_registry import build_sources

        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sources": [
                            {"id": "source-a", "name": "源 A", "url": "https://a.example/", "enabled": True},
                            {"id": "source-b", "name": "源 B", "url": "https://b.example/", "enabled": True},
                            {"id": "source-off", "name": "禁用源", "url": "https://off.example/", "enabled": False},
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sites": [
                            {
                                "id": "source-a",
                                "name": "拓扑 A",
                                "entry_url": "https://a.example/",
                                "allowed_hosts": ["a.example"],
                                "seed_urls": ["https://a.example/notices/"],
                                "detail_url_regex": [r"/detail/\d+$"],
                                "list_url_regex": [r"/notices/?$"],
                            },
                            {
                                "id": "source-b",
                                "name": "拓扑 B",
                                "entry_url": "https://b.example/",
                                "allowed_hosts": ["b.example"],
                                "seed_urls": ["https://b.example/notices/"],
                            },
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )

            sources = build_sources(
                sources_path,
                topologies_path,
                enabled_site_ids=["source-a"],
                site_metadata={"source-a": {"display_name": "展示名 A", "note": "keep"}},
                defaults={"domain_delay": 3, "auth_cookies": [{"domain": "a.example", "cookie": "sid=1"}]},
            )

        self.assertEqual([source.id for source in sources], ["source-a"])
        self.assertEqual(sources[0].name, "展示名 A")
        self.assertEqual(sources[0].url, "https://a.example/")
        self.assertEqual(sources[0].topology["id"], "source-a")
        self.assertEqual(sources[0].metadata["note"], "keep")
        self.assertEqual(sources[0].rate_limit["domain_delay"], 3)
        self.assertEqual(sources[0].auth_cookies[0]["cookie"], "sid=1")

    def test_build_sources_empty_enabled_sites_keeps_enabled_registry_defaults(self):
        from crawler.source_registry import build_sources

        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "sources": [
                            {"id": "source-a", "name": "源 A", "url": "https://a.example/", "enabled": True},
                            {"id": "source-off", "name": "禁用源", "url": "https://off.example/", "enabled": False},
                        ]
                    },
                    f,
                    ensure_ascii=False,
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                json.dump({"sites": []}, f)

            sources = build_sources(sources_path, topologies_path, enabled_site_ids=[])

        self.assertEqual([source.id for source in sources], ["source-a"])
        self.assertEqual(sources[0].topology, {})
```

- [ ] **Step 2: Run the source registry tests to verify RED**

Run:

```bash
python3 -m pytest tests/test_url_source_registry.py::UrlSourceRegistryTests::test_build_sources_filters_by_enabled_sites_and_merges_topology tests/test_url_source_registry.py::UrlSourceRegistryTests::test_build_sources_empty_enabled_sites_keeps_enabled_registry_defaults -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `build_sources`.

- [ ] **Step 3: Add source model dataclasses**

Create `src/crawler/source_models.py` with:

```python
"""Source-backed crawl models used by the phase-1 crawl pipeline."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    from database.storage import BidInfo
except ImportError:  # pragma: no cover
    from ..database.storage import BidInfo


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"spm", "from", "source", "src", "ref", "referer", "callback"}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    enabled: bool = True
    topology: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    rate_limit: dict[str, Any] = field(default_factory=dict)
    auth_cookies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Notice:
    source_id: str
    source_name: str
    title: str
    detail_url: str
    publish_date: str = ""
    source_item_id: str = ""
    notice_type: str = ""
    purchaser: str = ""
    region: str = ""
    content: str = ""
    content_hash: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)

    def to_bid_info(self) -> BidInfo:
        content = self.content or ""
        if self.raw:
            raw_text = json.dumps(self.raw, ensure_ascii=False, sort_keys=True)
            content = f"{content}\nraw: {raw_text}".strip()
        return BidInfo(
            title=self.title,
            url=self.detail_url,
            publish_date=self.publish_date or "",
            source=self.source_name,
            content=content,
            purchaser=self.purchaser,
        )


@dataclass
class CrawlResult:
    notices: list[Notice] = field(default_factory=list)
    fetched_count: int = 0
    candidate_count: int = 0
    parsed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


class NoticeDeduplicator:
    def __init__(self):
        self._seen: set[str] = set()

    def add(self, notice: Notice) -> bool:
        key = self.key_for(notice)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def key_for(self, notice: Notice) -> str:
        if notice.source_item_id:
            return f"item:{notice.source_id}:{notice.source_item_id}"
        normalized_url = normalize_notice_url(notice.detail_url)
        if normalized_url:
            return f"url:{notice.source_id}:{normalized_url}"
        weak = "|".join(
            [
                normalize_text(notice.title),
                normalize_text(notice.purchaser),
                notice.publish_date or "",
                normalize_text(notice.region),
            ]
        )
        return "weak:" + hashlib.sha256(weak.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).lower()


def normalize_notice_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in TRACKING_QUERY_KEYS or lower_key.startswith(TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    normalized = parsed._replace(fragment="", query=query)
    return urlunparse(normalized)
```

- [ ] **Step 4: Extend source registry**

Modify `src/crawler/source_registry.py`:

Add the import below existing imports:

```python
from .source_models import Source
```

Append these functions to the end of the file:

```python
def load_site_topologies(path: str) -> dict[str, dict[str, Any]]:
    topology_path = Path(path)
    if not path or not topology_path.exists():
        return {}
    payload = json.loads(topology_path.read_text(encoding="utf-8"))
    records = payload.get("sites") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        source_id = str(record.get("id", "")).strip()
        if source_id:
            result[source_id] = record
    return result


def build_sources(
    sources_path: str,
    topologies_path: str,
    enabled_site_ids: list[str] | None = None,
    site_metadata: dict[str, dict[str, Any]] | None = None,
    defaults: dict[str, Any] | None = None,
) -> list[Source]:
    enabled_filter = {str(item) for item in (enabled_site_ids or []) if item}
    metadata = site_metadata or {}
    defaults = defaults or {}
    topology_by_id = load_site_topologies(topologies_path)
    sources: list[Source] = []
    for url_source in load_url_sources(sources_path):
        if enabled_filter and url_source.id not in enabled_filter:
            continue
        source_metadata = metadata.get(url_source.id, {})
        display_name = source_metadata.get("display_name") or url_source.name
        sources.append(
            Source(
                id=url_source.id,
                name=display_name,
                url=url_source.url,
                enabled=True,
                topology=topology_by_id.get(url_source.id, {}),
                metadata=dict(source_metadata),
                rate_limit={"domain_delay": defaults.get("domain_delay", 0)},
                auth_cookies=list(defaults.get("auth_cookies") or []),
            )
        )
    return sources
```

- [ ] **Step 5: Run source registry tests to verify GREEN**

Run:

```bash
python3 -m pytest tests/test_url_source_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/crawler/source_models.py src/crawler/source_registry.py tests/test_url_source_registry.py
git commit -m "feat: add source registry models"
```

---

### Task 2: Crawl Run Storage

**Files:**
- Modify: `src/database/storage.py`
- Test: `tests/test_crawl_run_storage.py`

- [ ] **Step 1: Write failing crawl-run storage tests**

Create `tests/test_crawl_run_storage.py`:

```python
import os
import tempfile
import unittest

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from database.storage import Storage


class CrawlRunStorageTests(unittest.TestCase):
    def test_storage_migrates_crawl_runs_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            conn = storage._get_connection()

            columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()}

        self.assertIn("source_id", columns)
        self.assertIn("candidate_count", columns)
        self.assertIn("inserted_count", columns)
        self.assertIn("error_message", columns)

    def test_start_finish_increment_and_read_crawl_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))

            run_id = storage.start_crawl_run("source-a", "源 A")
            storage.increment_crawl_run_counts(run_id, inserted_delta=2, skipped_delta=1)
            storage.finish_crawl_run(
                run_id,
                "partial",
                {
                    "fetched_count": 3,
                    "candidate_count": 4,
                    "parsed_count": 2,
                    "error_count": 1,
                    "error_message": "one detail failed",
                },
            )
            run = storage.get_crawl_run(run_id)

        self.assertEqual(run["source_id"], "source-a")
        self.assertEqual(run["source_name"], "源 A")
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["fetched_count"], 3)
        self.assertEqual(run["candidate_count"], 4)
        self.assertEqual(run["parsed_count"], 2)
        self.assertEqual(run["inserted_count"], 2)
        self.assertEqual(run["skipped_count"], 1)
        self.assertEqual(run["error_count"], 1)
        self.assertEqual(run["error_message"], "one detail failed")
        self.assertTrue(run["started_at"])
        self.assertTrue(run["finished_at"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run crawl-run storage tests to verify RED**

Run:

```bash
python3 -m pytest tests/test_crawl_run_storage.py -q
```

Expected: FAIL because `crawl_runs` table and methods do not exist.

- [ ] **Step 3: Add crawl-run table and methods**

Modify `src/database/storage.py`:

After `RESULT_QUERY_FILTERS`, add:

```python
CRAWL_RUN_COLUMNS = {
    "source_id": "TEXT NOT NULL",
    "source_name": "TEXT DEFAULT ''",
    "started_at": "TEXT DEFAULT ''",
    "finished_at": "TEXT DEFAULT ''",
    "status": "TEXT DEFAULT 'running'",
    "fetched_count": "INTEGER DEFAULT 0",
    "candidate_count": "INTEGER DEFAULT 0",
    "parsed_count": "INTEGER DEFAULT 0",
    "inserted_count": "INTEGER DEFAULT 0",
    "updated_count": "INTEGER DEFAULT 0",
    "skipped_count": "INTEGER DEFAULT 0",
    "error_count": "INTEGER DEFAULT 0",
    "error_message": "TEXT DEFAULT ''",
}
```

Inside `_init_db()`, after the `bids` table creation block and before `self._migrate_schema(conn)`, add:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    source_name TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    finished_at TEXT DEFAULT '',
                    status TEXT DEFAULT 'running',
                    fetched_count INTEGER DEFAULT 0,
                    candidate_count INTEGER DEFAULT 0,
                    parsed_count INTEGER DEFAULT 0,
                    inserted_count INTEGER DEFAULT 0,
                    updated_count INTEGER DEFAULT 0,
                    skipped_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    error_message TEXT DEFAULT ''
                )
                """
            )
```

Inside `_migrate_schema()`, after the existing `bids` migration loop, add:

```python
        crawl_run_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()
        }
        for column, definition in CRAWL_RUN_COLUMNS.items():
            if column not in crawl_run_columns:
                conn.execute(f"ALTER TABLE crawl_runs ADD COLUMN {column} {definition}")
```

Add these methods before `count_all()`:

```python
    def start_crawl_run(self, source_id: str, source_name: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT INTO crawl_runs (source_id, source_name, started_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, source_name, now, "running"),
        )
        conn.commit()
        return cursor.lastrowid

    def finish_crawl_run(self, run_id: int, status: str, counts: Optional[dict] = None) -> None:
        counts = counts or {}
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE crawl_runs
            SET finished_at = ?, status = ?, fetched_count = ?, candidate_count = ?,
                parsed_count = ?, updated_count = ?, error_count = ?, error_message = ?
            WHERE id = ?
            """,
            (
                datetime.utcnow().isoformat(timespec="seconds"),
                status,
                int(counts.get("fetched_count", 0)),
                int(counts.get("candidate_count", 0)),
                int(counts.get("parsed_count", 0)),
                int(counts.get("updated_count", 0)),
                int(counts.get("error_count", 0)),
                str(counts.get("error_message", ""))[:500],
                run_id,
            ),
        )
        conn.commit()

    def increment_crawl_run_counts(
        self,
        run_id: int,
        inserted_delta: int = 0,
        updated_delta: int = 0,
        skipped_delta: int = 0,
    ) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE crawl_runs
            SET inserted_count = inserted_count + ?,
                updated_count = updated_count + ?,
                skipped_count = skipped_count + ?
            WHERE id = ?
            """,
            (inserted_delta, updated_delta, skipped_delta, run_id),
        )
        conn.commit()

    def get_crawl_run(self, run_id: int) -> Optional[dict]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_recent_crawl_runs(self, limit: int = 50) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM crawl_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Run crawl-run storage tests to verify GREEN**

Run:

```bash
python3 -m pytest tests/test_crawl_run_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: Run storage regression tests**

Run:

```bash
python3 -m pytest tests/test_storage_results_center.py tests/test_crawl_run_storage.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/database/storage.py tests/test_crawl_run_storage.py
git commit -m "feat: record source crawl runs"
```

---

### Task 3: Topology Source Adapter And Notice Admission

**Files:**
- Modify: `src/crawler/url_list.py`
- Create: `src/crawler/source_adapter.py`
- Test: `tests/test_source_adapter.py`

- [ ] **Step 1: Write failing source adapter tests**

Create `tests/test_source_adapter.py`:

```python
import os
import tempfile
import unittest
from unittest.mock import patch

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_adapter import TopologySourceAdapter
from crawler.source_models import Notice, NoticeDeduplicator, Source


class TopologySourceAdapterTests(unittest.TestCase):
    def make_source(self):
        return Source(
            id="portal",
            name="入口测试",
            url="https://portal.example.com/",
            topology={
                "id": "portal",
                "name": "入口测试",
                "entry_url": "https://portal.example.com/",
                "allowed_hosts": ["portal.example.com"],
                "seed_urls": ["https://portal.example.com/notices/"],
                "list_url_regex": [r"/notices/?$"],
                "detail_url_regex": [r"/detail/\d+(?:\?.*)?$"],
            },
        )

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_adapter_emits_notice_only_after_detail_page_is_verified(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return ("<html><body><a href='/notices/'>招标公告</a></body></html>", 200, "OK")
            if url == "https://portal.example.com/notices/":
                return (
                    "<html><body><a href='/detail/42'>上海弱电工程公开招标公告</a></body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海弱电工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购弱电智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"timeout": 1, "max_retries": 1}).collect(self.make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].title, "上海弱电工程公开招标公告")
        self.assertEqual(result.notices[0].detail_url, "https://portal.example.com/detail/42")
        self.assertEqual(result.notices[0].publish_date, "2026-07-02")
        self.assertGreaterEqual(result.candidate_count, 1)
        self.assertEqual(result.parsed_count, 1)

    @patch("crawler.url_list.UrlListCrawler._request_url")
    def test_adapter_preserves_missing_publish_date_as_empty(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return ("<html><body><a href='/detail/42'>上海弱电工程公开招标公告</a></body></html>", 200, "OK")
            if url == "https://portal.example.com/detail/42":
                return (
                    "<html><body><h1>上海弱电工程公开招标公告</h1>"
                    "<p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购弱电智能化系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        result = TopologySourceAdapter({"timeout": 1, "max_retries": 1}).collect(self.make_source())

        self.assertEqual(len(result.notices), 1)
        self.assertEqual(result.notices[0].publish_date, "")

    def test_notice_deduplicator_collapses_tracking_query_variants(self):
        dedupe = NoticeDeduplicator()
        first = Notice(
            source_id="portal",
            source_name="入口测试",
            title="上海弱电工程公开招标公告",
            detail_url="https://portal.example.com/detail/42?utm_source=x&b=2&a=1",
        )
        second = Notice(
            source_id="portal",
            source_name="入口测试",
            title="上海弱电工程公开招标公告",
            detail_url="https://portal.example.com/detail/42?a=1&b=2&utm_campaign=y",
        )

        self.assertTrue(dedupe.add(first))
        self.assertFalse(dedupe.add(second))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run source adapter tests to verify RED**

Run:

```bash
python3 -m pytest tests/test_source_adapter.py -q
```

Expected: FAIL because `crawler.source_adapter` does not exist and `UrlListCrawler` cannot preserve missing dates yet.

- [ ] **Step 3: Add missing-date preservation to UrlListCrawler**

Modify `src/crawler/url_list.py`:

Inside `UrlListCrawler.__init__`, after `self.auth_cookies = ...`, add:

```python
        self.preserve_missing_publish_date = bool(config.get("preserve_missing_publish_date"))
```

Add this helper near `_normalize_date()`:

```python
    def _fallback_publish_date(self) -> str:
        return "" if self.preserve_missing_publish_date else datetime.now().strftime("%Y-%m-%d")
```

Replace each `datetime.now().strftime("%Y-%m-%d")` publish-date fallback inside `_parse_page()`, `_parse_json_records()`, `_extract_detail_bid()`, and `_extract_announcement_links()` with `self._fallback_publish_date()`.

The important replacements are:

```python
publish_date=fields.get("publish_date") or self._fallback_publish_date()
```

```python
publish_date or self._fallback_publish_date()
```

```python
publish_date = fields.get("publish_date") or self._fallback_publish_date()
```

```python
publish_date = self._extract_date(context) or self._fallback_publish_date()
```

- [ ] **Step 4: Add TopologySourceAdapter**

Create `src/crawler/source_adapter.py`:

```python
"""Source adapters for the phase-1 source-backed crawl pipeline."""
from __future__ import annotations

from typing import Any

from .source_models import CrawlResult, Notice, NoticeDeduplicator, Source
from .url_list import UrlListCrawler


class TopologySourceAdapter:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.config["preserve_missing_publish_date"] = True

    def collect(self, source: Source, stop_event=None) -> CrawlResult:
        source_config = {
            "name": source.name,
            "file_path": "",
            "enabled": source.enabled,
            "auth_cookies": source.auth_cookies,
            "domain_delay": source.rate_limit.get("domain_delay", self.config.get("domain_delay", 0)),
        }
        crawler = UrlListCrawler(self.config, source_config)
        if source.topology:
            crawler.site_topologies = [source.topology]

        result = CrawlResult()
        dedupe = NoticeDeduplicator()
        try:
            bids = crawler._crawl_one_entry(1, 1, source.url, stop_event=stop_event)
            result.fetched_count = len(getattr(crawler, "_last_domain_request_at", {}) or {source.url: True})
            result.candidate_count = max(len(bids), 0)
            for bid in bids:
                notice = Notice(
                    source_id=source.id,
                    source_name=source.name,
                    title=bid.title,
                    detail_url=bid.url,
                    publish_date=bid.publish_date or "",
                    purchaser=bid.purchaser or "",
                    content=bid.content or "",
                    raw={"legacy_source": bid.source},
                )
                if not notice.title or not notice.detail_url:
                    result.skipped_count += 1
                    continue
                if not dedupe.add(notice):
                    result.skipped_count += 1
                    continue
                result.notices.append(notice)
            result.parsed_count = len(result.notices)
        except Exception as exc:
            result.error_count += 1
            result.errors.append(str(exc)[:500])
        return result
```

- [ ] **Step 5: Run source adapter tests to verify GREEN**

Run:

```bash
python3 -m pytest tests/test_source_adapter.py -q
```

Expected: PASS.

- [ ] **Step 6: Run URL list regression tests**

Run:

```bash
python3 -m pytest tests/test_url_list_crawler.py tests/test_source_adapter.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/crawler/url_list.py src/crawler/source_adapter.py tests/test_source_adapter.py
git commit -m "feat: adapt topology crawl results into notices"
```

---

### Task 4: Crawl Runner And Source-Backed Crawler

**Files:**
- Create: `src/crawler/source_crawler.py`
- Test: `tests/test_source_crawler.py`

- [ ] **Step 1: Write failing source crawler tests**

Create `tests/test_source_crawler.py`:

```python
import os
import tempfile
import unittest

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_crawler import CrawlRunner, SourceBackedCrawler
from crawler.source_models import CrawlResult, Notice, Source
from database.storage import Storage


class FakeAdapter:
    def collect(self, source, stop_event=None):
        return CrawlResult(
            notices=[
                Notice(
                    source_id=source.id,
                    source_name=source.name,
                    title="上海智能化公开招标",
                    detail_url="https://example.com/detail/1",
                    publish_date="2026-07-02",
                    content="弱电智能化",
                )
            ],
            fetched_count=2,
            candidate_count=3,
            parsed_count=1,
        )


class SourceCrawlerTests(unittest.TestCase):
    def test_crawl_runner_records_run_and_tags_bidinfo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            source = Source(id="source-a", name="源 A", url="https://example.com/")
            runner = CrawlRunner(storage, adapter=FakeAdapter())

            bids = runner.run_source(source)
            runs = storage.get_recent_crawl_runs()

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].title, "上海智能化公开招标")
        self.assertEqual(getattr(bids[0], "crawl_run_id"), runs[0]["id"])
        self.assertEqual(getattr(bids[0], "source_id"), "source-a")
        self.assertEqual(runs[0]["source_id"], "source-a")
        self.assertEqual(runs[0]["status"], "success")
        self.assertEqual(runs[0]["fetched_count"], 2)
        self.assertEqual(runs[0]["candidate_count"], 3)
        self.assertEqual(runs[0]["parsed_count"], 1)

    def test_source_backed_crawler_runs_multiple_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            sources = [
                Source(id="source-a", name="源 A", url="https://a.example/"),
                Source(id="source-b", name="源 B", url="https://b.example/"),
            ]
            crawler = SourceBackedCrawler(
                sources,
                {"timeout": 1},
                storage_provider=lambda: storage,
                adapter_factory=lambda config: FakeAdapter(),
            )

            bids = crawler.crawl()
            runs = storage.get_recent_crawl_runs()

        self.assertEqual(crawler.name, "配置数据源")
        self.assertEqual(len(bids), 2)
        self.assertEqual({run["source_id"] for run in runs}, {"source-a", "source-b"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run source crawler tests to verify RED**

Run:

```bash
python3 -m pytest tests/test_source_crawler.py -q
```

Expected: FAIL because `crawler.source_crawler` does not exist.

- [ ] **Step 3: Add CrawlRunner and SourceBackedCrawler**

Create `src/crawler/source_crawler.py`:

```python
"""Crawler facade and runner for configured Source objects."""
from __future__ import annotations

from typing import Any, Callable

from .source_adapter import TopologySourceAdapter
from .source_models import Source


class CrawlRunner:
    def __init__(self, storage, adapter=None, log_callback: Callable[[str], None] | None = None):
        self.storage = storage
        self.adapter = adapter or TopologySourceAdapter()
        self.log_callback = log_callback or (lambda _message: None)

    def run_source(self, source: Source, stop_event=None):
        run_id = self.storage.start_crawl_run(source.id, source.name)
        result = self.adapter.collect(source, stop_event=stop_event)
        status = self._status_for(result)
        self.storage.finish_crawl_run(
            run_id,
            status,
            {
                "fetched_count": result.fetched_count,
                "candidate_count": result.candidate_count,
                "parsed_count": result.parsed_count,
                "skipped_count": result.skipped_count,
                "error_count": result.error_count,
                "error_message": "; ".join(result.errors)[:500],
            },
        )
        bids = []
        for notice in result.notices:
            bid = notice.to_bid_info()
            setattr(bid, "crawl_run_id", run_id)
            setattr(bid, "source_id", source.id)
            bids.append(bid)
        return bids

    def _status_for(self, result) -> str:
        if result.error_count and result.notices:
            return "partial"
        if result.error_count and not result.notices:
            return "failed"
        if not result.notices:
            return "skipped"
        return "success"


class SourceBackedCrawler:
    name = "配置数据源"

    def __init__(
        self,
        sources: list[Source],
        config: dict[str, Any] | None,
        storage_provider: Callable[[], Any],
        adapter_factory: Callable[[dict[str, Any]], Any] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        self.sources = list(sources)
        self.config = dict(config or {})
        self.storage_provider = storage_provider
        self.adapter_factory = adapter_factory or (lambda config: TopologySourceAdapter(config))
        self.log_callback = log_callback or (lambda _message: None)

    def crawl(self, stop_event=None):
        all_bids = []
        storage = self.storage_provider()
        for source in self.sources:
            if stop_event and stop_event.is_set():
                break
            adapter = self.adapter_factory(self.config)
            runner = CrawlRunner(storage, adapter=adapter, log_callback=self.log_callback)
            all_bids.extend(runner.run_source(source, stop_event=stop_event))
        return all_bids
```

- [ ] **Step 4: Run source crawler tests to verify GREEN**

Run:

```bash
python3 -m pytest tests/test_source_crawler.py -q
```

Expected: PASS.

- [ ] **Step 5: Run source-related tests**

Run:

```bash
python3 -m pytest tests/test_url_source_registry.py tests/test_source_adapter.py tests/test_source_crawler.py tests/test_crawl_run_storage.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/crawler/source_crawler.py tests/test_source_crawler.py
git commit -m "feat: run configured sources with crawl records"
```

---

### Task 5: MonitorCore Source-Backed Integration

**Files:**
- Modify: `src/monitor_core.py`
- Modify: `tests/test_monitor_core_url_sources.py`

- [ ] **Step 1: Write failing MonitorCore tests**

Append these tests to `tests/test_monitor_core_url_sources.py`:

```python
    def test_monitor_core_builds_source_backed_crawler_for_json_sources_filtered_by_enabled_sites(self):
        from crawler.source_crawler import SourceBackedCrawler

        with tempfile.TemporaryDirectory() as tmpdir:
            sources_path = os.path.join(tmpdir, "url_sources.json")
            topologies_path = os.path.join(tmpdir, "site_topologies.json")
            with open(sources_path, "w", encoding="utf-8") as f:
                f.write(
                    '{"sources": ['
                    '{"id": "source-a", "name": "源 A", "url": "https://a.example/", "enabled": true},'
                    '{"id": "source-b", "name": "源 B", "url": "https://b.example/", "enabled": true}'
                    ']}'
                )
            with open(topologies_path, "w", encoding="utf-8") as f:
                f.write('{"sites": [{"id": "source-a", "allowed_hosts": ["a.example"], "seed_urls": []}]}')

            monitor = MonitorCore(
                keywords=["弱电"],
                notify_method="none",
                crawler_overrides={
                    "enabled_sites": ["source-a"],
                    "use_selenium": False,
                    "site_topologies_path": topologies_path,
                    "csv_url_sources": [
                        {
                            "name": "招标URL源",
                            "file_path": sources_path,
                            "source_type": "json",
                            "enabled": True,
                        }
                    ],
                },
            )

        source_crawlers = [crawler for crawler in monitor.crawlers if isinstance(crawler, SourceBackedCrawler)]
        self.assertEqual(len(source_crawlers), 1)
        self.assertEqual([source.id for source in source_crawlers[0].sources], ["source-a"])

    def test_monitor_core_updates_crawl_run_inserted_and_skipped_counts(self):
        class RunTaggedCrawler:
            name = "fake-source"

            def __init__(self, run_id):
                self.run_id = run_id

            def crawl(self, stop_event=None):
                bid = BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "弱电智能化")
                setattr(bid, "crawl_run_id", self.run_id)
                return [bid]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "bids.db")
            monitor = MonitorCore(
                keywords=["智能化"],
                notify_method="none",
                crawler_overrides={"enabled_sites": [], "csv_url_sources": []},
            )
            monitor.storage = Storage(db_path)
            run_id = monitor.storage.start_crawl_run("source-a", "源 A")
            monitor.crawlers = [RunTaggedCrawler(run_id)]

            with patch.object(monitor_core_module, "enrich_new_bid"):
                result = monitor.run_once()
            run = monitor.storage.get_crawl_run(run_id)

        self.assertEqual(result["new_count"], 1)
        self.assertEqual(run["inserted_count"], 1)
        self.assertEqual(run["skipped_count"], 0)
```

Also add this import near the existing imports in `tests/test_monitor_core_url_sources.py`:

```python
from database.storage import BidInfo, Storage
```

Replace the existing `from database.storage import Storage` import to avoid importing `Storage` twice.

- [ ] **Step 2: Run MonitorCore tests to verify RED**

Run:

```bash
python3 -m pytest tests/test_monitor_core_url_sources.py::MonitorCoreUrlSourcesTests::test_monitor_core_builds_source_backed_crawler_for_json_sources_filtered_by_enabled_sites tests/test_monitor_core_url_sources.py::MonitorCoreUrlSourcesTests::test_monitor_core_updates_crawl_run_inserted_and_skipped_counts -q
```

Expected: FAIL because `MonitorCore` still creates `UrlListCrawler` for JSON sources and does not increment crawl-run insert counts.

- [ ] **Step 3: Import source-backed crawl components in MonitorCore**

Modify `src/monitor_core.py`:

Replace:

```python
from crawler.source_registry import load_url_sources
```

with:

```python
from crawler.source_registry import build_sources, load_url_sources
from crawler.source_crawler import SourceBackedCrawler
```

- [ ] **Step 4: Build SourceBackedCrawler for JSON URL source configs**

In `_init_crawlers()`, replace the JSON branch inside the `csv_url_sources` loop with this behavior.

Use this full replacement for lines that currently instantiate `UrlListCrawler`:

```python
                    is_json_source = source.get("source_type") == "json" or str(file_path).lower().endswith(".json")
                    if is_json_source:
                        sources = build_sources(
                            file_path,
                            source.get("site_topologies_path")
                            or crawler_config.get("site_topologies_path")
                            or os.path.join(BASE_DIR, "server", "site_topologies.json"),
                            enabled_site_ids=enabled,
                            site_metadata=self.config.get("site_metadata", {}),
                            defaults=source,
                        )
                        if not sources:
                            self.log(f"[WARN] Source registry {name} has no enabled sources")
                            continue
                        crawler = SourceBackedCrawler(
                            sources,
                            crawler_config,
                            storage_provider=lambda self=self: self.storage,
                            log_callback=self.log,
                        )
                        crawlers.append(crawler)
                        self.log(f"[OK] Loaded source registry crawler: {name} ({len(sources)} sources)")
                        continue

                    crawler = UrlListCrawler(crawler_config, source)
                    crawlers.append(crawler)
                    self.log(f"[OK] Loaded URL list crawler: {name}")
```

Keep txt/csv sources on `UrlListCrawler`.

- [ ] **Step 5: Increment crawl-run counts in `run_once()`**

Inside `MonitorCore.run_once()`, after a bid is saved successfully:

```python
                                crawl_run_id = getattr(bid, "crawl_run_id", None)
                                if crawl_run_id:
                                    self.storage.increment_crawl_run_counts(crawl_run_id, inserted_delta=1)
```

Inside the branch where the bid matched but already exists, add:

```python
                        else:
                            crawl_run_id = getattr(bid, "crawl_run_id", None)
                            if crawl_run_id:
                                self.storage.increment_crawl_run_counts(crawl_run_id, skipped_delta=1)
```

The final structure around save should be:

```python
                        if not self.storage.exists(bid):
                            result_id = self.storage.save(bid, notified=False)
                            if result_id:
                                crawl_run_id = getattr(bid, "crawl_run_id", None)
                                if crawl_run_id:
                                    self.storage.increment_crawl_run_counts(crawl_run_id, inserted_delta=1)
                                all_matched_bids.append(bid)
                                matched_count += 1
                                enrich_new_bid(
                                    self.storage,
                                    result_id,
                                    bid,
                                    self.ai_config_for_extraction,
                                    log_callback=self.log,
                                    fetch_config=self.config.get('crawler', {}),
                                )
                        else:
                            crawl_run_id = getattr(bid, "crawl_run_id", None)
                            if crawl_run_id:
                                self.storage.increment_crawl_run_counts(crawl_run_id, skipped_delta=1)
```

- [ ] **Step 6: Run MonitorCore tests to verify GREEN**

Run:

```bash
python3 -m pytest tests/test_monitor_core_url_sources.py -q
```

Expected: PASS.

- [ ] **Step 7: Run monitor/browser regression tests**

Run:

```bash
python3 -m pytest tests/test_monitor_core_url_sources.py tests/test_monitor_core_browser_mode.py tests/test_monitor_core_ai_extraction.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/monitor_core.py tests/test_monitor_core_url_sources.py
git commit -m "feat: run json url sources through source registry"
```

---

### Task 6: End-To-End Regression And Documentation Check

**Files:**
- No production files expected.
- Existing tests only.

- [ ] **Step 1: Run focused source pipeline tests**

Run:

```bash
python3 -m pytest tests/test_url_source_registry.py tests/test_crawl_run_storage.py tests/test_source_adapter.py tests/test_source_crawler.py tests/test_monitor_core_url_sources.py -q
```

Expected: PASS.

- [ ] **Step 2: Run server config and result-center regression tests**

Run:

```bash
python3 -m pytest tests/test_server_config_defaults.py tests/test_server_results_api.py tests/test_storage_results_center.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
python3 -m pytest
```

Expected: PASS with the existing skipped browser tests only.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended source pipeline, storage, monitor, test, and plan/spec files are changed.

- [ ] **Step 5: Commit the implementation plan if not already committed**

```bash
git add docs/superpowers/plans/2026-07-03-source-adapter-crawlrun.md
git commit -m "docs: plan source adapter crawl run implementation"
```

If the plan was committed before execution, skip this step and leave no extra commit.

---

## Self-Review

Spec coverage:

- Source model and enablement filtering: Task 1.
- CrawlRun storage: Task 2.
- Notice and SourceAdapter admission: Task 3.
- CrawlRunner and source-backed crawler: Task 4.
- MonitorCore integration: Task 5.
- Regression verification: Task 6.

Placeholder scan:

- No placeholder markers or open-ended implementation instructions.
- Each behavior has a failing test command and expected failure.
- Each production behavior has concrete code or exact edit instructions.

Type consistency:

- `Source`, `Notice`, `CrawlResult`, and `NoticeDeduplicator` are defined in Task 1 and reused consistently.
- `TopologySourceAdapter.collect()` returns `CrawlResult`.
- `CrawlRunner.run_source()` tags returned `BidInfo` objects with `crawl_run_id` and `source_id`.
- `MonitorCore.run_once()` reads `crawl_run_id` from `BidInfo` and updates `Storage.increment_crawl_run_counts()`.
