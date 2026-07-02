# Results Center AI Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a spreadsheet-like results center with automatic detail-page AI extraction, editable review workflow fields, bulk review editing, and removal of colleague-facing custom URL/contact/notification UI entry points.

**Architecture:** Extend the existing SQLite `bids` storage with column-backed high-frequency fields and JSON-backed AI/manual data. Add a focused result service layer for validation, merged display values, detail fetching, and AI extraction, then expose it through FastAPI routes consumed by the vanilla JS frontend table and detail side panel. Work is split so storage/API contracts land first, then AI extraction, frontend, and entry-point cleanup can proceed in parallel.

**Tech Stack:** Python 3, SQLite, FastAPI-style route functions in `server/app.py`, vanilla HTML/CSS/JavaScript in `server/static`, `unittest` tests, `requests`, `BeautifulSoup`/`lxml` when available.

## Global Constraints

- Do not implement per-site login adaptation, membership level display, remaining membership time, or site-specific search algorithms in this stage.
- Keep existing notification modules under `src/notifier/*`; hide Web UI entry points only.
- Remove the custom URL feature from Web UI, API, and config for this stage.
- Preserve existing results and old SQLite databases through additive migration.
- API keys must never be returned to the browser in plaintext.
- New results must remain visible even when detail fetch or AI extraction fails.
- Manual urgency must not be overwritten by automatic urgency suggestions.
- Use TDD for each task: write or update failing tests first, verify failure, implement, verify pass.
- Avoid broad refactors and do not revert unrelated existing work in the dirty tree.

---

## Parallel Execution Strategy

Wave 1 must run first because it defines shared data contracts:

- Task 1: Storage migration, result models, validation helpers.

After Task 1 passes, dispatch these independent subagents in parallel:

- Task 2: AI extraction and detail fetch service.
- Task 3: Results API and settings API.
- Task 4: Frontend results table/detail/bulk edit UI.
- Task 5: Remove custom URL/contact/notification UI entry points and custom-sites API/config.

Task 6 runs last in the main session to integrate, resolve conflicts, run targeted tests, and verify the minimum usable workflow.

Expected fast path for the 1-hour window:

1. Finish Task 1.
2. Run Tasks 2-5 in parallel.
3. Integrate Task 6 with targeted tests: storage, server config/API, AI client, static frontend assets.

## File Structure

- `src/database/storage.py`: Owns SQLite schema migration, `BidInfo` shape, CRUD/query/update methods for results center fields.
- `src/results/__init__.py`: Package marker for result-center helpers.
- `src/results/review.py`: Review enums, reason defaults, validation, merge of AI/manual/original values.
- `src/results/detail_fetcher.py`: Detail-page fetching and HTML-to-text cleanup.
- `src/results/ai_extractor.py`: AI client supporting `responses` and `chat_completions`, strict JSON extraction parsing, field sync helpers.
- `src/monitor_core.py`: Calls result enrichment for new saved results after keyword/AI relevance filtering.
- `server/app.py`: Adds result/settings APIs, masks AI keys, removes custom-sites API.
- `server/static/index.html`: Replaces results card area with table shell, side panel, bulk edit modal, removes/hides contact and custom URL UI.
- `server/static/app.js`: Results table state, filters, detail side panel, review updates, bulk edits, AI config endpoint type, removal of custom site/contact calls.
- `server/static/styles.css`: Dense table, toolbar, side panel, bulk modal, responsive behavior.
- `tests/test_storage_results_center.py`: Storage migration and result CRUD tests.
- `tests/test_result_review.py`: Review validation and display merge tests.
- `tests/test_ai_extractor.py`: AI endpoint payload/parse tests.
- `tests/test_server_results_api.py`: Result/settings route tests.
- `tests/test_server_config_defaults.py`: Config defaults and custom-sites removal updates.
- `tests/test_static_frontend_assets.py`: Frontend DOM/JS/CSS contract updates.
- `tests/test_monitor_core_ai_extraction.py`: MonitorCore triggers extraction for newly saved results without hiding failures.

---

### Task 1: Storage Migration and Review Domain Contracts

**Files:**
- Modify: `src/database/storage.py`
- Create: `src/results/__init__.py`
- Create: `src/results/review.py`
- Create: `tests/test_storage_results_center.py`
- Create: `tests/test_result_review.py`

**Interfaces:**
- Produces: `src.results.review.DEFAULT_NON_FOLLOW_REASON_TAGS: list[str]`
- Produces: `src.results.review.validate_review_update(payload: dict, reason_tags: list[str]) -> dict`
- Produces: `src.results.review.resolve_result_data(bid: BidInfo) -> dict`
- Produces: `Storage.get_by_id(result_id: int) -> BidInfo | None`
- Produces: `Storage.query_results(filters: dict | None = None, limit: int = 50, offset: int = 0) -> tuple[list[BidInfo], int]`
- Produces: `Storage.update_review(result_ids: list[int], update: dict) -> None`
- Produces: `Storage.update_manual_overrides(result_id: int, overrides: dict) -> None`
- Produces: `Storage.update_ai_extraction(result_id: int, status: str, ai_data: dict | None, columns: dict | None, error: str | None = None) -> None`
- Produces: `Storage.update_detail_fetch(result_id: int, status: str, detail_text: str = "", error: str | None = None) -> None`
- Produces: `Storage.save(...)` returns the inserted row id for new rows and `False` for duplicates, while preserving existing truthiness behavior for callers.

- [ ] **Step 1: Write failing storage migration tests**

Create `tests/test_storage_results_center.py`:

```python
import json
import os
import sqlite3
import tempfile
import unittest

from src.database.storage import BidInfo, Storage


class StorageResultsCenterTests(unittest.TestCase):
    def make_storage(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        return Storage(os.path.join(tmpdir.name, "bids.db"))

    def test_new_database_has_results_center_columns(self):
        storage = self.make_storage()
        conn = sqlite3.connect(storage.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(bids)").fetchall()}

        for column in [
            "fit_status",
            "follow_decision",
            "urgency",
            "urgency_source",
            "project_stage",
            "amount",
            "amount_unit",
            "region",
            "category",
            "project_type",
            "nature",
            "registration_deadline",
            "submission_deadline",
            "bid_opening_time",
            "deadline_source",
            "urgency_reference_time",
            "urgency_reference_type",
            "ai_extract_status",
            "detail_fetch_status",
            "detail_fetched_at",
            "detail_text",
            "ai_extracted_data",
            "manual_overrides",
            "non_follow_reasons",
            "review_notes",
            "ai_recommendation",
            "ai_extract_error",
            "detail_fetch_error",
            "updated_at",
        ]:
            self.assertIn(column, columns)

    def test_existing_database_is_migrated_without_losing_rows(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "bids.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE bids (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    publish_date TEXT,
                    source TEXT,
                    content TEXT,
                    purchaser TEXT,
                    notified INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO bids (unique_id, title, url, publish_date, source) VALUES (?, ?, ?, ?, ?)",
                ("u1", "旧项目", "https://example.com/1", "2026-07-01", "测试源"),
            )

        storage = Storage(db_path)
        bid = storage.get_all()[0]

        self.assertEqual(bid.title, "旧项目")
        self.assertEqual(bid.fit_status, "pending")
        self.assertEqual(bid.follow_decision, "pending")
        self.assertEqual(bid.project_stage, "lead")
        self.assertEqual(bid.ai_extract_status, "pending")

    def test_save_returns_row_id_and_defaults_review_fields(self):
        storage = self.make_storage()
        result_id = storage.save(
            BidInfo(
                title="上海智能化公开招标",
                url="https://example.com/result/1",
                publish_date="2026-07-01",
                source="测试源",
                content="弱电智能化项目",
            )
        )

        self.assertIsInstance(result_id, int)
        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.fit_status, "pending")
        self.assertEqual(bid.follow_decision, "pending")
        self.assertEqual(bid.project_stage, "lead")
        self.assertEqual(bid.ai_extract_status, "pending")
        self.assertEqual(storage.save(bid), False)

    def test_query_update_review_and_manual_overrides(self):
        storage = self.make_storage()
        result_id = storage.save(BidInfo("项目A", "https://example.com/a", "2026-07-01", "源"))

        storage.update_review(
            [result_id],
            {
                "fit_status": "not_fit",
                "follow_decision": "not_follow",
                "urgency": "high",
                "urgency_source": "manual",
                "project_stage": "screening",
                "non_follow_reasons": ["地域问题", "其它"],
                "review_notes": "外省项目，先不跟进",
            },
        )
        storage.update_manual_overrides(result_id, {"organization": "人工单位", "amount": "120000"})

        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.fit_status, "not_fit")
        self.assertEqual(bid.follow_decision, "not_follow")
        self.assertEqual(bid.urgency, "high")
        self.assertEqual(bid.non_follow_reasons, ["地域问题", "其它"])
        self.assertEqual(bid.manual_overrides["organization"], "人工单位")

        rows, total = storage.query_results({"follow_decision": "not_follow"}, limit=10, offset=0)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].id, result_id)

    def test_update_ai_extraction_syncs_columns_and_json(self):
        storage = self.make_storage()
        result_id = storage.save(BidInfo("项目A", "https://example.com/a", "2026-07-01", "源"))

        ai_data = {
            "organization": "上海某单位",
            "amount": "50",
            "amount_unit": "万元",
            "region": "上海",
            "category": "弱电智能化",
            "project_type": "公开招标",
            "nature": "服务",
            "deadlines": [
                {"type": "submission_deadline", "end_at": "2026-07-05 10:00", "raw_text": "投标截止"},
            ],
        }
        storage.update_ai_extraction(
            result_id,
            "extracted",
            ai_data,
            {
                "amount": "50",
                "amount_unit": "万元",
                "region": "上海",
                "category": "弱电智能化",
                "project_type": "公开招标",
                "nature": "服务",
                "submission_deadline": "2026-07-05 10:00",
                "deadline_source": "ai",
            },
        )

        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.ai_extract_status, "extracted")
        self.assertEqual(bid.region, "上海")
        self.assertEqual(bid.submission_deadline, "2026-07-05 10:00")
        self.assertEqual(bid.ai_extracted_data["organization"], "上海某单位")
```

- [ ] **Step 2: Write failing review helper tests**

Create `tests/test_result_review.py`:

```python
import unittest

from src.database.storage import BidInfo
from src.results.review import (
    DEFAULT_NON_FOLLOW_REASON_TAGS,
    resolve_result_data,
    validate_review_update,
)


class ResultReviewTests(unittest.TestCase):
    def test_default_non_follow_reason_tags_include_required_business_reasons(self):
        for tag in ["地域问题", "金额不合适", "项目类型不匹配", "资质不满足", "时间太紧", "信息不完整", "重复项目", "已过期", "其它"]:
            self.assertIn(tag, DEFAULT_NON_FOLLOW_REASON_TAGS)

    def test_validate_review_update_rejects_not_follow_without_reason(self):
        with self.assertRaises(ValueError) as ctx:
            validate_review_update(
                {"follow_decision": "not_follow", "non_follow_reasons": []},
                DEFAULT_NON_FOLLOW_REASON_TAGS,
            )

        self.assertIn("non_follow_reasons", str(ctx.exception))

    def test_validate_review_update_rejects_unknown_enum_and_reason(self):
        with self.assertRaises(ValueError):
            validate_review_update({"urgency": "now"}, DEFAULT_NON_FOLLOW_REASON_TAGS)

        with self.assertRaises(ValueError):
            validate_review_update(
                {"follow_decision": "not_follow", "non_follow_reasons": ["未知原因"]},
                DEFAULT_NON_FOLLOW_REASON_TAGS,
            )

    def test_validate_review_update_normalizes_valid_payload(self):
        normalized = validate_review_update(
            {
                "fit_status": "not_fit",
                "follow_decision": "not_follow",
                "urgency": "urgent",
                "project_stage": "screening",
                "non_follow_reasons": ["地域问题"],
                "review_notes": "外地项目",
            },
            DEFAULT_NON_FOLLOW_REASON_TAGS,
        )

        self.assertEqual(normalized["urgency_source"], "manual")
        self.assertEqual(normalized["non_follow_reasons"], ["地域问题"])

    def test_resolve_result_data_prefers_manual_then_ai_then_original(self):
        bid = BidInfo(
            title="原始标题",
            url="https://example.com/a",
            publish_date="2026-07-01",
            source="源",
            purchaser="原始采购人",
        )
        bid.ai_extracted_data = {
            "organization": "AI单位",
            "amount": "80",
            "deadlines": [{"type": "submission_deadline", "end_at": "2026-07-04"}],
        }
        bid.manual_overrides = {"organization": "人工单位"}

        resolved = resolve_result_data(bid)

        self.assertEqual(resolved["organization"], "人工单位")
        self.assertEqual(resolved["amount"], "80")
        self.assertEqual(resolved["title"], "原始标题")
```

- [ ] **Step 3: Run the new tests and confirm they fail**

Run: `python3 -m unittest tests.test_storage_results_center tests.test_result_review -v`

Expected: FAIL because `src.results.review` and new `Storage` methods/fields do not exist.

- [ ] **Step 4: Implement storage schema, dataclass fields, JSON helpers, and review helpers**

Modify `src/database/storage.py`:

- Extend `BidInfo` with optional result-center fields listed in the tests.
- Add `_migrate_schema()` called from `_init_db()` after `CREATE TABLE IF NOT EXISTS`.
- Use `PRAGMA table_info(bids)` and `ALTER TABLE bids ADD COLUMN ...` for missing columns.
- Add JSON serialization helpers `_json_dumps(value)` and `_json_loads(value, default)`.
- Update `save()` to insert default statuses and return `cursor.lastrowid` for new rows, `False` for duplicates.
- Add `_row_to_bid(row)` used by `get_all`, `get_recent`, `get_unnotified`, `get_by_id`, and `query_results`.
- Add methods named in the Interfaces block.

Create `src/results/__init__.py`:

```python
"""Result center helpers for BidMonitor."""
```

Create `src/results/review.py` with:

```python
DEFAULT_NON_FOLLOW_REASON_TAGS = [
    "地域问题",
    "金额不合适",
    "项目类型不匹配",
    "资质不满足",
    "时间太紧",
    "信息不完整",
    "重复项目",
    "已过期",
    "其它",
]

FIT_STATUSES = {"pending", "fit", "not_fit"}
FOLLOW_DECISIONS = {"pending", "follow", "not_follow"}
URGENCIES = {"low", "medium", "high", "urgent"}
PROJECT_STAGES = {"lead", "screening", "following", "submitted", "ended"}


def validate_review_update(payload, reason_tags):
    allowed = {}
    if "fit_status" in payload:
        value = payload["fit_status"]
        if value not in FIT_STATUSES:
            raise ValueError("invalid fit_status")
        allowed["fit_status"] = value
    if "follow_decision" in payload:
        value = payload["follow_decision"]
        if value not in FOLLOW_DECISIONS:
            raise ValueError("invalid follow_decision")
        allowed["follow_decision"] = value
    if "urgency" in payload:
        value = payload["urgency"]
        if value not in URGENCIES:
            raise ValueError("invalid urgency")
        allowed["urgency"] = value
        allowed["urgency_source"] = "manual"
    if "project_stage" in payload:
        value = payload["project_stage"]
        if value not in PROJECT_STAGES:
            raise ValueError("invalid project_stage")
        allowed["project_stage"] = value
    if "non_follow_reasons" in payload:
        reasons = payload.get("non_follow_reasons") or []
        if not isinstance(reasons, list):
            raise ValueError("non_follow_reasons must be a list")
        unknown = [reason for reason in reasons if reason not in reason_tags]
        if unknown:
            raise ValueError("unknown non_follow_reasons")
        allowed["non_follow_reasons"] = reasons
    if "review_notes" in payload:
        allowed["review_notes"] = str(payload.get("review_notes") or "")

    final_decision = allowed.get("follow_decision", payload.get("follow_decision"))
    final_reasons = allowed.get("non_follow_reasons", payload.get("non_follow_reasons", []))
    if final_decision == "not_follow" and not final_reasons:
        raise ValueError("non_follow_reasons required when follow_decision is not_follow")
    return allowed


def _first_non_empty(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def resolve_result_data(bid):
    manual = getattr(bid, "manual_overrides", None) or {}
    ai = getattr(bid, "ai_extracted_data", None) or {}
    return {
        "id": getattr(bid, "id", None),
        "title": bid.title,
        "url": bid.url,
        "source": bid.source,
        "publish_date": bid.publish_date,
        "organization": _first_non_empty(manual.get("organization"), ai.get("organization"), bid.purchaser),
        "amount": _first_non_empty(manual.get("amount"), ai.get("amount"), getattr(bid, "amount", "")),
        "amount_unit": _first_non_empty(manual.get("amount_unit"), ai.get("amount_unit"), getattr(bid, "amount_unit", "")),
        "region": _first_non_empty(manual.get("region"), ai.get("region"), getattr(bid, "region", "")),
        "category": _first_non_empty(manual.get("category"), ai.get("category"), getattr(bid, "category", "")),
        "project_type": _first_non_empty(manual.get("project_type"), ai.get("project_type"), getattr(bid, "project_type", "")),
        "nature": _first_non_empty(manual.get("nature"), ai.get("nature"), getattr(bid, "nature", "")),
        "registration_deadline": _first_non_empty(manual.get("registration_deadline"), getattr(bid, "registration_deadline", "")),
        "submission_deadline": _first_non_empty(manual.get("submission_deadline"), getattr(bid, "submission_deadline", "")),
        "bid_opening_time": _first_non_empty(manual.get("bid_opening_time"), getattr(bid, "bid_opening_time", "")),
        "deadlines": _first_non_empty(manual.get("deadlines"), ai.get("deadlines"), []),
    }
```

- [ ] **Step 5: Run tests for Task 1**

Run: `python3 -m unittest tests.test_storage_results_center tests.test_result_review -v`

Expected: PASS.

- [ ] **Step 6: Run affected existing storage/server tests**

Run: `python3 -m unittest tests.test_server_config_defaults tests.test_url_list_crawler -v`

Expected: PASS, or failures only where later tasks intentionally change custom-sites/frontend contracts.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/database/storage.py src/results/__init__.py src/results/review.py tests/test_storage_results_center.py tests/test_result_review.py
git commit -m "feat: add results center storage fields"
```

---

### Task 2: Detail Fetch and AI Extraction Service

**Files:**
- Create: `src/results/detail_fetcher.py`
- Create: `src/results/ai_extractor.py`
- Modify: `src/monitor_core.py`
- Create: `tests/test_ai_extractor.py`
- Create: `tests/test_monitor_core_ai_extraction.py`

**Interfaces:**
- Consumes: `Storage.update_detail_fetch`, `Storage.update_ai_extraction` from Task 1.
- Produces: `fetch_detail_text(url: str, timeout: int = 30) -> tuple[bool, str, str | None]`
- Produces: `AIExtractor.extract(title: str, url: str, source: str, publish_date: str, summary: str, detail_text: str) -> dict`
- Produces: `build_column_updates(ai_data: dict) -> dict`
- Produces: `suggest_urgency(ai_data: dict, now: datetime | None = None) -> dict`
- Produces: `enrich_new_bid(storage: Storage, result_id: int, bid: BidInfo, ai_config: dict | None, log_callback: callable | None = None) -> None`

- [ ] **Step 1: Write failing AI extractor tests**

Create `tests/test_ai_extractor.py`:

```python
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from src.results.ai_extractor import AIExtractor, build_column_updates, suggest_urgency


class AIExtractorTests(unittest.TestCase):
    def test_responses_payload_and_parse_output_text_json(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "output_text": json.dumps({"organization": "上海某单位", "amount": "30", "deadlines": []}, ensure_ascii=False)
        }

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            data = AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")

        self.assertEqual(data["organization"], "上海某单位")
        url, kwargs = post.call_args
        self.assertEqual(url[0], "https://api.example.com/v1/responses")
        self.assertEqual(kwargs["json"]["model"], "grok-4.20-fast")
        self.assertIn("input", kwargs["json"])
        self.assertNotIn("messages", kwargs["json"])

    def test_chat_completions_payload_and_parse_message_json(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1/chat/completions",
            "api_key": "secret",
            "model": "deepseek-chat",
            "endpoint_type": "chat_completions",
        }
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "```json\n{\"region\":\"上海\",\"deadlines\":[]}\n```"}}]
        }

        with patch("src.results.ai_extractor.requests.post", return_value=response) as post:
            data = AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")

        self.assertEqual(data["region"], "上海")
        self.assertEqual(post.call_args[0][0], "https://api.example.com/v1/chat/completions")
        self.assertIn("messages", post.call_args.kwargs["json"])

    def test_build_column_updates_extracts_three_deadline_columns(self):
        data = {
            "amount": "50",
            "amount_unit": "万元",
            "region": "上海",
            "category": "弱电智能化",
            "project_type": "公开招标",
            "nature": "服务",
            "deadlines": [
                {"type": "registration_deadline", "end_at": "2026-07-03 17:00"},
                {"type": "submission_deadline", "end_at": "2026-07-05 10:00"},
                {"type": "bid_opening_time", "start_at": "2026-07-05 10:30"},
            ],
        }

        columns = build_column_updates(data)

        self.assertEqual(columns["registration_deadline"], "2026-07-03 17:00")
        self.assertEqual(columns["submission_deadline"], "2026-07-05 10:00")
        self.assertEqual(columns["bid_opening_time"], "2026-07-05 10:30")
        self.assertEqual(columns["deadline_source"], "ai")

    def test_suggest_urgency_uses_submission_deadline_first(self):
        data = {
            "deadlines": [
                {"type": "registration_deadline", "end_at": "2026-07-20 17:00"},
                {"type": "submission_deadline", "end_at": "2026-07-04 10:00"},
            ]
        }

        suggestion = suggest_urgency(data, now=datetime(2026, 7, 2, 9, 0))

        self.assertEqual(suggestion["urgency"], "urgent")
        self.assertEqual(suggestion["urgency_source"], "auto")
        self.assertEqual(suggestion["urgency_reference_type"], "submission")

    def test_invalid_json_raises_value_error(self):
        config = {"enable": True, "base_url": "https://api.example.com/v1", "api_key": "secret", "model": "grok", "endpoint_type": "responses"}
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"output_text": "not json"}

        with patch("src.results.ai_extractor.requests.post", return_value=response):
            with self.assertRaises(ValueError):
                AIExtractor(config).extract("标题", "https://e.test", "源", "2026-07-01", "摘要", "详情")
```

- [ ] **Step 2: Write failing monitor integration test**

Create `tests/test_monitor_core_ai_extraction.py`:

```python
import unittest
from unittest.mock import Mock, patch

from src.database.storage import BidInfo, Storage
from src.monitor_core import MonitorCore


class FakeCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "源", "弱电智能化")]


class MonitorCoreAIExtractionTests(unittest.TestCase):
    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_new_saved_bid_triggers_enrichment(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage

        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={"enabled_sites": []},
            ai_config={"enable": False},
        )
        monitor.crawlers = [FakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            result = monitor.run_once()

        self.assertEqual(result["new_count"], 1)
        enrich.assert_called_once()
        self.assertEqual(enrich.call_args.args[1], 123)
```

- [ ] **Step 3: Run the new tests and confirm they fail**

Run: `python3 -m unittest tests.test_ai_extractor tests.test_monitor_core_ai_extraction -v`

Expected: FAIL because modules and `enrich_new_bid` call do not exist.

- [ ] **Step 4: Implement detail fetcher**

Create `src/results/detail_fetcher.py`:

```python
import re

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


def clean_html_to_text(html):
    if not html:
        return ""
    if BeautifulSoup is None:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_detail_text(url, timeout=30):
    if requests is None:
        return False, "", "requests is not installed"
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 BidMonitor/1.0"},
            verify=False,
        )
        if response.status_code >= 400:
            return False, "", f"HTTP {response.status_code}"
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return True, clean_html_to_text(response.text), None
    except Exception as exc:
        return False, "", str(exc)[:200]
```

- [ ] **Step 5: Implement AI extractor**

Create `src/results/ai_extractor.py` with:

- `AIExtractor._endpoint_url()` that appends `/responses` for `endpoint_type=responses` when `base_url` ends in `/v1`, and uses `base_url` directly for full paths.
- `AIExtractor._build_prompt(...)` requiring strict JSON and deadline types from the spec.
- `AIExtractor.extract(...)` using `requests.post` with `Authorization: Bearer ...`, timeout 120, and parsing `output_text` for responses or `choices[0].message.content` for chat completions.
- `_parse_json_text(text)` that accepts fenced JSON and raises `ValueError` on invalid JSON.
- `build_column_updates(ai_data)` syncing amount, unit, region, category, project_type, nature, three deadline columns, `deadline_source=ai`, and `ai_recommendation`.
- `suggest_urgency(ai_data, now=None)` with thresholds: <=3 days urgent, <=7 high, <=14 medium, else low. It returns `urgency`, `urgency_source=auto`, `urgency_reference_time`, and `urgency_reference_type`.
- `enrich_new_bid(storage, result_id, bid, ai_config, log_callback=None)` that fetches detail, updates detail status, exits with detail failure if needed, skips AI if disabled/missing key with `ai_extract_status=pending`, otherwise extracts and updates storage. It must catch AI errors and store `extract_failed`.

- [ ] **Step 6: Wire MonitorCore to enrichment**

Modify `src/monitor_core.py`:

- Import `enrich_new_bid` with a fallback import compatible with existing relative/import style.
- After `result_id = self.storage.save(bid, notified=False)`, append only if `result_id` is truthy.
- Call `enrich_new_bid(self.storage, result_id, bid, self.ai_config_for_extraction, log_callback=self.log)` or store the original `ai_config` on `self` during `__init__`.
- Do not block result visibility if enrichment fails; `enrich_new_bid` owns failure statuses.

- [ ] **Step 7: Run Task 2 tests**

Run: `python3 -m unittest tests.test_ai_extractor tests.test_monitor_core_ai_extraction -v`

Expected: PASS.

- [ ] **Step 8: Run MonitorCore regression tests**

Run: `python3 -m unittest tests.test_monitor_core_browser_mode tests.test_monitor_core_url_sources -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/results/detail_fetcher.py src/results/ai_extractor.py src/monitor_core.py tests/test_ai_extractor.py tests/test_monitor_core_ai_extraction.py
git commit -m "feat: add AI extraction for new results"
```

---

### Task 3: Results API, Settings API, and Config Defaults

**Files:**
- Modify: `server/app.py`
- Modify: `tests/test_server_config_defaults.py`
- Create: `tests/test_server_results_api.py`

**Interfaces:**
- Consumes: `Storage.query_results`, `Storage.get_by_id`, `Storage.update_review`, `Storage.update_manual_overrides`, `validate_review_update`, `resolve_result_data`, `DEFAULT_NON_FOLLOW_REASON_TAGS`.
- Produces: `GET /api/results` table response with `items`, `total`, `offset`, `limit`.
- Produces: `GET /api/results/{result_id}` detail response.
- Produces: `PATCH /api/results/{result_id}/review`.
- Produces: `PATCH /api/results/bulk-review`.
- Produces: `PATCH /api/results/{result_id}/fields`.
- Produces: `GET /api/result-settings`.
- Produces: `POST /api/result-settings/reasons`.

- [ ] **Step 1: Write failing API tests**

Create `tests/test_server_results_api.py`:

```python
import asyncio
import unittest
from unittest.mock import Mock, patch

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
SRC_DIR = os.path.join(ROOT_DIR, "src")
for path in [SERVER_DIR, SRC_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

import app
from database.storage import BidInfo


class ServerResultsApiTests(unittest.TestCase):
    def setUp(self):
        self.storage = Mock()
        app.app_state.storage = self.storage
        app.app_state.config = {"non_follow_reason_tags": ["地域问题", "其它"], "ai_config": {"api_key": "secret"}}

    def make_bid(self):
        bid = BidInfo("项目A", "https://example.com/a", "2026-07-01", "源", purchaser="采购人")
        bid.id = 7
        bid.fit_status = "pending"
        bid.follow_decision = "pending"
        bid.urgency = "medium"
        bid.urgency_source = "auto"
        bid.project_stage = "lead"
        bid.region = "上海"
        bid.category = "弱电智能化"
        bid.amount = "50"
        bid.amount_unit = "万元"
        bid.registration_deadline = "2026-07-03 17:00"
        bid.submission_deadline = "2026-07-05 10:00"
        bid.bid_opening_time = "2026-07-05 10:30"
        bid.ai_extract_status = "extracted"
        bid.detail_fetch_status = "success"
        bid.ai_extracted_data = {"organization": "AI单位", "deadlines": []}
        bid.manual_overrides = {"organization": "人工单位"}
        bid.non_follow_reasons = []
        bid.review_notes = ""
        return bid

    def test_get_results_returns_table_fields_and_filters(self):
        bid = self.make_bid()
        self.storage.query_results.return_value = ([bid], 1)

        result = asyncio.run(app.get_results(limit=20, offset=0, fit_status="pending", user={"role": "user"}))

        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["id"], 7)
        self.assertEqual(item["organization"], "人工单位")
        self.assertEqual(item["registration_deadline"], "2026-07-03 17:00")
        self.assertEqual(item["submission_deadline"], "2026-07-05 10:00")
        self.assertEqual(item["bid_opening_time"], "2026-07-05 10:30")
        self.storage.query_results.assert_called_once()
        self.assertEqual(self.storage.query_results.call_args.args[0]["fit_status"], "pending")

    def test_get_result_detail_returns_ai_manual_and_resolved_data(self):
        bid = self.make_bid()
        self.storage.get_by_id.return_value = bid

        result = asyncio.run(app.get_result_detail(7, user={"role": "user"}))

        self.assertEqual(result["id"], 7)
        self.assertEqual(result["resolved"]["organization"], "人工单位")
        self.assertEqual(result["ai_extracted_data"]["organization"], "AI单位")
        self.assertEqual(result["manual_overrides"]["organization"], "人工单位")

    def test_update_review_validates_not_follow_reason(self):
        self.storage.get_by_id.return_value = self.make_bid()

        with self.assertRaises(app.HTTPException) as ctx:
            asyncio.run(app.update_result_review(7, {"follow_decision": "not_follow", "non_follow_reasons": []}, user={"role": "user"}))

        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_review_saves_valid_payload(self):
        self.storage.get_by_id.return_value = self.make_bid()

        result = asyncio.run(
            app.update_result_review(
                7,
                {"follow_decision": "not_follow", "non_follow_reasons": ["地域问题"], "urgency": "urgent"},
                user={"role": "user"},
            )
        )

        self.assertTrue(result["success"])
        self.storage.update_review.assert_called_once()
        self.assertEqual(self.storage.update_review.call_args.args[0], [7])
        self.assertEqual(self.storage.update_review.call_args.args[1]["urgency_source"], "manual")

    def test_bulk_review_rejects_invalid_batch_atomically(self):
        with self.assertRaises(app.HTTPException):
            asyncio.run(app.bulk_update_result_review({"ids": [1, 2], "update": {"project_stage": "bad"}}, user={"role": "user"}))
        self.storage.update_review.assert_not_called()

    def test_update_manual_fields_saves_overrides(self):
        result = asyncio.run(app.update_result_fields(7, {"organization": "修正单位", "amount": "80"}, user={"role": "user"}))

        self.assertTrue(result["success"])
        self.storage.update_manual_overrides.assert_called_once_with(7, {"organization": "修正单位", "amount": "80"})

    def test_result_settings_masks_defaults_and_updates_reasons_for_admin(self):
        settings = asyncio.run(app.get_result_settings(user={"role": "user"}))
        self.assertEqual(settings["non_follow_reason_tags"], ["地域问题", "其它"])
        self.assertIn("urgent", settings["urgencies"])

        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.update_non_follow_reasons({"tags": ["地域问题", "金额不合适"]}, user={"role": "admin"}))

        self.assertTrue(result["success"])
        self.assertEqual(app.app_state.config["non_follow_reason_tags"], ["地域问题", "金额不合适"])
        save_config.assert_called_once_with(app.app_state.config)
```

- [ ] **Step 2: Update config/default tests for AI endpoint type, reason tags, and custom-sites removal**

In `tests/test_server_config_defaults.py`, add assertions to `test_default_config_targets_shanghai_url_list_first`:

```python
self.assertIn("non_follow_reason_tags", config)
self.assertIn("地域问题", config["non_follow_reason_tags"])
self.assertEqual(config["ai_config"]["endpoint_type"], "responses")
self.assertNotIn("custom_sites", config)
```

Add a test:

```python
def test_get_config_masks_ai_key(self):
    app.app_state.config = app.normalize_config({
        "ai_config": {
            "api_key": "secret",
            "base_url": "https://api.example.com/v1",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }
    })
    config = asyncio.run(app.get_config(user={"role": "user"}))

    self.assertEqual(config["ai_config"]["api_key"], "***")
```

- [ ] **Step 3: Run API tests and confirm they fail**

Run: `python3 -m unittest tests.test_server_results_api tests.test_server_config_defaults -v`

Expected: FAIL because routes, config defaults, and masking are not implemented.

- [ ] **Step 4: Implement config defaults and masking**

Modify `server/app.py`:

- Import review helpers:

```python
from results.review import DEFAULT_NON_FOLLOW_REASON_TAGS, FIT_STATUSES, FOLLOW_DECISIONS, PROJECT_STAGES, URGENCIES, resolve_result_data, validate_review_update
```

- Add `non_follow_reason_tags` to `default_config`.
- Add `endpoint_type: "responses"` to `ai_config`.
- Remove `custom_sites` from `default_config`.
- Stop passing `custom_sites` to `MonitorCore` in `crawler_overrides`.
- In `normalize_config`, backfill `non_follow_reason_tags` and `ai_config.endpoint_type`, and remove `custom_sites` if present.
- In `get_config`, deep-copy config and mask `ai_config.api_key` as `"***"` when present.
- In `update_full_config`, preserve existing `ai_config.api_key` if incoming value is empty or `"***"`.

- [ ] **Step 5: Implement result serialization and API routes**

In `server/app.py`, add helpers:

```python
def result_summary(bid):
    resolved = resolve_result_data(bid)
    return {
        "id": bid.id,
        "title": bid.title,
        "url": bid.url,
        "source": bid.source,
        "pub_date": bid.publish_date or None,
        "fit_status": bid.fit_status,
        "follow_decision": bid.follow_decision,
        "urgency": bid.urgency,
        "project_stage": bid.project_stage,
        "organization": resolved.get("organization"),
        "amount": resolved.get("amount"),
        "amount_unit": resolved.get("amount_unit"),
        "region": resolved.get("region"),
        "category": resolved.get("category"),
        "registration_deadline": resolved.get("registration_deadline"),
        "submission_deadline": resolved.get("submission_deadline"),
        "bid_opening_time": resolved.get("bid_opening_time"),
        "ai_extract_status": bid.ai_extract_status,
        "detail_fetch_status": bid.detail_fetch_status,
        "non_follow_reasons": bid.non_follow_reasons,
        "review_notes": bid.review_notes,
    }
```

Replace `get_results` signature with explicit optional filters:

```python
async def get_results(
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    fit_status: Optional[str] = None,
    follow_decision: Optional[str] = None,
    urgency: Optional[str] = None,
    project_stage: Optional[str] = None,
    ai_extract_status: Optional[str] = None,
    source: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
```

Build filters dict from non-empty values, call `app_state.storage.query_results(filters, limit, offset)`, return summaries.

Add routes:

- `@app.get("/api/results/{result_id}") async def get_result_detail(...)`
- `@app.patch("/api/results/{result_id}/review") async def update_result_review(result_id: int, payload: Dict[str, Any], ...)`
- `@app.patch("/api/results/bulk-review") async def bulk_update_result_review(payload: Dict[str, Any], ...)`
- `@app.patch("/api/results/{result_id}/fields") async def update_result_fields(result_id: int, payload: Dict[str, Any], ...)`
- `@app.get("/api/result-settings") async def get_result_settings(...)`
- `@app.post("/api/result-settings/reasons") async def update_non_follow_reasons(payload: Dict[str, Any], user=Depends(require_admin))`

Use `HTTPException(status_code=400, detail=str(exc))` for validation errors.

- [ ] **Step 6: Remove custom-sites API routes**

Delete `get_custom_sites` and `update_custom_sites` route functions from `server/app.py`.

- [ ] **Step 7: Update `/api/test/ai` for endpoint type**

Modify `test_ai` to use `AIExtractor` with `endpoint_type`, a short prompt, and return success when extraction client can call the configured endpoint. Preserve secret masking and never log the API key.

- [ ] **Step 8: Run Task 3 tests**

Run: `python3 -m unittest tests.test_server_results_api tests.test_server_config_defaults -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```bash
git add server/app.py tests/test_server_results_api.py tests/test_server_config_defaults.py
git commit -m "feat: add results center API"
```

---

### Task 4: Results Center Frontend Table, Detail Panel, and Bulk Edit

**Files:**
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`
- Modify: `server/static/styles.css`
- Modify: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes: `GET /api/results`
- Consumes: `GET /api/results/{id}`
- Consumes: `PATCH /api/results/{id}/review`
- Consumes: `PATCH /api/results/bulk-review`
- Consumes: `PATCH /api/results/{id}/fields`
- Consumes: `GET /api/result-settings`
- Produces: DOM hooks `resultsTableBody`, `resultDetailPanel`, `bulkReviewModal`, `resultFilterBar`.

- [ ] **Step 1: Update static frontend tests first**

Modify `tests/test_static_frontend_assets.py`:

- In `test_behavioral_dom_contract_is_preserved`, remove required IDs: `contactsList`, `contactModal`, `customSitesList`, `customSiteModal`.
- Add required IDs:

```python
"resultFilterBar",
"resultsTableBody",
"resultDetailPanel",
"bulkReviewModal",
"bulkFitStatus",
"bulkFollowDecision",
"bulkUrgency",
"bulkProjectStage",
"bulkNonFollowReasons",
"aiEndpointType",
```

- In `test_app_js_keeps_spa_behavior_without_global_event_dependency`, remove `self.assertIn("loadContacts()", js)`.
- Add a test:

```python
def test_results_center_table_contract(self):
    html = self.read("index.html")
    js = self.read("app.js")
    css = self.read("styles.css")

    for header in ["项目名称", "适合性", "跟进决策", "紧急度", "项目阶段", "单位", "金额", "地区", "分类", "报名/文件截止", "投标截止", "开标时间", "AI状态", "来源"]:
        self.assertIn(header, html)
    for hook in ["resultsTableBody", "resultDetailPanel", "bulkReviewModal", "resultFilterBar"]:
        self.assertIn(f'id="{hook}"', html)
    for fn in ["loadResultSettings", "loadResults", "renderResultsTable", "openResultDetail", "saveResultReview", "openBulkReview", "saveBulkReview"]:
        self.assertIn(f"function {fn}", js)
    for endpoint in ["/api/result-settings", "/api/results/bulk-review", "/api/results/"]:
        self.assertIn(endpoint, js)
    for selector in [".results-table", ".result-detail-panel", ".bulk-review-grid", ".result-filter-bar"]:
        self.assertIn(selector, css)
```

- Add a test:

```python
def test_removed_colleague_entry_points_are_not_visible(self):
    html = self.read("index.html")
    js = self.read("app.js")

    self.assertNotIn('data-page="contacts"', html)
    self.assertNotIn('id="page-contacts"', html)
    self.assertNotIn('id="contactModal"', html)
    self.assertNotIn('id="customSiteModal"', html)
    self.assertNotIn("showAddCustomSite", js)
    self.assertNotIn("/api/custom-sites", js)
    self.assertNotIn("loadContacts()", js)
    self.assertNotIn("showSmsConfig()", html)
    self.assertNotIn("showVoiceConfig()", html)
```

- [ ] **Step 2: Run static tests and confirm failure**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: FAIL because results table/detail/bulk hooks do not exist and old contact/custom-site hooks still exist.

- [ ] **Step 3: Replace results page markup**

Modify `server/static/index.html`:

- Replace the current `page-results` card body with:
  - `div id="resultFilterBar" class="result-filter-bar"` containing search input, filters, refresh button, bulk edit button.
  - `.results-table-wrap` with `<table class="results-table">`.
  - `<tbody id="resultsTableBody">`.
  - `<aside id="resultDetailPanel" class="result-detail-panel">`.
  - `<div id="bulkReviewModal" class="modal">` containing controls for `bulkFitStatus`, `bulkFollowDecision`, `bulkUrgency`, `bulkProjectStage`, `bulkNonFollowReasons`, and notes.
- Add `select id="aiEndpointType"` in the AI modal with options `responses` and `chat_completions`.

- [ ] **Step 4: Implement frontend results state and rendering**

Modify `server/static/app.js`:

- Add globals:

```javascript
let currentResults = [], resultSettings = null, selectedResultIds = new Set(), activeResultId = null;
```

- Add `loadResultSettings()` that fetches `/api/result-settings`.
- Update `showPage('results')` to call `loadResultSettings()` then `loadResults()`.
- Replace current `loadResults()` card rendering with API query construction, table rendering, and selection preservation.
- Add `renderResultsTable(data)` using the default columns and three deadline columns.
- Add `renderStatusLabel(value, map)` helpers for Chinese labels.
- Add `openResultDetail(id)`, `renderResultDetail(detail)`, `saveResultReview(id)`, `saveResultFields(id)`.
- Add `openBulkReview()`, `renderReasonCheckboxes(containerId, selected)`, `saveBulkReview()`.
- Ensure `not_follow` with no reason is blocked client-side before sending.

- [ ] **Step 5: Update AI config frontend**

Modify `showAiConfig()` and `saveAiConfig()` in `server/static/app.js`:

- Populate `aiEndpointType` from `currentConfig.ai_config.endpoint_type || "responses"`.
- Save `endpoint_type` into `currentConfig.ai_config`.
- Keep `api_key` empty meaning preserve existing secret.

- [ ] **Step 6: Add CSS for dense table and side panel**

Modify `server/static/styles.css`:

- Add `.result-filter-bar`, `.results-table-wrap`, `.results-table`, `.result-checkbox`, `.status-select`, `.result-detail-panel`, `.result-detail-panel.active`, `.detail-grid`, `.bulk-review-grid`, `.reason-list`.
- Keep no `box-shadow`, no gradients, no negative letter spacing.
- Use compact controls and stable table dimensions.
- Add responsive behavior: horizontal table scroll and full-screen side panel on narrow screens.

- [ ] **Step 7: Run frontend static tests**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: PASS after Task 5 also removes old entry points, or FAIL only for removal tests until Task 5 lands. Coordinate with Task 5 owner before committing if both modify the same frontend files.

- [ ] **Step 8: Commit Task 4**

```bash
git add server/static/index.html server/static/app.js server/static/styles.css tests/test_static_frontend_assets.py
git commit -m "feat: add results center frontend"
```

---

### Task 5: Remove Custom URL UI/API/Config and Hide Contacts/Notifications

**Files:**
- Modify: `server/app.py`
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`
- Modify: `server/static/styles.css`
- Modify: `src/monitor_core.py`
- Modify: `tests/test_static_frontend_assets.py`
- Modify: `tests/test_server_config_defaults.py`

**Interfaces:**
- Consumes: Existing site metadata page.
- Produces: No colleague-visible custom URL/contact/notification entry points.
- Produces: No `/api/custom-sites` routes.
- Produces: `MonitorCore` no longer reads `custom_sites` overrides in this Web stage.

- [ ] **Step 1: Update tests for removed custom URL and hidden contact/notification UI**

If Task 4 has not already updated `tests/test_static_frontend_assets.py`, apply the removal assertions from Task 4 Step 1.

Modify `tests/test_server_config_defaults.py`:

```python
def test_custom_sites_removed_from_default_config_and_routes(self):
    with patch.object(app.os.path, "exists", return_value=False):
        config = app.load_config()

    self.assertNotIn("custom_sites", config)
    route_paths = {path for (_method, path) in getattr(app.app, "routes", {}).keys()} if isinstance(getattr(app.app, "routes", None), dict) else set()
    self.assertNotIn("/api/custom-sites", route_paths)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python3 -m unittest tests.test_static_frontend_assets tests.test_server_config_defaults -v`

Expected: FAIL while old custom-site/contact/notification UI and API still exist.

- [ ] **Step 3: Remove custom-sites backend and config**

Modify `server/app.py`:

- Remove `custom_sites` from `default_config`.
- In `normalize_config`, `config.pop("custom_sites", None)`.
- Remove `get_custom_sites` and `update_custom_sites` route functions.
- Stop passing `custom_sites` in `crawler_overrides`.

Modify `src/monitor_core.py`:

- Remove or ignore `custom_sites` loading block for Web config. If desktop GUI still needs custom sites, guard with a config flag:

```python
if self.config.get("enable_custom_sites", False):
    custom_sites = self.config.get("custom_sites", [])
else:
    custom_sites = []
```

- [ ] **Step 4: Remove contact/custom URL frontend entry points**

Modify `server/static/index.html`:

- Remove `page-contacts`.
- Remove contacts nav button.
- Remove `contactModal`.
- Remove `customSiteModal`.
- Remove custom-site entry button and list container.
- Remove notification config rows for SMS and voice. Keep AI config row.
- Remove hint text that says email/wechat tokens are configured in contacts.

Modify `server/static/app.js`:

- Remove `currentContacts`, `editingContactIndex`, `currentCustomSites`.
- Remove `loadContacts`, `renderContacts`, `showAddContact`, `editContact`, `closeContactModal`, `saveContact`, `deleteContact`, `testContactNotify` if present.
- Remove `loadCustomSites`, `renderCustomSites`, `showAddCustomSite`, `saveCustomSite`, `deleteCustomSite`.
- Remove `if (name === 'contacts') loadContacts();`.
- Remove calls to `/api/custom-sites`.
- Leave SMS/voice functions only if no UI calls them; better remove Web functions if tests allow.

- [ ] **Step 5: Run removal tests**

Run: `python3 -m unittest tests.test_static_frontend_assets tests.test_server_config_defaults -v`

Expected: PASS, or failures only from Task 4 if results table hooks are not merged yet.

- [ ] **Step 6: Commit Task 5**

```bash
git add server/app.py server/static/index.html server/static/app.js server/static/styles.css src/monitor_core.py tests/test_static_frontend_assets.py tests/test_server_config_defaults.py
git commit -m "feat: remove colleague URL and contact entry points"
```

---

### Task 6: Integration, Conflict Resolution, and Verification

**Files:**
- Read/modify only files touched by Tasks 1-5 if integration reveals mismatches.
- Update plan checkboxes as tasks complete.

**Interfaces:**
- Consumes: All tasks above.
- Produces: A coherent first-stage results center implementation with passing targeted tests.

- [ ] **Step 1: Inspect staged and unstaged changes**

Run: `git status --short`

Expected: dirty tree may include pre-existing unrelated files. Confirm task changes are limited to planned files before staging.

- [ ] **Step 2: Resolve frontend/API naming mismatches**

Check these exact contracts:

- `GET /api/result-settings` exists and `app.js` calls `/api/result-settings`.
- Bulk endpoint is exactly `/api/results/bulk-review`.
- Detail endpoint is exactly `/api/results/${id}`.
- Field override endpoint is exactly `/api/results/${id}/fields`.
- Review endpoint is exactly `/api/results/${id}/review`.
- Frontend table IDs match tests: `resultsTableBody`, `resultDetailPanel`, `bulkReviewModal`, `resultFilterBar`.

- [ ] **Step 3: Run targeted backend tests**

Run:

```bash
python3 -m unittest \
  tests.test_storage_results_center \
  tests.test_result_review \
  tests.test_ai_extractor \
  tests.test_server_results_api \
  tests.test_server_config_defaults \
  tests.test_monitor_core_ai_extraction \
  -v
```

Expected: PASS.

- [ ] **Step 4: Run targeted crawler/monitor regression tests**

Run:

```bash
python3 -m unittest \
  tests.test_url_list_crawler \
  tests.test_monitor_core_browser_mode \
  tests.test_monitor_core_url_sources \
  -v
```

Expected: PASS.

- [ ] **Step 5: Run frontend static tests**

Run: `python3 -m unittest tests.test_static_frontend_assets -v`

Expected: PASS.

- [ ] **Step 6: Smoke import server app**

Run: `python3 -m unittest tests.test_server_auth -v`

Expected: PASS. This catches route/import breakage in the FastAPI fallback test harness.

- [ ] **Step 7: Manual API smoke with in-memory calls**

Run a short Python command from repo root:

```bash
python3 - <<'PY'
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.abspath("server"))
sys.path.insert(0, os.path.abspath("src"))
import app
from database.storage import Storage, BidInfo

tmp = tempfile.TemporaryDirectory()
app.app_state.storage = Storage(os.path.join(tmp.name, "bids.db"))
result_id = app.app_state.storage.save(BidInfo("上海智能化公开招标", "https://example.com/a", "2026-07-01", "测试源", "弱电智能化"))
app.app_state.config["non_follow_reason_tags"] = ["地域问题", "其它"]
print(asyncio.run(app.get_results(user={"role": "user"}))["total"])
print(asyncio.run(app.update_result_review(result_id, {"follow_decision": "not_follow", "non_follow_reasons": ["地域问题"]}, user={"role": "user"}))["success"])
tmp.cleanup()
PY
```

Expected output contains:

```text
1
True
```

- [ ] **Step 8: Final diff review**

Run: `git diff --stat` and inspect diffs for files listed in the File Structure section.

Expected: no unrelated file rewrites, no plaintext API key, no accidental removal of auth/user management.

- [ ] **Step 9: Commit integration fixes**

If Task 6 made changes:

```bash
git add docs/superpowers/plans/2026-07-02-results-center-ai-extraction.md
git commit -m "fix: integrate results center workflow"
```

Replace the `git add` path above with the exact planned files changed during integration, such as `server/app.py` or `server/static/app.js`. If no changes were needed, do not create an empty commit.

---

## Self-Review Notes

Spec coverage:

- Result table and side panel: Task 4.
- Detail fetch and automatic AI extraction: Task 2.
- AI original plus manual corrections: Tasks 1, 3, 4.
- Review workflow and full bulk editing: Tasks 1, 3, 4.
- Three deadline columns plus full deadline JSON: Tasks 1, 2, 4.
- Configurable non-follow reasons: Tasks 1, 3, 4.
- Responses and chat completions endpoint support: Tasks 2, 3, 4.
- Custom URL removal: Tasks 3, 5.
- Contact/notification Web hiding while keeping modules: Task 5.
- Verification: Task 6.

Parallelization:

- Task 1 is the contract gate.
- Tasks 2 and 3 can run in parallel after Task 1 if Task 3 uses the interfaces exactly.
- Tasks 4 and 5 both touch frontend files, so dispatch them together only if each subagent is told to coordinate through tests and preserve the other's hooks. If minimizing merge risk is more important than speed, run Task 5 first, then Task 4.
- Task 6 must run after all task branches return.
