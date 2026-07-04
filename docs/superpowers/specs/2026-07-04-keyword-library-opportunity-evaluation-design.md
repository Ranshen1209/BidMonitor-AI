# Keyword Library and Opportunity Evaluation Design

## Goal

Restructure BidMonitor-AI from mixed keyword text boxes and AI filtering semantics into a unified keyword library plus AI opportunity evaluation workflow.

The system must store every crawled procurement notice that passes crawler-level notice parsing. AI may enrich, evaluate, rank, and support notifications, but it must not block database insertion.

## Scope

Included:

- Make structured `keyword_library` the primary search configuration model.
- Replace Web search keyword textarea controls with a spreadsheet-like keyword library manager.
- Update the existing Tkinter desktop GUI in `src/gui.py` so it also manages the structured keyword library rather than only comma-separated keyword inputs.
- Keep legacy `keywords`, `exclude`, and `must_contain` as migration inputs and compatibility-derived fields.
- Add AI opportunity evaluation as a separate module, not part of `KeywordMatcher`.
- Store AI opportunity fields and human opportunity review fields in SQLite with migration compatibility for existing databases.
- Extend results APIs for opportunity filters, details, sorting, and human review.
- Update Web result list and detail panel to show opportunity evaluation, matched keyword evidence, risk, and human corrections.
- Ensure tests cover keyword defaults/import/API, AI JSON parsing, storage migration, result API fields and sorting, opportunity review saves, static frontend contracts, and desktop GUI keyword-library compatibility.

Excluded from this design:

- Rewriting crawler site adapters beyond feeding them derived search keywords.
- Introducing a separate full CRM pipeline.
- Removing historical modules only for cleanup if they are not in the active path.
- Network calls in tests.

## Non-Negotiable Constraints

- Every crawled notice that the crawler emits as a valid bid result is saved before AI evaluation.
- AI cannot be an insertion gate.
- Keyword library entries support search, match evidence, UI management, and AI business context; they do not directly determine final opportunity score.
- Final score is produced by AI from title, summary/content, detail text, procurement stage, region, owner, amount, deadlines, and project content.
- `KeywordMatcher` remains a lightweight matching/evidence helper only. No complex scoring logic goes into it.
- Human users can correct AI suggestion, manual priority, business direction, region, stage, amount band, owner type, follow decision, and notes.
- Default result sorting is manual priority first, AI score second, then publish or insertion time.

## Chosen Architecture

Use a clean replacement architecture with compatibility edges.

`keyword_library` becomes the main configuration shape shared by Web, desktop GUI, monitor core, and AI opportunity evaluation. Legacy keyword strings are still accepted when loading old config files, then normalized into default or migrated keyword library entries.

AI opportunity evaluation is handled by a new `src/results/opportunity_evaluator.py` module. It is separate from both `src/matcher/keyword.py` and the existing `src/results/ai_extractor.py`. Field extraction and opportunity evaluation can share HTTP endpoint mechanics, but they must remain separate conceptual operations:

- `AIExtractor`: extracts procurement fields such as organization, amount, region, and deadlines.
- `OpportunityEvaluator`: evaluates business opportunity, score, reasons, risks, and review metadata.
- `KeywordMatcher`: finds keyword evidence and notification candidates.

The old `AIGuard` filtering semantics are removed from the insertion path. If the module remains for compatibility, it must be a wrapper or deprecated helper and must not decide whether a result is saved.

## Keyword Library Model

Each keyword rule has:

- `id`
- `enabled`
- `business_direction`
- `sub_category`
- `keyword`
- `synonyms`
- `match_scope`: `title`, `content`, or `title_content`
- `note`

`synonyms` is normalized internally as a list of strings. API and UI may accept a comma-separated string for convenient editing and import.

Default keyword library entries must cover these business directions:

- 音视频会议
- 显示大屏与指挥中心
- AI 视频与智能分析
- 基础弱电 / 智能化工程
- 安防监控
- 门禁一卡通
- 综合布线 / 网络 / 机房
- 可做杂项

The default terms below are not exclusion terms. They tell crawlers what to search, provide match evidence, and give the AI business context.

### Default Keyword Library Contents

The implementation must seed these enabled rows. Each bullet is one business direction. Implementations may store each term as a separate row or split terms into main keywords plus synonyms, but every term below must be searchable and available to the AI business dictionary.

音视频会议:

`音视频`, `音视频系统`, `会议系统`, `视频会议`, `会议室`, `无纸化会议`, `会议扩声`, `会议音响`, `会议摄像机`, `会议终端`, `会议平板`, `会议一体机`, `智能会议室`, `多功能厅`, `报告厅`, `阶梯教室`, `录播教室`, `录播系统`, `精品录播`, `常态化录播`, `扩声系统`, `音频系统`, `调音台`, `功放`, `音箱`, `麦克风`, `无线话筒`, `鹅颈话筒`, `中控系统`, `矩阵切换器`, `视频矩阵`, `分布式坐席`, `分布式系统`, `同声传译`, `远程会议`, `智慧会议`, `会议预约`, `会议管理平台`

显示大屏与指挥中心:

`大屏`, `LED显示屏`, `LCD拼接屏`, `液晶拼接屏`, `DLP大屏`, `显示系统`, `可视化大屏`, `指挥中心`, `调度中心`, `应急指挥`, `作战指挥`, `融媒体中心`, `监控中心`, `值班室`, `控制室`, `可视化平台`, `信息发布屏`, `信息发布系统`, `触控一体机`, `电子班牌`, `导览屏`, `数字标牌`

AI 视频与智能分析:

`AI视频`, `AI 视频`, `智能视频分析`, `视频智能分析`, `视频结构化`, `行为分析`, `周界识别`, `人脸识别`, `车辆识别`, `算法平台`, `视觉识别`, `视频算法`, `智能预警`, `智能监管`, `AI监管`, `AI管理平台`, `AI 管理平台`, `智能管理平台`, `智慧监管平台`, `视频联网平台`, `视频汇聚平台`, `视频云平台`, `安防智能化`, `图像识别`, `客流分析`, `人员轨迹`, `异常行为识别`

基础弱电 / 智能化工程:

`弱电`, `弱电工程`, `基础弱电`, `智能化`, `建筑智能化`, `楼宇智能化`, `智能化工程`, `智能化系统`, `信息化`, `信息化建设`, `信息化改造`, `智慧校园`, `智慧园区`, `智慧楼宇`, `智慧社区`, `系统集成`, `集成服务`, `工程改造`, `设备采购及安装`, `维保`, `运维`, `维修`, `改造`, `升级`, `扩容`

安防监控:

`安防`, `监控`, `视频监控`, `监控系统`, `监控改造`, `监控维保`, `摄像头`, `摄像机`, `枪机`, `球机`, `半球`, `硬盘录像机`, `NVR`, `DVR`, `存储服务器`, `安防平台`, `安防系统`, `电子围栏`, `周界报警`, `入侵报警`, `一键报警`, `报警系统`, `巡更系统`, `访客系统`

门禁一卡通:

`门禁`, `门禁系统`, `门禁改造`, `人脸门禁`, `刷卡门禁`, `闸机`, `通道闸`, `翼闸`, `摆闸`, `速通门`, `一卡通`, `校园一卡通`, `消费系统`, `考勤系统`, `访客预约`, `出入口管理`, `车辆道闸`, `停车场系统`, `车牌识别`

综合布线 / 网络 / 机房:

`综合布线`, `网络布线`, `弱电布线`, `光纤`, `网线`, `桥架`, `机柜`, `配线架`, `信息点`, `网络改造`, `无线网络`, `WiFi`, `无线覆盖`, `AP`, `交换机`, `路由器`, `防火墙`, `网络设备`, `机房`, `数据中心`, `UPS`, `精密空调`, `机房改造`, `机房建设`, `服务器`, `存储`, `等保`, `网络安全`

可做杂项:

`消防`, `消防改造`, `消防报警`, `暖通`, `空调`, `装修`, `装修改造`, `强电`, `电力改造`, `配电`, `办公设备`, `电脑`, `打印机`, `扫描仪`, `耗材`, `线缆`, `软件开发`, `管理系统`, `平台建设`

### Legacy Compatibility

When loading config:

- If `keyword_library` exists and is a non-empty list, use it.
- If `keyword_library` is missing, build it from defaults plus legacy `keywords`.
- Legacy `exclude` and `must_contain` are retained in config for old callers, but the Web and desktop GUI no longer expose them as the primary workflow.
- Derived crawler search keywords are built from enabled keyword library rows, prioritizing unique main keywords and high-value business directions.

When saving config:

- Persist `keyword_library`.
- Also persist derived `keywords` for old desktop or script callers until those paths are fully retired.
- Do not persist AI scoring decisions into keyword library rows.

## Keyword Library APIs

Add or update:

- `GET /api/keyword-library`
- `POST /api/keyword-library`
- `POST /api/keyword-library/import`

`GET /api/keyword-library` returns normalized rows and available business directions.

`POST /api/keyword-library` replaces the normalized library after validating row shape, allowed scopes, required keyword text, and stable IDs.

`POST /api/keyword-library/import` accepts pasted TSV/CSV style text. It supports headers when present and falls back to the column order:

`business_direction, sub_category, keyword, synonyms, match_scope, note, enabled`

It returns parsed rows, rejected rows, and a merged preview or merged final result depending on payload mode.

Export is implemented in the browser using the `GET /api/keyword-library` response converted to TSV. No server export endpoint is required in the first implementation.

## Opportunity Evaluation Data Model

Add SQLite columns to `bids` with migration-safe defaults:

- `ai_suggestion`: text, one of `强烈跟进`, `建议跟进`, `观察待确认`, `不建议跟进`, or empty.
- `opportunity_score`: integer default `0`.
- `manual_priority`: text, one of `置顶`, `高`, `中`, `低`, `未设置`, `忽略`.
- `business_directions`: JSON list.
- `matched_keywords`: JSON object with `title`, `content`, `detail` arrays.
- `region_category`: text.
- `owner_type`: text.
- `owner_priority`: text.
- `amount_band`: text.
- `risk_flags`: JSON list.
- `score_breakdown`: JSON object.
- `ai_reason_summary`: text.
- `deadline_summary`: text.
- `opportunity_raw_evaluation`: JSON object containing the normalized parsed AI opportunity result.
- `manual_score_overrides`: JSON object.
- `opportunity_review_notes`: text.

Existing review fields remain for compatibility:

- `fit_status`
- `follow_decision`
- `urgency`
- `project_stage`
- `manual_overrides`
- `review_notes`

The new opportunity review API may update some existing fields where the concepts overlap, but it must preserve existing API behavior.

## Opportunity Evaluation JSON

`OpportunityEvaluator` requires the AI to return strict JSON only:

```json
{
  "ai_suggestion": "强烈跟进 | 建议跟进 | 观察待确认 | 不建议跟进",
  "score": 0,
  "business_directions": [],
  "matched_keywords": {
    "title": [],
    "content": [],
    "detail": []
  },
  "project_stage": "采购意向 | 预采购 | 预招标 | 正式公告 | 已过期 | 未知",
  "region_category": "上海市区 | 上海郊区 | 江苏 | 浙江 | 安徽 | 其它外地 | 上海业主外地项目 | 未知",
  "owner_name": "",
  "owner_type": "",
  "owner_priority": "第一优先级 | 第二优先级 | 第三优先级 | 未知",
  "amount": "",
  "amount_band": "未写金额 | 10万以下 | 10-50万 | 50-200万 | 200-500万 | 500-1000万 | 1000万以上 | 亿级",
  "deadline_summary": "",
  "risk_flags": [],
  "reason_summary": "",
  "score_breakdown": {
    "business": "",
    "region": "",
    "owner": "",
    "stage_time": "",
    "amount": "",
    "risk": ""
  }
}
```

Parsing rules:

- Reject missing or non-object responses.
- Accept fenced JSON only as a tolerance path, but the prompt still says JSON only.
- Clamp `score` to `0..100`.
- Normalize unknown enum values to safe unknown or empty defaults.
- Store the normalized parsed object in `opportunity_raw_evaluation`; table and filter fields must also be column-backed.

## Business Rules for AI Prompt

The opportunity prompt must include:

- Weak-current as the broad business pool.
- Shanghai plus good owner plus weak-current related is worth review.
- Shanghai city highest, Shanghai suburb high, Jiangsu/Zhejiang medium-high, Anhui medium, other outside regions low.
- Shanghai owner with outside project is a separate region category, not ordinary low-priority outside region.
- Owner priority tiers exactly as supplied: first priority schools/universities/public institutions/SOEs/public security/banks; second priority courts/prisons/government/hospitals/parks/research institutes/streets/communities/cultural venues/transport/metro/airport/central SOE subsidiaries; third priority private companies/property companies/integrators/agencies/unknown.
- Procurement intentions, pre-procurement, and pre-tender stages are highest because early intervention is valuable.
- Formal tenders remain important, but deadlines within 7 days lower priority slightly.
- Expired projects stay in storage with lowest priority.
- Missing date is `日期不明`, not an exclusion reason.
- Best amount range is 200-500 万.
- Unknown amount is not fatal.
- 500-1000 万 is valuable but carries qualification/delivery pressure.
- 1000 万以上 and 亿级 require human judgment and risk notes.

The prompt must explicitly say keyword matches are evidence and business dictionary context, not direct scoring rules.

## Monitor Flow

The new monitor flow is:

1. Load normalized keyword library.
2. Derive crawler search keywords from enabled rows.
3. Crawl enabled sources.
4. Save every valid `BidInfo` from crawlers if not duplicate.
5. Collect keyword evidence against title/content and, after detail fetch, detail text.
6. Fetch detail and run field extraction when configured.
7. Run opportunity evaluation when AI is enabled and credentials exist.
8. Store opportunity fields and evaluation status.
9. Determine notification candidates from manual/AI opportunity fields and existing policy, but never delete or hide stored rows.

If AI is disabled or fails:

- The row remains visible.
- Opportunity fields remain empty/default.
- Status or error fields indicate evaluation was skipped or failed.

The previous behavior where AI rejection marked `fit_status=not_fit` may be replaced by storing `ai_suggestion=不建议跟进`. It must not mark the record as manually reviewed.

## Results APIs

Extend `GET /api/results` to include:

- `ai_suggestion`
- `opportunity_score`
- `manual_priority`
- `business_directions`
- `region_category`
- `project_stage`
- `owner_type`
- `owner_priority`
- `amount_band`
- `deadline_summary`
- `risk_flags`
- `ai_reason_summary`
- `follow_decision`
- existing extracted fields

Add filters:

- `ai_suggestion`
- `manual_priority`
- `business_direction`
- `region_category`
- `owner_type`
- `amount_band`
- `project_stage`

Default sort:

1. Manual priority: `置顶`, `高`, `中`, `低`, `未设置` or empty, `忽略`.
2. `opportunity_score` descending.
3. Publish date descending if parseable, otherwise `created_at` descending.

Extend `GET /api/results/{id}` with full opportunity evaluation details:

- matched keywords split by title/content/detail
- risk flags
- score breakdown
- raw AI parsed opportunity object if stored
- manual score overrides

Add:

- `PATCH /api/results/{id}/opportunity-review`

It saves human corrections for:

- AI suggestion correction
- manual priority
- business directions
- project stage
- region category
- owner type and owner priority
- amount band
- follow decision
- notes

Existing `/api/results/{id}/review` and `/api/results/{id}/fields` remain compatible.

## Web UI Design

### Search Configuration

The `page-sites` search configuration card becomes a keyword library workspace.

Required controls:

- Business direction filter.
- Compact toolbar for add row, delete selected, batch enable, batch disable, paste import, export, save.
- Spreadsheet-like table with row selection.
- Inline editable cells for enabled, business direction, sub-category, keyword, synonyms, match scope, and note.
- TSV/CSV paste import textarea or modal.
- Export current library as TSV.
- Interval and browser mode controls remain available but visually separated from keyword library management.

The old big keyword textarea must not be the primary search UI.

### Results List

Table columns become opportunity-centric:

- AI建议
- 人工优先级
- 评分
- 项目名称
- 业务方向
- 地区分类
- 项目阶段
- 业主类型
- 金额档位
- 截止摘要
- AI理由
- 人工决策
- 来源

Filters include AI suggestion, manual priority, business direction, region, owner type, amount band, and project stage.

The layout should stay dense and office-friendly. Do not turn the results center into a marketing page or decorative card grid.

### Result Detail

The detail panel adds:

- AI opportunity summary.
- Score and suggestion.
- Score breakdown for business, region, owner, stage/time, amount, and risk.
- Matched keywords grouped by title/content/detail.
- Risk flags.
- Manual opportunity correction controls.
- Existing field comparison and raw AI extraction JSON remain accessible.

## Desktop GUI Design

`src/gui.py` currently has legacy keyword entry controls. It must be updated so desktop users share the same `keyword_library` model.

Minimum desktop requirements:

- Load normalized keyword library from config.
- Display keyword rules in a table-like widget.
- Support add, edit, delete, enable, disable.
- Support business direction filtering.
- Support import/export through pasted or file-like TSV/CSV text if existing GUI patterns make file dialogs awkward.
- Save `keyword_library` and derived legacy `keywords`.
- Preserve existing monitor start/run behavior.

The desktop GUI does not need to perfectly match the Web UI visually, but it must not remain a plain comma-separated keyword entry as the only keyword-management path.

## Testing Strategy

Use TDD for implementation.

Backend tests:

- Keyword library defaults include all eight business directions and representative required terms.
- Legacy config migrates into normalized `keyword_library`.
- TSV/CSV import parses headers, no-header column order, enabled flags, synonyms, and rejects malformed rows.
- Keyword library API returns, saves, imports, and preserves derived legacy keywords.
- Storage migration adds opportunity columns to fresh and existing databases without losing rows.
- Opportunity JSON parser accepts valid strict JSON and rejects invalid response shapes.
- Opportunity column mapping stores enum-normalized fields and JSON fields.
- Results API returns opportunity fields.
- Results API filters by AI suggestion, manual priority, business direction, region category, owner type, amount band, and project stage.
- Results API default sorting follows manual priority, score, then date.
- Opportunity review API saves human corrections.
- Monitor saves AI rejected or `不建议跟进` records.

Frontend static tests:

- Search configuration page no longer exposes only the old keyword textarea.
- Keyword library table hooks, filters, import, export, batch enable/disable, and save functions exist.
- Results table contains AI suggestion, manual priority, score, reason, risk, and opportunity filters.
- Detail panel contains score breakdown, matched keyword groups, risk flags, and opportunity review controls.

Desktop GUI tests:

- Default GUI configuration reads normalized keyword library.
- Saving GUI config writes `keyword_library` and derived `keywords`.
- GUI source no longer relies solely on `keywords_var`, `exclude_var`, and `must_contain_var` for search configuration.

Full regression:

- Existing AI extraction, results center, monitor core, storage, auth, crawler, and static frontend tests continue to pass.

## Multi-Agent Implementation Constraints

The implementation plan must be written for subagent-driven development and parallel review.

### Dependency Phases

Phase 1 must be serial:

- Keyword library model and config normalization.
- Storage migration fields.
- Opportunity evaluator interfaces.

These define contracts consumed by later tasks.

Phase 2 may run in parallel after Phase 1:

- API endpoints and result serialization.
- Web keyword library UI.
- Web results opportunity UI.
- Desktop GUI keyword library UI.
- Opportunity evaluator prompt and parser tests.

Phase 3 must be serial integration:

- Monitor flow wiring.
- Notification semantics cleanup.
- Cross-surface regression fixes.
- Final full-suite verification.

### File Ownership Rules

To avoid agent conflicts:

- Only one task at a time may edit `src/database/storage.py`.
- Only one task at a time may edit `server/app.py`.
- Only one task at a time may edit `src/monitor_core.py`.
- Only one task at a time may edit `src/gui.py`.
- Web HTML/CSS/JS tasks may be split only if one owns keyword-library UI and another owns results UI, with explicit non-overlapping sections in `server/static/index.html`, `server/static/app.js`, and `server/static/styles.css`.
- Shared constants and schemas should live in new focused modules such as `src/results/keyword_library.py` and `src/results/opportunity_evaluator.py` so parallel tasks can consume stable interfaces instead of editing the same large files.

### Agent Task Shape

Each task in the implementation plan must include:

- Exact files owned by that task.
- Interfaces produced and consumed.
- Tests to write before implementation.
- Commands to prove the new tests fail first.
- Commands to prove the task passes.
- Whether the task is parallel-safe and which other tasks it can run beside.

Do not dispatch multiple implementation agents to edit the same file concurrently. Parallel agents may investigate or review independently, but write ownership must be explicit.

## Rollout and Migration

First run after upgrade:

- Existing config is normalized.
- Default keyword library is created if none exists.
- Legacy keyword strings are folded in as enabled entries under a migrated direction or preserved in derived fields.
- Existing bids receive default opportunity fields through schema migration.

Old results remain visible. Rows without opportunity evaluation sort after manually prioritized or scored rows unless they have manual priority.

## Acceptance Criteria

- Crawled results remain visible even when AI returns `不建议跟进`.
- Web search configuration is structured keyword library management, not a pile of mixed keywords in textarea controls.
- Desktop GUI also manages structured keyword library.
- Results list shows AI suggestion, score, reason, risk, manual priority, and follow decision.
- Result detail shows full AI score explanation, keyword evidence grouped by title/content/detail, risk flags, and manual opportunity correction fields.
- Humans can save opportunity corrections.
- Default sorting follows manual priority first, then AI score, then date.
- Old config and old data do not crash after migration.
- Tests cover the backend, Web static contracts, desktop config behavior, AI JSON parsing, storage migration, result APIs, and monitor insertion guarantee.
