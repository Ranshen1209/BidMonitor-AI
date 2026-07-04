# Crawl / AI Quality Fixes Handoff

日期：2026-07-04

## 当前状态

- 分支：`crawl-ai-quality-fixes`
- 隔离 worktree：`/home/qiming/BidMonitor-AI/.worktrees/crawl-ai-quality-fixes`
- 当前 HEAD：`2dc7b61 test: align url source fixture with detail evidence rules`
- main 分支未被修改；所有修复都在隔离 worktree 的 feature branch 上完成。
- 工作树在交接前是干净状态。

## 已完成范围

已按 `docs/superpowers/plans/2026-07-04-bidmonitor-crawl-ai-quality.md` 执行完 Tasks 1-12。

主要修复：

- URL 候选准入：过滤下载、附件、静态资源、模板变量、hash 登录页。
- 拓扑抓取：增加域名级熔断，严格拓扑详情正则，拒绝新闻/处罚/公司页/SPA 壳页。
- 详情准入：最小详情证据必须包含结构化采购字段。
- AIExtractor：增强 JSON 截取和 `deadlines` 容错。
- AIGuard：AI 请求失败、非标准 JSON、歧义 JSON/文本不再 fail-open；补齐正负向文本 fallback。
- 通知策略：新增 `crawler.notification_policy`，支持 `strict_keyword_and_ai`、`keyword_or_ai`、`keyword_only_on_ai_error`，并正确处理 AI 未运行、未知和异常。
- AI/详情成本控制：新增 `crawler.enrich_only_candidate_results`，低价值结果可跳过详情 enrichment。
- BFS 候选排序：详情页、强公告词、日期、业务词优先；负向栏目降权。
- 拓扑搜索：执行 topology `search` 配置，支持 GET/POST/GET_OR_POST；POST 请求保留 method/body 身份，不会退化为 browser GET；source adapter 请求计数修正。

## 关键提交

- `f1dfd7a` docs: plan crawl and ai quality repairs
- `bfc711e` / `8f22632` / `26ab899` URL shape rejection
- `a15062f` / `7c1350c` domain circuit breaker
- `1ea4ca5` / `3c554eb` / `d41383b` / `732adf6` strict topology detail regex
- `277f0b5` / `65f3ac7` / `4ce013e` / `8d8a405` non-announcement and shell rejection
- `71ce1e7` structured detail evidence requirement
- `fffac46` through `f69e482` AIExtractor JSON/deadline hardening
- `876131c` through `5de17e7`, plus `35ac646` AIGuard fail-closed / unknown handling
- `0045248` / `442940d` / `25af4b1` / `3825bc6` notification policy fixes
- `08f5509` / `d5db95b` candidate scoring
- `9454f33` / `3669080` / `ee10f22` topology GET/POST search execution and quality fixes
- `70aa9d2` enrichment gating
- `2dc7b61` URL source fixture alignment with strict detail evidence

## Review 状态

Subagent review 已完成：

- Task 7/8 AI + notification 最终 quality review：通过，无 Critical/Important。
- Task 9 spec review：通过。
- Task 10 spec review：通过；quality review 曾发现两个 Important，均已修复并复审通过。
- Task 11 spec review 和 quality review：通过，无 Critical/Important。

最后一次全分支 final reviewer 曾启动，但在上下文中断后不可用；交接前已用 full suite 和各任务 review 作为收口依据。新 Codex 如需合并前再保险，可重新派一个 final reviewer 审 `main...HEAD`。

## 验证记录

以下命令已在 worktree 中 fresh 跑过：

```bash
PYTHONPATH=. pytest tests/test_url_list_crawler.py tests/test_ai_extractor.py tests/test_ai_guard.py tests/test_monitor_core_ai_extraction.py tests/test_source_adapter.py -q
```

结果：

```text
156 passed, 1 skipped, 11 warnings, 64 subtests passed
```

```bash
PYTHONPATH=. pytest tests/test_url_list_crawler.py -q -k "download or circuit or topology or shell or evidence or scoring"
```

结果：

```text
37 passed, 40 deselected, 6 subtests passed
```

```bash
PYTHONPATH=. pytest tests/test_url_list_crawler.py tests/test_source_adapter.py tests/test_monitor_core_ai_extraction.py -q
```

结果：

```text
120 passed, 1 skipped, 2 warnings, 46 subtests passed
```

```bash
PYTHONPATH=. pytest -q
```

结果：

```text
317 passed, 2 skipped, 55 warnings, 82 subtests passed
```

```bash
git diff --check main...HEAD
```

结果：无输出。

Warnings 主要来自：

- `src/database/storage.py` 中 `datetime.utcnow()` 的 deprecation warning。
- 本地 HTTPS 测试的 urllib3 `InsecureRequestWarning`。

这些不是本轮修复引入的阻塞问题。

## 最后一次 full suite 失败及处理

`tests/test_monitor_core_url_sources.py::MonitorCoreUrlSourcesTests::test_monitor_core_run_once_saves_url_list_results_to_storage` 曾失败：

- 现象：`new_count` 为 0。
- 根因：Task 5 后详情准入要求结构化采购字段；旧测试 HTML 只有标题和正文，不再代表可入库公告详情。
- 修复：提交 `2dc7b61` 给测试 fixture 增加 `发布时间` 和 `采购单位`。
- 修复后该 test file 和 full suite 均通过。

## 已知注意事项

- `.worktrees/crawl-ai-quality-fixes` 是隔离 worktree，不要在 main 目录直接继续改同一批文件。
- root/main 工作区之前有一个未跟踪计划文件提示：`docs/superpowers/plans/2026-07-04-bidmonitor-crawl-ai-quality.md`。本分支内该计划文件已提交，新的 Codex 不应回滚 main 工作区里用户可能留下的未跟踪文件。
- 不要使用 `git reset --hard` 或 `git checkout --` 清理用户变更。
- 如果要继续使用 Subagent-Driven Development，先检查 worktree 状态，再派只读 review 或 scoped worker，避免多个 worker 同时写 `src/crawler/url_list.py`。

## 建议下一步

1. 确认远端分支已推送：

   ```bash
   git status --short --branch
   git log --oneline --decorate -5
   git branch -vv
   ```

2. 如需合并前再保险，重新运行：

   ```bash
   PYTHONPATH=. pytest -q
   ```

3. 可选：派 final reviewer 审：

   ```bash
   git diff main...HEAD
   ```

4. 若用户要合并：

   - 建议先开 PR：`crawl-ai-quality-fixes` -> `main`
   - 不要自动清理 worktree，PR review 可能还要迭代。

