# Keyword Library Opportunity Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mixed keyword text configuration and AI filtering semantics with a structured keyword library and AI opportunity evaluation workflow across Web, desktop GUI, storage, APIs, and monitor flow.

**Architecture:** Add focused domain modules for keyword-library normalization and opportunity evaluation, then wire those contracts into FastAPI config/results APIs, SQLite storage, monitor enrichment, Web UI, and Tkinter GUI. AI evaluation updates stored rows after insertion and never blocks storage. Parallel implementation is allowed only where file ownership does not overlap.

**Tech Stack:** Python 3, FastAPI-compatible route functions, SQLite, unittest/pytest, static HTML/CSS/JavaScript, Tkinter.

## Global Constraints

- Every crawled notice that the crawler emits as a valid bid result is saved before AI evaluation.
- AI cannot be an insertion gate.
- Keyword library entries support search, match evidence, UI management, and AI business context; they do not directly determine final opportunity score.
- Final score is produced by AI from title, summary/content, detail text, procurement stage, region, owner, amount, deadlines, and project content.
- `KeywordMatcher` remains a lightweight matching/evidence helper only. No complex scoring logic goes into it.
- Human users can correct AI suggestion, manual priority, business direction, region, stage, amount band, owner type, follow decision, and notes.
- Default result sorting is manual priority first, AI score second, then publish or insertion time.
- `keyword_library` is the primary configuration shape shared by Web, desktop GUI, monitor core, and AI opportunity evaluation.
- Legacy `keywords`, `exclude`, and `must_contain` are migration inputs and compatibility-derived fields, not the primary UI model.
- Web and desktop GUI must not leave a plain comma-separated keyword entry as the only keyword-management path.
- Export is implemented in the browser using the `GET /api/keyword-library` response converted to TSV. No server export endpoint is required in the first implementation.
- Do not dispatch multiple implementation agents to edit the same file concurrently.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-07-04-keyword-library-opportunity-evaluation-design.md`
- Existing Web app: `server/app.py`, `server/static/index.html`, `server/static/app.js`, `server/static/styles.css`
- Existing monitor flow: `src/monitor_core.py`
- Existing storage: `src/database/storage.py`
- Existing AI field extraction: `src/results/ai_extractor.py`
- Existing review helpers: `src/results/review.py`
- Existing desktop GUI: `src/gui.py`

## Parallel Execution Map

**Phase 0: branch and baseline, serial**

- Task 0.

**Phase 1: shared contracts, serial**

- Task 1: keyword-library module.
- Task 2: storage migration and opportunity persistence.
- Task 3: opportunity evaluator module.

These tasks define interfaces used by every later task.

**Phase 2: feature surfaces, parallel-safe after Phase 1 with file locks**

- Task 4 can run alone for `server/app.py` keyword-library APIs.
- Task 5 can run after Task 4 or after the Task 4 API contract is accepted; it owns all Web static files.
- Task 6 can run alone for `server/app.py` result APIs after Task 2.
- Task 7 can run after Tasks 1-3; it owns monitor/enrichment files.
- Task 8 can run after Task 1; it owns `src/gui.py`.

Task 4 and Task 6 both edit `server/app.py`; do not run them in parallel. Task 5 and Task 8 may run in parallel with Task 6 because their files do not overlap. Task 7 may run in parallel with Task 5 and Task 8 after Tasks 1-3.

**Phase 3: integration, serial**

- Task 9: final cross-surface cleanup and full regression.

## File Ownership Matrix

| File | Owner Task | Parallel Rule |
| --- | --- | --- |
| `src/results/keyword_library.py` | Task 1 | Shared interface after Task 1; later edits require coordinator approval |
| `tests/test_keyword_library.py` | Task 1 | Same as Task 1 |
| `src/database/storage.py` | Task 2 | Exclusive lock |
| `tests/test_storage_results_center.py` | Task 2 | Exclusive with storage task |
| `src/results/opportunity_evaluator.py` | Task 3 | Shared interface after Task 3 |
| `tests/test_opportunity_evaluator.py` | Task 3 | Same as Task 3 |
| `server/app.py` | Tasks 4 and 6 | Exclusive lock; run Task 4 before Task 6 |
| `tests/test_server_config_defaults.py` | Task 4 | Can be edited with Task 4 only |
| `tests/test_server_keyword_library_api.py` | Task 4 | Can be edited with Task 4 only |
| `tests/test_server_results_api.py` | Task 6 | Can be edited with Task 6 only |
| `server/static/index.html` | Task 5 | Exclusive Web static lock |
| `server/static/app.js` | Task 5 | Exclusive Web static lock |
| `server/static/styles.css` | Task 5 | Exclusive Web static lock |
| `tests/test_static_frontend_assets.py` | Task 5 | Exclusive Web static lock |
| `src/results/ai_extractor.py` | Task 7 | Exclusive enrichment lock |
| `src/monitor_core.py` | Task 7 | Exclusive monitor lock |
| `tests/test_ai_extractor.py` | Task 7 | Exclusive enrichment lock |
| `tests/test_monitor_core_ai_extraction.py` | Task 7 | Exclusive monitor lock |
| `src/gui.py` | Task 8 | Exclusive GUI lock |
| `tests/test_gui_keyword_library.py` | Task 8 | Exclusive GUI lock |
| `README.md` | Task 9 | Serial final cleanup only |

## Task 0: Branch, Baseline, and Execution Ledger

**Parallel safety:** Serial preflight. No implementation agent should start before this completes.

**Files:**
- Create: `.superpowers/sdd/progress.md`
- No production code changes.

**Interfaces:**
- Consumes: current repository state.
- Produces: clean baseline and a durable progress ledger for subagent-driven execution.

- [ ] **Step 1: Verify isolation and status**

Run:

```bash
git status --short
git branch --show-current
git rev-parse --git-dir
git rev-parse --git-common-dir
```

Expected: clean worktree. If not already in an isolated worktree, use `superpowers:using-git-worktrees` before implementation execution.

- [ ] **Step 2: Run baseline tests**

Run:

```bash
PYTHONPATH=. pytest -q
```

Expected: current suite passes before feature work. If it fails, record failures and stop for triage.

- [ ] **Step 3: Create execution ledger**

Create `.superpowers/sdd/progress.md` with:

```markdown
# Keyword Library Opportunity Evaluation Progress

Plan: docs/superpowers/plans/2026-07-04-keyword-library-opportunity-evaluation.md
Spec: docs/superpowers/specs/2026-07-04-keyword-library-opportunity-evaluation-design.md

## Completed Tasks
```

- [ ] **Step 4: Commit only if the ledger is tracked by local workflow**

The ledger is normally scratch state. Do not commit it unless the repository already tracks `.superpowers/sdd`.

## Task 1: Keyword Library Domain Module

**Parallel safety:** Phase 1 serial. This task must finish before Tasks 4, 5, 7, and 8.

**Files:**
- Create: `src/results/keyword_library.py`
- Create: `tests/test_keyword_library.py`

**Interfaces:**
- Produces:
  - `MATCH_SCOPES: set[str]`
  - `DEFAULT_KEYWORD_LIBRARY: list[dict]`
  - `normalize_keyword_library(value: object | None, legacy_keywords: str = "") -> list[dict]`
  - `derive_legacy_keywords(library: list[dict]) -> str`
  - `derive_search_keywords(library: list[dict], limit: int = 8) -> list[str]`
  - `parse_keyword_library_text(text: str) -> dict`
  - `merge_keyword_library(existing: list[dict], imported: list[dict]) -> list[dict]`
  - `keyword_library_directions(library: list[dict]) -> list[str]`
  - `match_keyword_evidence(title: str, content: str, detail_text: str, library: list[dict]) -> dict`
- Consumes: no new project interfaces.

- [ ] **Step 1: Write failing keyword-library tests**

Create `tests/test_keyword_library.py`:

```python
import unittest

from src.results.keyword_library import (
    DEFAULT_KEYWORD_LIBRARY,
    derive_legacy_keywords,
    derive_search_keywords,
    keyword_library_directions,
    match_keyword_evidence,
    merge_keyword_library,
    normalize_keyword_library,
    parse_keyword_library_text,
)


class KeywordLibraryTests(unittest.TestCase):
    def test_defaults_include_all_business_directions_and_required_terms(self):
        directions = keyword_library_directions(DEFAULT_KEYWORD_LIBRARY)
        for direction in [
            "音视频会议",
            "显示大屏与指挥中心",
            "AI 视频与智能分析",
            "基础弱电 / 智能化工程",
            "安防监控",
            "门禁一卡通",
            "综合布线 / 网络 / 机房",
            "可做杂项",
        ]:
            self.assertIn(direction, directions)
        serialized = "\n".join(
            f"{row['business_direction']} {row['keyword']} {' '.join(row.get('synonyms') or [])}"
            for row in DEFAULT_KEYWORD_LIBRARY
        )
        for term in ["音视频系统", "指挥中心", "AI 视频", "弱电工程", "视频监控", "校园一卡通", "综合布线", "消防改造"]:
            self.assertIn(term, serialized)

    def test_normalize_migrates_legacy_keywords_and_assigns_ids(self):
        rows = normalize_keyword_library(None, legacy_keywords="弱电, 视频会议, 智慧校园")
        keywords = [row["keyword"] for row in rows]
        self.assertIn("弱电", keywords)
        self.assertIn("视频会议", keywords)
        self.assertTrue(all(row["id"] for row in rows))
        self.assertTrue(all(row["match_scope"] in {"title", "content", "title_content"} for row in rows))

    def test_parse_tsv_with_header_and_synonyms(self):
        parsed = parse_keyword_library_text(
            "business_direction\tsub_category\tkeyword\tsynonyms\tmatch_scope\tnote\tenabled\n"
            "音视频会议\t会议扩声\t会议系统\t视频会议,会议室\ttitle_content\t重点\ttrue\n"
        )
        self.assertEqual(parsed["rejected"], [])
        row = parsed["rows"][0]
        self.assertEqual(row["business_direction"], "音视频会议")
        self.assertEqual(row["keyword"], "会议系统")
        self.assertEqual(row["synonyms"], ["视频会议", "会议室"])
        self.assertTrue(row["enabled"])

    def test_parse_csv_without_header_rejects_bad_scope(self):
        parsed = parse_keyword_library_text("音视频会议,会议扩声,会议系统,视频会议,bad_scope,备注,true\n")
        self.assertEqual(parsed["rows"], [])
        self.assertEqual(parsed["rejected"][0]["reason"], "invalid match_scope")

    def test_derive_search_keywords_uses_enabled_main_keywords(self):
        rows = normalize_keyword_library(
            [
                {"id": "1", "enabled": True, "business_direction": "基础弱电 / 智能化工程", "sub_category": "", "keyword": "弱电", "synonyms": [], "match_scope": "title_content", "note": ""},
                {"id": "2", "enabled": False, "business_direction": "安防监控", "sub_category": "", "keyword": "视频监控", "synonyms": [], "match_scope": "title_content", "note": ""},
            ]
        )
        self.assertEqual(derive_search_keywords(rows, limit=5), ["弱电"])
        self.assertEqual(derive_legacy_keywords(rows), "弱电")

    def test_match_keyword_evidence_respects_scope_and_detail(self):
        rows = normalize_keyword_library(
            [
                {"id": "1", "enabled": True, "business_direction": "音视频会议", "sub_category": "", "keyword": "会议系统", "synonyms": ["报告厅"], "match_scope": "title", "note": ""},
                {"id": "2", "enabled": True, "business_direction": "安防监控", "sub_category": "", "keyword": "视频监控", "synonyms": [], "match_scope": "content", "note": ""},
            ]
        )
        evidence = match_keyword_evidence("报告厅改造", "包含视频监控", "详情会议系统", rows)
        self.assertEqual(evidence["title"], ["报告厅"])
        self.assertEqual(evidence["content"], ["视频监控"])
        self.assertEqual(evidence["detail"], [])

    def test_merge_replaces_same_id_and_appends_new_rows(self):
        existing = normalize_keyword_library([{"id": "same", "enabled": True, "business_direction": "旧", "sub_category": "", "keyword": "旧词", "synonyms": [], "match_scope": "title_content", "note": ""}])
        imported = normalize_keyword_library([{"id": "same", "enabled": False, "business_direction": "新", "sub_category": "", "keyword": "新词", "synonyms": [], "match_scope": "title", "note": ""}])
        merged = merge_keyword_library(existing, imported)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["keyword"], "新词")
        self.assertFalse(merged[0]["enabled"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_keyword_library.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.results.keyword_library'`.

- [ ] **Step 3: Implement `src/results/keyword_library.py`**

Create the module with dataclass-free dict helpers so it serializes cleanly through existing config JSON:

```python
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Any

MATCH_SCOPES = {"title", "content", "title_content"}

DEFAULT_KEYWORD_GROUPS = {
    "音视频会议": ["音视频", "音视频系统", "会议系统", "视频会议", "会议室", "无纸化会议", "会议扩声", "会议音响", "会议摄像机", "会议终端", "会议平板", "会议一体机", "智能会议室", "多功能厅", "报告厅", "阶梯教室", "录播教室", "录播系统", "精品录播", "常态化录播", "扩声系统", "音频系统", "调音台", "功放", "音箱", "麦克风", "无线话筒", "鹅颈话筒", "中控系统", "矩阵切换器", "视频矩阵", "分布式坐席", "分布式系统", "同声传译", "远程会议", "智慧会议", "会议预约", "会议管理平台"],
    "显示大屏与指挥中心": ["大屏", "LED显示屏", "LCD拼接屏", "液晶拼接屏", "DLP大屏", "显示系统", "可视化大屏", "指挥中心", "调度中心", "应急指挥", "作战指挥", "融媒体中心", "监控中心", "值班室", "控制室", "可视化平台", "信息发布屏", "信息发布系统", "触控一体机", "电子班牌", "导览屏", "数字标牌"],
    "AI 视频与智能分析": ["AI视频", "AI 视频", "智能视频分析", "视频智能分析", "视频结构化", "行为分析", "周界识别", "人脸识别", "车辆识别", "算法平台", "视觉识别", "视频算法", "智能预警", "智能监管", "AI监管", "AI管理平台", "AI 管理平台", "智能管理平台", "智慧监管平台", "视频联网平台", "视频汇聚平台", "视频云平台", "安防智能化", "图像识别", "客流分析", "人员轨迹", "异常行为识别"],
    "基础弱电 / 智能化工程": ["弱电", "弱电工程", "基础弱电", "智能化", "建筑智能化", "楼宇智能化", "智能化工程", "智能化系统", "信息化", "信息化建设", "信息化改造", "智慧校园", "智慧园区", "智慧楼宇", "智慧社区", "系统集成", "集成服务", "工程改造", "设备采购及安装", "维保", "运维", "维修", "改造", "升级", "扩容"],
    "安防监控": ["安防", "监控", "视频监控", "监控系统", "监控改造", "监控维保", "摄像头", "摄像机", "枪机", "球机", "半球", "硬盘录像机", "NVR", "DVR", "存储服务器", "安防平台", "安防系统", "电子围栏", "周界报警", "入侵报警", "一键报警", "报警系统", "巡更系统", "访客系统"],
    "门禁一卡通": ["门禁", "门禁系统", "门禁改造", "人脸门禁", "刷卡门禁", "闸机", "通道闸", "翼闸", "摆闸", "速通门", "一卡通", "校园一卡通", "消费系统", "考勤系统", "访客预约", "出入口管理", "车辆道闸", "停车场系统", "车牌识别"],
    "综合布线 / 网络 / 机房": ["综合布线", "网络布线", "弱电布线", "光纤", "网线", "桥架", "机柜", "配线架", "信息点", "网络改造", "无线网络", "WiFi", "无线覆盖", "AP", "交换机", "路由器", "防火墙", "网络设备", "机房", "数据中心", "UPS", "精密空调", "机房改造", "机房建设", "服务器", "存储", "等保", "网络安全"],
    "可做杂项": ["消防", "消防改造", "消防报警", "暖通", "空调", "装修", "装修改造", "强电", "电力改造", "配电", "办公设备", "电脑", "打印机", "扫描仪", "耗材", "线缆", "软件开发", "管理系统", "平台建设"],
}
```

Then add helpers to normalize rows, split synonyms on comma-like separators, parse CSV/TSV with `csv.DictReader` or fixed columns, derive legacy/search keywords from enabled rows, and collect evidence by scope. Use stable generated IDs such as `kw-<uuid>` for rows missing an ID.

- [ ] **Step 4: Run keyword-library tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_keyword_library.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/results/keyword_library.py tests/test_keyword_library.py
git commit -m "feat: add structured keyword library"
```

## Task 2: Storage Migration and Opportunity Persistence

**Parallel safety:** Phase 1 serial. Exclusive lock on `src/database/storage.py`.

**Files:**
- Modify: `src/database/storage.py`
- Modify: `tests/test_storage_results_center.py`

**Interfaces:**
- Consumes: no new code from Task 1.
- Produces:
  - `BidInfo` fields for all opportunity columns.
  - Storage migration columns for opportunity evaluation.
  - `Storage.update_opportunity_evaluation(result_id: int, evaluation: dict, columns: dict, error: str | None = None) -> None`
  - `Storage.update_opportunity_review(result_id: int, update: dict) -> None`
  - `Storage.query_results(filters: dict | None = None, limit: int = 50, offset: int = 0) -> tuple[list[BidInfo], int]` supports filters for opportunity fields and default opportunity sort.

- [ ] **Step 1: Add failing storage tests**

Append these tests to `tests/test_storage_results_center.py`:

```python
    def test_new_database_has_opportunity_columns(self):
        storage = self.make_storage()
        conn = sqlite3.connect(storage.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(bids)").fetchall()}

        for column in [
            "ai_suggestion",
            "opportunity_score",
            "manual_priority",
            "business_directions",
            "matched_keywords",
            "region_category",
            "owner_type",
            "owner_priority",
            "amount_band",
            "risk_flags",
            "score_breakdown",
            "ai_reason_summary",
            "deadline_summary",
            "opportunity_raw_evaluation",
            "manual_score_overrides",
            "opportunity_review_notes",
            "opportunity_eval_status",
            "opportunity_eval_error",
        ]:
            self.assertIn(column, columns)

    def test_existing_database_migrates_opportunity_defaults(self):
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

        self.assertEqual(bid.ai_suggestion, "")
        self.assertEqual(bid.opportunity_score, 0)
        self.assertEqual(bid.manual_priority, "未设置")
        self.assertEqual(bid.business_directions, [])
        self.assertEqual(bid.risk_flags, [])

    def test_update_opportunity_evaluation_persists_columns_and_json(self):
        storage = self.make_storage()
        result_id = storage.save(BidInfo("上海会议系统采购意向", "https://example.com/o", "2026-07-01", "源"))
        normalized = {
            "ai_suggestion": "强烈跟进",
            "score": 92,
            "business_directions": ["音视频会议"],
            "matched_keywords": {"title": ["会议系统"], "content": [], "detail": ["报告厅"]},
            "region_category": "上海市区",
            "owner_type": "学校",
            "owner_priority": "第一优先级",
            "amount_band": "200-500万",
            "deadline_summary": "采购意向，日期不明",
            "risk_flags": ["日期不明"],
            "reason_summary": "上海学校会议系统采购意向",
            "score_breakdown": {"business": "核心方向"},
        }
        columns = {
            "ai_suggestion": "强烈跟进",
            "opportunity_score": 92,
            "business_directions": ["音视频会议"],
            "matched_keywords": {"title": ["会议系统"], "content": [], "detail": ["报告厅"]},
            "region_category": "上海市区",
            "owner_type": "学校",
            "owner_priority": "第一优先级",
            "amount_band": "200-500万",
            "deadline_summary": "采购意向，日期不明",
            "risk_flags": ["日期不明"],
            "ai_reason_summary": "上海学校会议系统采购意向",
            "score_breakdown": {"business": "核心方向"},
        }

        storage.update_opportunity_evaluation(result_id, normalized, columns)

        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.ai_suggestion, "强烈跟进")
        self.assertEqual(bid.opportunity_score, 92)
        self.assertEqual(bid.business_directions, ["音视频会议"])
        self.assertEqual(bid.matched_keywords["detail"], ["报告厅"])
        self.assertEqual(bid.opportunity_raw_evaluation["score"], 92)
        self.assertEqual(bid.opportunity_eval_status, "evaluated")

    def test_update_opportunity_review_and_default_sort(self):
        storage = self.make_storage()
        top_id = storage.save(BidInfo("置顶项目", "https://example.com/top", "2026-07-01", "源"))
        high_score_id = storage.save(BidInfo("高分项目", "https://example.com/high", "2026-07-02", "源"))
        ignored_id = storage.save(BidInfo("忽略项目", "https://example.com/ignore", "2026-07-03", "源"))
        storage.update_opportunity_review(top_id, {"manual_priority": "置顶", "follow_decision": "follow", "opportunity_review_notes": "重点"})
        storage.update_opportunity_evaluation(high_score_id, {"score": 95}, {"opportunity_score": 95, "ai_suggestion": "建议跟进"})
        storage.update_opportunity_review(ignored_id, {"manual_priority": "忽略"})

        rows, total = storage.query_results({}, limit=10, offset=0)

        self.assertEqual(total, 3)
        self.assertEqual([row.id for row in rows], [top_id, high_score_id, ignored_id])
        self.assertEqual(storage.get_by_id(top_id).follow_decision, "follow")
        self.assertEqual(storage.get_by_id(top_id).opportunity_review_notes, "重点")
```

- [ ] **Step 2: Run storage tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_storage_results_center.py -q
```

Expected: FAIL because opportunity columns and methods do not exist.

- [ ] **Step 3: Extend storage schema and `BidInfo`**

Modify `src/database/storage.py`:

- Add opportunity columns to `RESULT_CENTER_COLUMNS`.
- Add opportunity filters to `RESULT_QUERY_FILTERS`.
- Implement `business_direction` as a special query filter against the JSON text in `business_directions`; use a conservative `LIKE` predicate with a JSON-quoted needle such as `%"音视频会议"%`.
- Add dataclass fields to `BidInfo`.
- Load JSON fields in `_row_to_bid`.
- Include defaults in `save`.
- Add JSON-aware update methods.

Use these defaults:

```python
OPPORTUNITY_COLUMNS = {
    "ai_suggestion": "TEXT DEFAULT ''",
    "opportunity_score": "INTEGER DEFAULT 0",
    "manual_priority": "TEXT DEFAULT '未设置'",
    "business_directions": "TEXT DEFAULT '[]'",
    "matched_keywords": "TEXT DEFAULT '{}'",
    "region_category": "TEXT DEFAULT ''",
    "owner_type": "TEXT DEFAULT ''",
    "owner_priority": "TEXT DEFAULT ''",
    "amount_band": "TEXT DEFAULT ''",
    "risk_flags": "TEXT DEFAULT '[]'",
    "score_breakdown": "TEXT DEFAULT '{}'",
    "ai_reason_summary": "TEXT DEFAULT ''",
    "deadline_summary": "TEXT DEFAULT ''",
    "opportunity_raw_evaluation": "TEXT DEFAULT '{}'",
    "manual_score_overrides": "TEXT DEFAULT '{}'",
    "opportunity_review_notes": "TEXT DEFAULT ''",
    "opportunity_eval_status": "TEXT DEFAULT 'pending'",
    "opportunity_eval_error": "TEXT DEFAULT ''",
}
```

Add priority sort expression inside `query_results`:

```python
ORDER BY CASE COALESCE(NULLIF(manual_priority, ''), '未设置')
    WHEN '置顶' THEN 0
    WHEN '高' THEN 1
    WHEN '中' THEN 2
    WHEN '低' THEN 3
    WHEN '未设置' THEN 4
    WHEN '忽略' THEN 5
    ELSE 4
END ASC,
opportunity_score DESC,
COALESCE(NULLIF(publish_date, ''), created_at) DESC,
created_at DESC
```

- [ ] **Step 4: Run storage tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_storage_results_center.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/database/storage.py tests/test_storage_results_center.py
git commit -m "feat: store opportunity evaluation fields"
```

## Task 3: Opportunity Evaluator Module

**Parallel safety:** Phase 1 serial. Can be followed by Task 7 and Task 6.

**Files:**
- Create: `src/results/opportunity_evaluator.py`
- Create: `tests/test_opportunity_evaluator.py`

**Interfaces:**
- Consumes: `src.results.keyword_library.keyword_library_directions`
- Produces:
  - `OpportunityEvaluator(config: dict | None)`
  - `OpportunityEvaluator.evaluate(title: str, url: str, source: str, publish_date: str, summary: str, detail_text: str, keyword_library: list[dict], matched_keywords: dict, extracted_data: dict | None = None) -> dict`
  - `normalize_opportunity_result(data: dict, fallback_matched_keywords: dict | None = None) -> dict`
  - `build_opportunity_column_updates(normalized: dict) -> dict`

- [ ] **Step 1: Write failing evaluator tests**

Create `tests/test_opportunity_evaluator.py`:

```python
import json
import unittest
from unittest.mock import Mock, patch

from src.results.opportunity_evaluator import (
    OpportunityEvaluator,
    build_opportunity_column_updates,
    normalize_opportunity_result,
)


VALID_AI_JSON = {
    "ai_suggestion": "强烈跟进",
    "score": 108,
    "business_directions": ["音视频会议"],
    "matched_keywords": {"title": ["会议系统"], "content": [], "detail": ["报告厅"]},
    "project_stage": "采购意向",
    "region_category": "上海市区",
    "owner_name": "上海某大学",
    "owner_type": "大学",
    "owner_priority": "第一优先级",
    "amount": "300万元",
    "amount_band": "200-500万",
    "deadline_summary": "日期不明",
    "risk_flags": ["日期不明"],
    "reason_summary": "上海高校音视频会议采购意向",
    "score_breakdown": {"business": "核心业务", "region": "上海市区"},
}


class OpportunityEvaluatorTests(unittest.TestCase):
    def test_normalize_clamps_score_and_preserves_allowed_fields(self):
        normalized = normalize_opportunity_result(VALID_AI_JSON)

        self.assertEqual(normalized["score"], 100)
        self.assertEqual(normalized["ai_suggestion"], "强烈跟进")
        self.assertEqual(normalized["business_directions"], ["音视频会议"])
        self.assertEqual(normalized["matched_keywords"]["title"], ["会议系统"])
        self.assertEqual(normalized["reason_summary"], "上海高校音视频会议采购意向")

    def test_normalize_replaces_unknown_enums_with_safe_defaults(self):
        normalized = normalize_opportunity_result(
            {
                "ai_suggestion": "马上冲",
                "score": -5,
                "project_stage": "奇怪阶段",
                "region_category": "火星",
                "owner_priority": "超级优先",
                "amount_band": "很多钱",
            },
            fallback_matched_keywords={"title": ["弱电"], "content": [], "detail": []},
        )

        self.assertEqual(normalized["score"], 0)
        self.assertEqual(normalized["ai_suggestion"], "观察待确认")
        self.assertEqual(normalized["project_stage"], "未知")
        self.assertEqual(normalized["region_category"], "未知")
        self.assertEqual(normalized["owner_priority"], "未知")
        self.assertEqual(normalized["amount_band"], "未写金额")
        self.assertEqual(normalized["matched_keywords"]["title"], ["弱电"])

    def test_build_column_updates_maps_normalized_result(self):
        normalized = normalize_opportunity_result(VALID_AI_JSON)

        columns = build_opportunity_column_updates(normalized)

        self.assertEqual(columns["ai_suggestion"], "强烈跟进")
        self.assertEqual(columns["opportunity_score"], 100)
        self.assertEqual(columns["business_directions"], ["音视频会议"])
        self.assertEqual(columns["risk_flags"], ["日期不明"])
        self.assertEqual(columns["ai_reason_summary"], "上海高校音视频会议采购意向")

    def test_parse_json_text_rejects_non_object(self):
        evaluator = OpportunityEvaluator({})

        with self.assertRaisesRegex(ValueError, "AI opportunity JSON must be an object"):
            evaluator._parse_json_text("[1, 2]")

    def test_evaluate_responses_payload_and_json_only_prompt(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "responses",
        }
        response = Mock()
        response.json.return_value = {"output_text": json.dumps(VALID_AI_JSON, ensure_ascii=False)}
        response.raise_for_status.return_value = None

        with patch("src.results.opportunity_evaluator.requests.post", return_value=response) as post:
            result = OpportunityEvaluator(config).evaluate(
                "上海某大学会议系统采购意向",
                "https://example.com/a",
                "源",
                "2026-07-01",
                "摘要",
                "报告厅音视频会议系统",
                [{"business_direction": "音视频会议", "keyword": "会议系统", "enabled": True}],
                {"title": ["会议系统"], "content": [], "detail": ["报告厅"]},
                {"amount": "300", "region": "上海"},
            )

        self.assertEqual(result["ai_suggestion"], "强烈跟进")
        payload = post.call_args.kwargs["json"]
        self.assertIn("input", payload)
        self.assertIn("严格只返回 JSON", payload["input"])
        self.assertIn("关键词命中只是证据", payload["input"])
        self.assertEqual(post.call_args.args[0], "https://api.example.com/v1/responses")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run evaluator tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_opportunity_evaluator.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement evaluator module**

Create `src/results/opportunity_evaluator.py` with:

- endpoint handling parallel to `AIExtractor`
- JSON extraction compatible with fenced JSON and wrapped object text
- prompt containing the business rules from the spec
- enum normalization sets:

```python
AI_SUGGESTIONS = {"强烈跟进", "建议跟进", "观察待确认", "不建议跟进"}
PROJECT_STAGES = {"采购意向", "预采购", "预招标", "正式公告", "已过期", "未知"}
REGION_CATEGORIES = {"上海市区", "上海郊区", "江苏", "浙江", "安徽", "其它外地", "上海业主外地项目", "未知"}
OWNER_PRIORITIES = {"第一优先级", "第二优先级", "第三优先级", "未知"}
AMOUNT_BANDS = {"未写金额", "10万以下", "10-50万", "50-200万", "200-500万", "500-1000万", "1000万以上", "亿级"}
```

Do not import or call `KeywordMatcher`.

- [ ] **Step 4: Run evaluator tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_opportunity_evaluator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/results/opportunity_evaluator.py tests/test_opportunity_evaluator.py
git commit -m "feat: add opportunity evaluator"
```

## Task 4: Keyword Library Config and API

**Parallel safety:** Phase 2. Exclusive lock on `server/app.py`. Run before Task 6.

**Files:**
- Modify: `server/app.py`
- Modify: `tests/test_server_config_defaults.py`
- Create: `tests/test_server_keyword_library_api.py`

**Interfaces:**
- Consumes from Task 1:
  - `normalize_keyword_library`
  - `derive_legacy_keywords`
  - `parse_keyword_library_text`
  - `merge_keyword_library`
  - `keyword_library_directions`
- Produces:
  - config key `keyword_library`
  - API routes `get_keyword_library`, `update_keyword_library`, `import_keyword_library`

- [ ] **Step 1: Write failing config/default tests**

Append to `tests/test_server_config_defaults.py`:

```python
    def test_default_config_contains_keyword_library_and_derived_keywords(self):
        with patch.object(app.os.path, "exists", return_value=False):
            config = app.load_config()

        self.assertIn("keyword_library", config)
        self.assertTrue(config["keyword_library"])
        directions = {row["business_direction"] for row in config["keyword_library"]}
        self.assertIn("基础弱电 / 智能化工程", directions)
        self.assertIn("音视频会议", directions)
        self.assertIn("弱电", config["keywords"])
        self.assertEqual(config["must_contain"], "")

    def test_normalize_config_migrates_legacy_keywords_into_keyword_library(self):
        normalized = app.normalize_config(
            {
                "keywords": "弱电,视频会议",
                "exclude": "旧排除",
                "must_contain": "旧必含",
                "csv_url_sources": [],
            }
        )

        keywords = {row["keyword"] for row in normalized["keyword_library"]}
        self.assertIn("弱电", keywords)
        self.assertIn("视频会议", keywords)
        self.assertIn("弱电", normalized["keywords"])
        self.assertEqual(normalized["exclude"], "旧排除")
        self.assertEqual(normalized["must_contain"], "旧必含")
```

- [ ] **Step 2: Write failing API tests**

Create `tests/test_server_keyword_library_api.py`:

```python
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
SRC_DIR = os.path.join(ROOT_DIR, "src")
for path in [SERVER_DIR, SRC_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

import app


class ServerKeywordLibraryApiTests(unittest.TestCase):
    def setUp(self):
        app.app_state.config = app.normalize_config({"csv_url_sources": []})

    def test_get_keyword_library_returns_rows_and_directions(self):
        result = asyncio.run(app.get_keyword_library(user={"role": "user"}))

        self.assertIn("items", result)
        self.assertIn("business_directions", result)
        self.assertTrue(result["items"])
        self.assertIn("基础弱电 / 智能化工程", result["business_directions"])

    def test_update_keyword_library_saves_normalized_rows_and_derived_keywords(self):
        payload = {
            "items": [
                {
                    "id": "row-1",
                    "enabled": True,
                    "business_direction": "音视频会议",
                    "sub_category": "会议扩声",
                    "keyword": "会议系统",
                    "synonyms": "视频会议,会议室",
                    "match_scope": "title_content",
                    "note": "重点",
                }
            ]
        }

        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.update_keyword_library(payload, user={"role": "admin"}))

        self.assertTrue(result["success"])
        row = app.app_state.config["keyword_library"][0]
        self.assertEqual(row["synonyms"], ["视频会议", "会议室"])
        self.assertEqual(app.app_state.config["keywords"], "会议系统")
        save_config.assert_called_once_with(app.app_state.config)

    def test_import_keyword_library_merges_tsv_rows(self):
        payload = {
            "text": "business_direction\tsub_category\tkeyword\tsynonyms\tmatch_scope\tnote\tenabled\n"
                    "安防监控\t监控\t视频监控\t摄像机\ttitle_content\t\ttrue\n",
            "mode": "merge",
        }

        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.import_keyword_library(payload, user={"role": "admin"}))

        self.assertTrue(result["success"])
        self.assertEqual(result["rejected"], [])
        self.assertIn("视频监控", {row["keyword"] for row in app.app_state.config["keyword_library"]})
        save_config.assert_called_once_with(app.app_state.config)

    def test_import_keyword_library_preview_does_not_save(self):
        payload = {
            "text": "音视频会议,会议扩声,会议系统,视频会议,title_content,,true\n",
            "mode": "preview",
        }

        before = list(app.app_state.config["keyword_library"])
        with patch.object(app, "save_config") as save_config:
            result = asyncio.run(app.import_keyword_library(payload, user={"role": "admin"}))

        self.assertFalse(result["success"])
        self.assertEqual(app.app_state.config["keyword_library"], before)
        self.assertTrue(result["items"])
        save_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_default_config_contains_keyword_library_and_derived_keywords tests/test_server_config_defaults.py::ServerConfigDefaultsTests::test_normalize_config_migrates_legacy_keywords_into_keyword_library tests/test_server_keyword_library_api.py -q
```

Expected: FAIL because `keyword_library` config and routes do not exist.

- [ ] **Step 4: Implement config normalization and routes**

Modify `server/app.py`:

- import from `results.keyword_library`
- add `keyword_library` to default config via `normalize_keyword_library(None, default_keywords)`
- update `normalize_config` so it always sets normalized `keyword_library` and derived `keywords`
- add route functions:

```python
@app.get("/api/keyword-library")
async def get_keyword_library(user: Dict[str, Any] = Depends(get_current_user)):
    library = normalize_keyword_library(app_state.config.get("keyword_library"), app_state.config.get("keywords", ""))
    return {"items": library, "business_directions": keyword_library_directions(library)}


@app.post("/api/keyword-library")
async def update_keyword_library(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    rows = payload.get("items") if isinstance(payload, dict) else payload
    library = normalize_keyword_library(rows)
    app_state.config["keyword_library"] = library
    app_state.config["keywords"] = derive_legacy_keywords(library)
    save_config(app_state.config)
    return {"success": True, "items": library, "business_directions": keyword_library_directions(library)}


@app.post("/api/keyword-library/import")
async def import_keyword_library(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    parsed = parse_keyword_library_text(str(payload.get("text") or ""))
    mode = payload.get("mode") or "merge"
    merged = merge_keyword_library(app_state.config.get("keyword_library", []), parsed["rows"])
    if mode == "preview":
        return {"success": False, "items": merged, "parsed": parsed["rows"], "rejected": parsed["rejected"]}
    app_state.config["keyword_library"] = merged
    app_state.config["keywords"] = derive_legacy_keywords(merged)
    save_config(app_state.config)
    return {"success": True, "items": merged, "parsed": parsed["rows"], "rejected": parsed["rejected"], "business_directions": keyword_library_directions(merged)}
```

Adjust names to avoid collisions with existing helpers.

- [ ] **Step 5: Run keyword API tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_server_config_defaults.py tests/test_server_keyword_library_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add server/app.py tests/test_server_config_defaults.py tests/test_server_keyword_library_api.py
git commit -m "feat: expose keyword library api"
```

## Task 5: Web Keyword Library and Opportunity UI

**Parallel safety:** Phase 2. Exclusive lock on Web static files. Can run in parallel with Task 7 or Task 8, not with another Web task.

**Files:**
- Modify: `server/static/index.html`
- Modify: `server/static/app.js`
- Modify: `server/static/styles.css`
- Modify: `tests/test_static_frontend_assets.py`

**Interfaces:**
- Consumes from Task 4:
  - `GET /api/keyword-library`
  - `POST /api/keyword-library`
  - `POST /api/keyword-library/import`
- Consumes from Task 6 by contract:
  - opportunity fields in `/api/results`
  - `PATCH /api/results/{id}/opportunity-review`
- Produces: static DOM and JS contract for keyword-library UI and opportunity result UI.

- [ ] **Step 1: Write failing static frontend tests**

Append to `tests/test_static_frontend_assets.py`:

```python
    def test_keyword_library_replaces_legacy_search_textarea_contract(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        for hook in [
            "keywordLibraryTableBody",
            "keywordDirectionFilter",
            "keywordImportModal",
            "keywordImportText",
            "keywordSelectAll",
        ]:
            self.assertIn(hook, html)
        for label in ["业务方向", "子类", "关键词", "同义词", "匹配范围", "备注"]:
            self.assertIn(label, html)
        self.assertNotIn('id="cfgKeywords"', html)
        self.assertNotIn('id="cfgExclude"', html)
        self.assertNotIn('id="cfgMustContain"', html)
        for fn in [
            "loadKeywordLibrary",
            "renderKeywordLibrary",
            "addKeywordRow",
            "deleteSelectedKeywordRows",
            "setSelectedKeywordRowsEnabled",
            "openKeywordImport",
            "importKeywordLibrary",
            "exportKeywordLibrary",
            "saveKeywordLibrary",
        ]:
            self.assertIn(f"function {fn}", js)
        for endpoint in ["/api/keyword-library", "/api/keyword-library/import"]:
            self.assertIn(endpoint, js)
        self.assertIn(".keyword-library-table", css)

    def test_results_ui_contains_opportunity_columns_filters_and_detail_controls(self):
        html = self.read("index.html")
        js = self.read("app.js")
        css = self.read("styles.css")

        for header in ["AI建议", "人工优先级", "评分", "业务方向", "地区分类", "业主类型", "金额档位", "截止摘要", "AI理由", "人工决策"]:
            self.assertIn(header, html)
        for hook in [
            "resultAiSuggestionFilter",
            "resultManualPriorityFilter",
            "resultBusinessDirectionFilter",
            "resultRegionCategoryFilter",
            "resultOwnerTypeFilter",
            "resultAmountBandFilter",
            "detailOpportunitySummary",
            "detailScoreBreakdown",
            "detailMatchedKeywords",
            "detailRiskFlags",
            "detailManualPriority",
            "detailOpportunityNotes",
        ]:
            self.assertIn(hook, html)
        for fn in [
            "renderOpportunityCell",
            "renderScoreBreakdown",
            "renderMatchedKeywords",
            "saveActiveOpportunityReview",
        ]:
            self.assertIn(f"function {fn}", js)
        self.assertIn("/opportunity-review", js)
        self.assertIn(".opportunity-summary", css)
```

- [ ] **Step 2: Run static tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_keyword_library_replaces_legacy_search_textarea_contract tests/test_static_frontend_assets.py::StaticFrontendAssetsTests::test_results_ui_contains_opportunity_columns_filters_and_detail_controls -q
```

Expected: FAIL because hooks and functions do not exist.

- [ ] **Step 3: Replace Web search config controls**

Modify the `page-sites` search card in `server/static/index.html`:

- remove `cfgKeywords`, `cfgExclude`, `cfgMustContain`
- add keyword library toolbar, table, direction filter, import modal
- keep `cfgInterval` and `cfgSelenium`

Required table body hook:

```html
<tbody id="keywordLibraryTableBody"></tbody>
```

Required import modal hook:

```html
<div id="keywordImportModal" class="modal">
  <div class="modal-content">
    <div class="modal-header"><span>导入关键词库</span><button class="modal-close" onclick="closeModal('keywordImportModal')" aria-label="关闭"><svg class="icon" aria-hidden="true"><use href="#icon-x"></use></svg></button></div>
    <div class="modal-body">
      <textarea class="config-input" id="keywordImportText" rows="10"></textarea>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline modal-action" onclick="closeModal('keywordImportModal')">取消</button>
      <button class="btn btn-primary modal-action" onclick="importKeywordLibrary()">导入</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Implement keyword library JS**

Modify `server/static/app.js`:

- add `let keywordLibrary = [], selectedKeywordRowIds = new Set();`
- `showPage('sites')` calls `loadKeywordLibrary()`
- `loadConfig()` no longer reads removed legacy inputs
- `saveConfig()` no longer writes removed legacy inputs
- add required functions from Step 1
- `exportKeywordLibrary()` creates TSV and uses `navigator.clipboard.writeText(tsv)` with fallback to a temporary textarea.

Use row update function:

```javascript
function updateKeywordRow(id, field, value) {
    keywordLibrary = keywordLibrary.map(row => row.id === id ? { ...row, [field]: value } : row);
}
```

- [ ] **Step 5: Update results table and detail UI**

Modify `server/static/index.html` and `server/static/app.js`:

- add opportunity filters to `buildResultQuery`
- replace or extend result table columns with opportunity columns
- show `ai_suggestion`, `manual_priority`, `opportunity_score`, `business_directions`, `region_category`, `owner_type`, `amount_band`, `deadline_summary`, `ai_reason_summary`, `follow_decision`
- add detail controls for opportunity review and call `PATCH /api/results/{id}/opportunity-review`

- [ ] **Step 6: Add compact CSS**

Modify `server/static/styles.css` with dense, non-card-nested table styles:

```css
.keyword-library-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}

.keyword-library-table th,
.keyword-library-table td {
    border-bottom: 1px solid var(--hairline);
    padding: 8px;
    vertical-align: middle;
}

.opportunity-summary,
.score-breakdown,
.matched-keyword-groups {
    display: grid;
    gap: 8px;
}
```

- [ ] **Step 7: Run static tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_static_frontend_assets.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add server/static/index.html server/static/app.js server/static/styles.css tests/test_static_frontend_assets.py
git commit -m "feat: add keyword library web ui"
```

## Task 6: Results Opportunity API and Review Endpoint

**Parallel safety:** Phase 2. Exclusive lock on `server/app.py`. Run after Task 4.

**Files:**
- Modify: `server/app.py`
- Modify: `src/results/review.py`
- Modify: `tests/test_server_results_api.py`
- Modify: `tests/test_result_review.py`

**Interfaces:**
- Consumes from Task 2:
  - `BidInfo` opportunity fields
  - `Storage.update_opportunity_review`
  - opportunity filters in `Storage.query_results`
- Produces:
  - result summary/detail opportunity fields
  - `PATCH /api/results/{id}/opportunity-review`
  - `validate_opportunity_review_update(payload: dict) -> dict`

- [ ] **Step 1: Write failing review helper tests**

Append to `tests/test_result_review.py`:

```python
    def test_validate_opportunity_review_update_accepts_supported_fields(self):
        from src.results.review import validate_opportunity_review_update

        normalized = validate_opportunity_review_update(
            {
                "ai_suggestion": "建议跟进",
                "manual_priority": "高",
                "business_directions": ["音视频会议"],
                "project_stage": "采购意向",
                "region_category": "上海市区",
                "owner_type": "大学",
                "owner_priority": "第一优先级",
                "amount_band": "200-500万",
                "follow_decision": "follow",
                "opportunity_review_notes": "提前介入",
            }
        )

        self.assertEqual(normalized["manual_priority"], "高")
        self.assertEqual(normalized["follow_decision"], "follow")
        self.assertEqual(normalized["business_directions"], ["音视频会议"])

    def test_validate_opportunity_review_update_rejects_unknown_priority(self):
        from src.results.review import validate_opportunity_review_update

        with self.assertRaises(ValueError):
            validate_opportunity_review_update({"manual_priority": "最高"})
```

- [ ] **Step 2: Write failing API tests**

Append to `tests/test_server_results_api.py`:

```python
    def test_get_results_returns_opportunity_fields_and_filters(self):
        bid = self.make_bid()
        bid.ai_suggestion = "建议跟进"
        bid.opportunity_score = 88
        bid.manual_priority = "高"
        bid.business_directions = ["音视频会议"]
        bid.region_category = "上海市区"
        bid.owner_type = "大学"
        bid.owner_priority = "第一优先级"
        bid.amount_band = "200-500万"
        bid.deadline_summary = "7天后截止"
        bid.risk_flags = ["时间较紧"]
        bid.ai_reason_summary = "上海高校音视频项目"
        self.storage.query_results.return_value = ([bid], 1)

        result = asyncio.run(
            app.get_results(
                limit=20,
                offset=0,
                ai_suggestion="建议跟进",
                manual_priority="高",
                business_direction="音视频会议",
                region_category="上海市区",
                owner_type="大学",
                amount_band="200-500万",
                user={"role": "user"},
            )
        )

        item = result["items"][0]
        self.assertEqual(item["ai_suggestion"], "建议跟进")
        self.assertEqual(item["opportunity_score"], 88)
        self.assertEqual(item["manual_priority"], "高")
        self.assertEqual(item["business_directions"], ["音视频会议"])
        filters = self.storage.query_results.call_args.args[0]
        self.assertEqual(filters["ai_suggestion"], "建议跟进")
        self.assertEqual(filters["manual_priority"], "高")
        self.assertEqual(filters["business_direction"], "音视频会议")

    def test_get_result_detail_returns_full_opportunity_details(self):
        bid = self.make_bid()
        bid.matched_keywords = {"title": ["会议系统"], "content": [], "detail": ["报告厅"]}
        bid.score_breakdown = {"business": "核心业务"}
        bid.opportunity_raw_evaluation = {"score": 88}
        bid.manual_score_overrides = {"amount_band": "200-500万"}
        self.storage.get_by_id.return_value = bid

        result = asyncio.run(app.get_result_detail(7, user={"role": "user"}))

        self.assertEqual(result["matched_keywords"]["title"], ["会议系统"])
        self.assertEqual(result["score_breakdown"]["business"], "核心业务")
        self.assertEqual(result["opportunity_raw_evaluation"]["score"], 88)

    def test_update_opportunity_review_saves_valid_payload(self):
        self.storage.get_by_id.return_value = self.make_bid()

        result = asyncio.run(
            app.update_result_opportunity_review(
                7,
                {"manual_priority": "高", "follow_decision": "follow", "opportunity_review_notes": "重点跟进"},
                user={"role": "user"},
            )
        )

        self.assertTrue(result["success"])
        self.storage.update_opportunity_review.assert_called_once_with(
            7,
            {"manual_priority": "高", "follow_decision": "follow", "opportunity_review_notes": "重点跟进"},
        )
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_result_review.py tests/test_server_results_api.py -q
```

Expected: FAIL because opportunity review validator, route, and serializer fields do not exist.

- [ ] **Step 4: Implement review validator**

Modify `src/results/review.py`:

```python
AI_SUGGESTIONS = {"强烈跟进", "建议跟进", "观察待确认", "不建议跟进"}
MANUAL_PRIORITIES = {"置顶", "高", "中", "低", "未设置", "忽略"}
OPPORTUNITY_PROJECT_STAGES = {"采购意向", "预采购", "预招标", "正式公告", "已过期", "未知"}
REGION_CATEGORIES = {"上海市区", "上海郊区", "江苏", "浙江", "安徽", "其它外地", "上海业主外地项目", "未知"}
OWNER_PRIORITIES = {"第一优先级", "第二优先级", "第三优先级", "未知"}
AMOUNT_BANDS = {"未写金额", "10万以下", "10-50万", "50-200万", "200-500万", "500-1000万", "1000万以上", "亿级"}


def validate_opportunity_review_update(payload: dict) -> dict:
    # validate only supplied fields; convert lists to clean string lists; raise ValueError on unsupported enum
```

Use existing `FOLLOW_DECISIONS` for follow decision validation.

- [ ] **Step 5: Implement result API fields and endpoint**

Modify `server/app.py`:

- import `validate_opportunity_review_update`
- add opportunity fields in `result_summary`
- add full fields in `result_detail_payload`
- extend `get_results` signature with opportunity filters
- map `business_direction` filter to storage filter
- add route:

```python
@app.patch("/api/results/{result_id}/opportunity-review")
async def update_result_opportunity_review(result_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    bid = app_state.storage.get_by_id(result_id)
    if not bid:
        raise _result_not_found(result_id)
    try:
        update = validate_opportunity_review_update(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    app_state.storage.update_opportunity_review(result_id, update)
    return {"success": True}
```

- [ ] **Step 6: Run API tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_result_review.py tests/test_server_results_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

Run:

```bash
git add server/app.py src/results/review.py tests/test_server_results_api.py tests/test_result_review.py
git commit -m "feat: add opportunity review results api"
```

## Task 7: Monitor Flow and Enrichment Integration

**Parallel safety:** Phase 2. Exclusive lock on monitor/enrichment files. Can run in parallel with Task 5 or Task 8 after Tasks 1-3.

**Files:**
- Modify: `src/results/ai_extractor.py`
- Modify: `src/monitor_core.py`
- Modify: `tests/test_ai_extractor.py`
- Modify: `tests/test_monitor_core_ai_extraction.py`

**Interfaces:**
- Consumes from Task 1:
  - `derive_search_keywords`
  - `match_keyword_evidence`
- Consumes from Task 3:
  - `OpportunityEvaluator`
  - `build_opportunity_column_updates`
- Consumes from Task 2:
  - `Storage.update_opportunity_evaluation`
- Produces:
  - `enrich_new_bid(storage, result_id: int, bid, ai_config: dict | None, log_callback=None, fetch_config: dict | None = None, keyword_library: list[dict] | None = None, matched_keywords: dict | None = None) -> dict`
  - monitor flow with no `AIGuard` insertion/filter semantics

- [ ] **Step 1: Write failing AI enrichment tests**

Append to `tests/test_ai_extractor.py`:

```python
    def test_enrich_new_bid_runs_opportunity_evaluation_after_detail_fetch(self):
        storage = self.make_storage()
        bid = BidInfo("上海会议系统采购意向", "https://example.com/opp", "2026-07-01", "源", content="上海大学报告厅")
        result_id = storage.save(bid)
        opportunity = {
            "ai_suggestion": "强烈跟进",
            "score": 90,
            "business_directions": ["音视频会议"],
            "matched_keywords": {"title": ["会议系统"], "content": [], "detail": ["报告厅"]},
            "project_stage": "采购意向",
            "region_category": "上海市区",
            "owner_type": "大学",
            "owner_priority": "第一优先级",
            "amount_band": "未写金额",
            "deadline_summary": "日期不明",
            "risk_flags": ["日期不明"],
            "reason_summary": "上海高校会议系统采购意向",
            "score_breakdown": {"business": "核心"},
        }

        with patch("src.results.ai_extractor.fetch_detail_text", return_value=(True, "报告厅会议系统详情", None)):
            with patch("src.results.ai_extractor.AIExtractor.extract", return_value={"organization": "上海大学", "deadlines": []}):
                with patch("src.results.ai_extractor.OpportunityEvaluator") as evaluator_cls:
                    evaluator_cls.return_value.evaluate.return_value = opportunity
                    result = enrich_new_bid(
                        storage,
                        result_id,
                        bid,
                        {"enable": True, "api_key": "secret", "base_url": "https://api.example.com/v1", "model": "grok-4.20-fast"},
                        keyword_library=[{"id": "1", "enabled": True, "business_direction": "音视频会议", "keyword": "会议系统", "synonyms": [], "match_scope": "title_content", "note": "", "sub_category": ""}],
                        matched_keywords={"title": ["会议系统"], "content": [], "detail": []},
                    )

        updated = storage.get_by_id(result_id)
        self.assertEqual(result["opportunity"]["ai_suggestion"], "强烈跟进")
        self.assertEqual(updated.ai_suggestion, "强烈跟进")
        self.assertEqual(updated.opportunity_score, 90)
        self.assertEqual(updated.opportunity_eval_status, "evaluated")
```

- [ ] **Step 2: Write failing monitor tests**

Append or update `tests/test_monitor_core_ai_extraction.py`:

```python
    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_monitor_derives_keywords_from_keyword_library_and_does_not_create_ai_guard(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=[],
            keyword_library=[
                {"id": "1", "enabled": True, "business_direction": "基础弱电 / 智能化工程", "sub_category": "", "keyword": "弱电", "synonyms": [], "match_scope": "title_content", "note": ""}
            ],
            crawler_overrides={"enabled_sites": []},
            ai_config={"enable": True, "api_key": "secret"},
        )
        monitor.crawlers = [FakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid", return_value={"opportunity": {"ai_suggestion": "不建议跟进"}}) as enrich:
            result = monitor.run_once()

        self.assertEqual(monitor.keywords, ["弱电"])
        self.assertIsNone(getattr(monitor, "ai_guard", None))
        self.assertEqual(result["new_count"], 1)
        storage.save.assert_called_once()
        enrich.assert_called_once()

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_ai_not_recommended_result_is_still_saved(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={"enabled_sites": []},
            ai_config={"enable": True, "api_key": "secret"},
        )
        monitor.crawlers = [FakeCrawler()]

        with patch("src.monitor_core.enrich_new_bid", return_value={"opportunity": {"ai_suggestion": "不建议跟进"}}):
            result = monitor.run_once()

        self.assertEqual(result["new_count"], 1)
        storage.save.assert_called_once()
        storage.update_review.assert_not_called()
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_ai_extractor.py tests/test_monitor_core_ai_extraction.py -q
```

Expected: FAIL because `keyword_library` argument, opportunity evaluator wiring, and no-`AIGuard` semantics are not implemented.

- [ ] **Step 4: Update enrichment**

Modify `src/results/ai_extractor.py`:

- import `OpportunityEvaluator`, `build_opportunity_column_updates`, and `match_keyword_evidence`
- extend `enrich_new_bid` signature:

```python
def enrich_new_bid(storage, result_id: int, bid, ai_config: dict | None, log_callback=None, fetch_config: dict | None = None, keyword_library: list[dict] | None = None, matched_keywords: dict | None = None) -> dict:
```

- always return a dict:

```python
{"detail_status": "success", "ai_extract_status": "extracted", "opportunity": normalized_or_none}
{"detail_status": "failed", "ai_extract_status": "detail_fetch_failed", "opportunity": None}
{"detail_status": "success", "ai_extract_status": "extract_failed", "opportunity": None}
```

- after successful detail fetch, compute detail evidence and call `OpportunityEvaluator` when AI is enabled and has an API key.
- call `storage.update_opportunity_evaluation(result_id, normalized, build_opportunity_column_updates(normalized))`.
- if evaluator fails, keep the row and call `storage.update_opportunity_evaluation(result_id, {}, {}, error=str(exc)[:200])`.

- [ ] **Step 5: Update monitor core**

Modify `src/monitor_core.py`:

- add `keyword_library: list[dict] | None = None` to `MonitorCore.__init__`
- derive `self.keywords` from `derive_search_keywords(keyword_library)` when `keyword_library` is supplied
- remove `AIGuard` initialization and `check_relevance` calls from `run_once`
- keep `KeywordMatcher` for evidence/notification candidate matching only
- pass `keyword_library` and `matched_keywords` into `enrich_new_bid`
- never call `storage.update_review` because AI suggested non-follow
- notification can remain keyword-based in this task; if using opportunity suggestion, it must not affect storage.

- [ ] **Step 6: Run integration tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_ai_extractor.py tests/test_monitor_core_ai_extraction.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

Run:

```bash
git add src/results/ai_extractor.py src/monitor_core.py tests/test_ai_extractor.py tests/test_monitor_core_ai_extraction.py
git commit -m "feat: evaluate opportunities after storage"
```

## Task 8: Desktop GUI Keyword Library

**Parallel safety:** Phase 2. Exclusive lock on `src/gui.py`. Can run in parallel with Task 5 or Task 7.

**Files:**
- Modify: `src/gui.py`
- Create: `tests/test_gui_keyword_library.py`

**Interfaces:**
- Consumes from Task 1:
  - `normalize_keyword_library`
  - `derive_legacy_keywords`
  - `derive_search_keywords`
  - `parse_keyword_library_text`
  - `merge_keyword_library`
- Produces: GUI config load/save/run uses `keyword_library`.

- [ ] **Step 1: Write failing GUI source/config tests**

Create `tests/test_gui_keyword_library.py`:

```python
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_PATH = os.path.join(ROOT, "src", "gui.py")


class GuiKeywordLibraryTests(unittest.TestCase):
    def read_gui(self):
        with open(GUI_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_gui_imports_keyword_library_helpers(self):
        source = self.read_gui()
        self.assertIn("normalize_keyword_library", source)
        self.assertIn("derive_legacy_keywords", source)
        self.assertIn("derive_search_keywords", source)
        self.assertIn("parse_keyword_library_text", source)

    def test_gui_search_config_uses_keyword_library_table_hooks(self):
        source = self.read_gui()
        for marker in [
            "keyword_library",
            "keyword_tree",
            "_render_keyword_library",
            "_add_keyword_rule",
            "_delete_keyword_rules",
            "_import_keyword_library",
            "_export_keyword_library",
        ]:
            self.assertIn(marker, source)
        self.assertNotIn('text="关注关键词 (逗号分隔):"', source)
        self.assertNotIn('text="排除关键词 (逗号分隔):"', source)
        self.assertNotIn('text="必须包含 (产品词):"', source)

    def test_gui_save_config_writes_keyword_library_and_derived_keywords(self):
        source = self.read_gui()
        save_match = re.search(r"def _save_config\\(self\\):(?P<body>.*?)(?:\\n    def |\\Z)", source, re.S)
        self.assertIsNotNone(save_match)
        body = save_match.group("body")
        self.assertIn("'keyword_library'", body)
        self.assertIn("derive_legacy_keywords", body)
        self.assertNotIn("'keywords': self.keywords_var.get()", body)

    def test_gui_crawl_uses_derived_search_keywords(self):
        source = self.read_gui()
        crawl_match = re.search(r"def _do_crawl\\(self\\):(?P<body>.*?)(?:\\n    def |\\Z)", source, re.S)
        self.assertIsNotNone(crawl_match)
        body = crawl_match.group("body")
        self.assertIn("derive_search_keywords", body)
        self.assertIn("keyword_library=", body)
        self.assertNotIn("self.must_contain_var.get().split", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run GUI tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest tests/test_gui_keyword_library.py -q
```

Expected: FAIL because GUI still uses legacy variables.

- [ ] **Step 3: Add imports and state**

Modify `src/gui.py` imports:

```python
try:
    from results.keyword_library import (
        derive_legacy_keywords,
        derive_search_keywords,
        keyword_library_directions,
        merge_keyword_library,
        normalize_keyword_library,
        parse_keyword_library_text,
    )
except ImportError:
    from src.results.keyword_library import (
        derive_legacy_keywords,
        derive_search_keywords,
        keyword_library_directions,
        merge_keyword_library,
        normalize_keyword_library,
        parse_keyword_library_text,
    )
```

Add `self.keyword_library = normalize_keyword_library(None, self.DEFAULT_KEYWORDS)` during initialization before UI rendering.

- [ ] **Step 4: Replace search config UI**

In the search configuration frame:

- remove keyword/exclude/must contain labels and entries
- add a direction filter combobox
- add `ttk.Treeview` named `self.keyword_tree`
- add buttons for add, delete, enable, disable, import, export
- implement helper methods:

```python
def _render_keyword_library(self):
    self.keyword_tree.delete(*self.keyword_tree.get_children())
    for row in self.keyword_library:
        self.keyword_tree.insert(
            "",
            tk.END,
            iid=row["id"],
            values=(
                "是" if row.get("enabled", True) else "否",
                row.get("business_direction", ""),
                row.get("sub_category", ""),
                row.get("keyword", ""),
                ", ".join(row.get("synonyms") or []),
                row.get("match_scope", "title_content"),
                row.get("note", ""),
            ),
        )

def _add_keyword_rule(self):
    keyword = simpledialog.askstring("新增关键词", "关键词")
    if keyword:
        self.keyword_library.append({
            "id": f"gui-{uuid.uuid4().hex[:8]}",
            "enabled": True,
            "business_direction": "基础弱电 / 智能化工程",
            "sub_category": "",
            "keyword": keyword.strip(),
            "synonyms": [],
            "match_scope": "title_content",
            "note": "",
        })
        self._render_keyword_library()

def _delete_keyword_rules(self):
    selected = set(self.keyword_tree.selection())
    self.keyword_library = [row for row in self.keyword_library if row["id"] not in selected]
    self._render_keyword_library()

def _set_selected_keyword_rules_enabled(self, enabled):
    selected = set(self.keyword_tree.selection())
    for row in self.keyword_library:
        if row["id"] in selected:
            row["enabled"] = bool(enabled)
    self._render_keyword_library()

def _import_keyword_library(self):
    text = simpledialog.askstring("导入关键词库", "粘贴 TSV/CSV 内容")
    if text:
        parsed = parse_keyword_library_text(text)
        self.keyword_library = merge_keyword_library(self.keyword_library, parsed["rows"])
        self._render_keyword_library()

def _export_keyword_library(self):
    lines = ["business_direction\tsub_category\tkeyword\tsynonyms\tmatch_scope\tnote\tenabled"]
    for row in self.keyword_library:
        lines.append("\t".join([
            row.get("business_direction", ""),
            row.get("sub_category", ""),
            row.get("keyword", ""),
            ", ".join(row.get("synonyms") or []),
            row.get("match_scope", "title_content"),
            row.get("note", ""),
            "true" if row.get("enabled", True) else "false",
        ]))
    self.root.clipboard_clear()
    self.root.clipboard_append("\n".join(lines))
```

For editing, use existing Tkinter dialogs or simple `simpledialog.askstring` fields. The minimum accepted implementation is row-level add/edit through dialogs plus table display.

- [ ] **Step 5: Update GUI config load/save/run**

Modify `_load_config`:

```python
self.keyword_library = normalize_keyword_library(config.get("keyword_library"), config.get("keywords", self.DEFAULT_KEYWORDS))
if hasattr(self, "keyword_tree"):
    self._render_keyword_library()
```

Modify `_save_config`:

```python
"keyword_library": self.keyword_library,
"keywords": derive_legacy_keywords(self.keyword_library),
"exclude": config.get("exclude", ""),
"must_contain": config.get("must_contain", ""),
```

Modify `_do_crawl`:

```python
keywords = derive_search_keywords(self.keyword_library)
core = MonitorCore(
    keywords=keywords,
    keyword_library=self.keyword_library,
    exclude_keywords=[],
    must_contain_keywords=[],
    notify_method=None,
    email="",
    phone="",
    log_callback=lambda msg: self.queue_log(msg),
    ai_config=ai_config,
)
```

- [ ] **Step 6: Run GUI tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest tests/test_gui_keyword_library.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 8**

Run:

```bash
git add src/gui.py tests/test_gui_keyword_library.py
git commit -m "feat: add desktop keyword library management"
```

## Task 9: Final Integration, Regression, and Documentation

**Parallel safety:** Serial final task. Run after all feature tasks are reviewed.

**Files:**
- Modify: `README.md`
- Modify: any tests needed for cross-task integration discovered during this task.

**Interfaces:**
- Consumes all previous tasks.
- Produces final verified branch.

- [ ] **Step 1: Write or update final acceptance tests if gaps remain**

Scan the spec and test list. If any acceptance criterion lacks coverage, add a focused test to the nearest existing test file. Required coverage must include:

- AI `不建议跟进` rows are still saved.
- Web search config does not expose legacy textarea-only workflow.
- Desktop GUI does not expose legacy keyword-only workflow.
- Results API sorting uses manual priority then score.

- [ ] **Step 2: Update README wording**

Modify `README.md` feature sections:

- replace “AI 智能过滤” as the main value proposition with “AI 机会评估”
- replace “关键词配置” text boxes with “结构化关键词库”
- state that AI does not block storage

- [ ] **Step 3: Run focused suites**

Run:

```bash
PYTHONPATH=. pytest tests/test_keyword_library.py tests/test_server_keyword_library_api.py tests/test_storage_results_center.py tests/test_opportunity_evaluator.py tests/test_result_review.py tests/test_server_results_api.py tests/test_ai_extractor.py tests/test_monitor_core_ai_extraction.py tests/test_static_frontend_assets.py tests/test_gui_keyword_library.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full suite**

Run:

```bash
PYTHONPATH=. pytest -q
```

Expected: PASS.

- [ ] **Step 5: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit final cleanup**

Run:

```bash
git add README.md tests
git commit -m "docs: update opportunity evaluation workflow"
```

If there are no documentation or test changes after verification, do not create an empty commit.

## Final Review Requirement

After Task 9:

1. Run a final whole-branch code review using `superpowers:requesting-code-review`.
2. The review package must cover the merge base through HEAD.
3. Fix all Critical and Important findings in one fix task.
4. Re-run focused tests for fixes and then `PYTHONPATH=. pytest -q`.
5. Use `superpowers:finishing-a-development-branch` after the final review is clean.
