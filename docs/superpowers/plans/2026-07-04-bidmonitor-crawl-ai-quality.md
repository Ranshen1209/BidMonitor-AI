# BidMonitor Crawl And AI Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce crawl time, bad URL traversal, false ingests, and AI extraction failures found in the July 4, 2026 crawl log review.

**Architecture:** Keep the existing `UrlListCrawler` topology crawler, but add three guard layers: URL-shape rejection before enqueue, topology-aware detail admission before save, and domain circuit breaking around repeated fetch failures. AI changes stay in `AIExtractor`, `AIGuard`, and `MonitorCore`, with conservative defaults and explicit notification policy.

**Tech Stack:** Python 3, `requests`, existing unittest/pytest test suite, SQLite storage layer, current crawler topology JSON.

---

## Scope And File Map

**P0 files:**
- Modify: `src/crawler/url_list.py`
- Modify: `src/results/ai_extractor.py`
- Modify: `src/ai_guard.py`
- Modify: `src/monitor_core.py`
- Test: `tests/test_url_list_crawler.py`
- Test: `tests/test_ai_extractor.py`
- Test: `tests/test_ai_guard.py`
- Test: `tests/test_monitor_core_ai_extraction.py`

**P1 files:**
- Modify: `src/crawler/url_list.py`
- Modify: `src/crawler/source_adapter.py`
- Modify: `src/results/ai_extractor.py`
- Modify: `src/monitor_core.py`
- Test: `tests/test_url_list_crawler.py`
- Test: `tests/test_source_adapter.py`
- Test: `tests/test_ai_extractor.py`
- Test: `tests/test_monitor_core_ai_extraction.py`

**Behavioral targets:**
- `bidchance` and other blocked domains stop after repeated 521/5xx/blocked responses in one run.
- `downloadFile`, attachment, binary, static asset, template-variable, and hash-login URLs do not enter topology queues.
- Sites with topology `detail_url_regex` no longer fall back to generic `.html` detail classification for same-topology hosts.
- Policy/news/penalty/company/SPA-shell pages are rejected before storage.
- `AIExtractor` tolerates JSON wrappers and malformed `deadlines`.
- AI relevance failures become `unknown`, not fail-open `relevant`, and notification behavior is policy-driven.

---

### Task 1: Add URL Shape Rejection Before Traversal

**Files:**
- Modify: `src/crawler/url_list.py:49-126`
- Modify: `src/crawler/url_list.py:1182-1325`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing tests for invalid candidate URLs**

Add these tests to `tests/test_url_list_crawler.py` inside `UrlListCrawlerTests`:

```python
    def test_rejects_download_static_template_and_hash_login_candidates(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )
        page_url = "https://portal.example.com/list"

        rejected = [
            "https://portal.example.com/file-web/downloadFile?id=abc",
            "https://portal.example.com/notice.docx",
            "https://portal.example.com/assets/app.css",
            "https://portal.example.com/${pingbiao.url}",
            "https://portal.example.com/#/login",
            "https://portal.example.com/login#/login",
        ]

        for candidate_url in rejected:
            with self.subTest(candidate_url=candidate_url):
                self.assertFalse(crawler._is_valid_traversal_url(candidate_url))
                self.assertFalse(crawler._should_follow_candidate(page_url, candidate_url, 0))

    def test_candidate_extraction_skips_invalid_url_shapes(self):
        crawler = self.make_crawler_with_source_config(
            "/tmp/missing.txt",
            None,
            {"topology_max_depth": 2},
        )
        html = (
            "<html><body>"
            "<a href='/file-web/downloadFile?id=abc'>招标文件下载</a>"
            "<a href='/assets/app.css'>采购样式</a>"
            "<a href='${pingbiao.url}'>采购公告模板</a>"
            "<a href='/#/login'>采购登录</a>"
            "<a href='/detail/1'>上海安防工程公开招标公告</a>"
            "</body></html>"
        )

        links = crawler._extract_candidate_links_from_html(html, "https://portal.example.com/list")

        self.assertEqual([link["url"] for link in links], ["https://portal.example.com/detail/1"])
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_download_static_template_and_hash_login_candidates tests/test_url_list_crawler.py::UrlListCrawlerTests::test_candidate_extraction_skips_invalid_url_shapes -q
```

Expected: FAIL because `_is_valid_traversal_url` does not exist and invalid candidates are currently allowed by some paths.

- [ ] **Step 3: Add rejection constants and helper**

In `src/crawler/url_list.py`, after `NEGATIVE_LINK_KEYWORDS`, add:

```python
STATIC_OR_BINARY_EXTENSIONS = {
    ".css", ".js", ".mjs", ".map", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".doc", ".docx", ".xls",
    ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z", ".tar", ".gz",
}

DOWNLOAD_PATH_TERMS = [
    "download",
    "downloadfile",
    "file-web",
    "attachment",
    "attach",
    "enclosure",
    "export",
]

HASH_LOGIN_TERMS = ["#/login", "#/signin", "#/auth", "#/user/login"]
```

Add this method to `UrlListCrawler` before `_is_traversal_link`:

```python
    def _is_valid_traversal_url(self, url: str) -> bool:
        if not url:
            return False
        if "{" in url or "}" in url or "${" in url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        lowered_full = url.lower()
        if any(term in lowered_full for term in HASH_LOGIN_TERMS):
            return False
        path_lower = parsed.path.lower()
        query_lower = parsed.query.lower()
        _, ext = os.path.splitext(path_lower.rstrip("/"))
        if ext in STATIC_OR_BINARY_EXTENSIONS:
            return False
        path_and_query = f"{path_lower}?{query_lower}"
        if any(term in path_and_query for term in DOWNLOAD_PATH_TERMS):
            return False
        return True
```

- [ ] **Step 4: Wire helper into candidate extraction and follow checks**

In `_extract_candidate_links_from_html`, after `full_url = urljoin(page_url, href)`, add:

```python
            if not self._is_valid_traversal_url(full_url):
                continue
```

In `_extract_topology_attribute_links`, after `full_url = urljoin(page_url, raw_url)`, add:

```python
            if not self._is_valid_traversal_url(full_url):
                continue
```

In `_is_traversal_link`, add at the top:

```python
        if not self._is_valid_traversal_url(url):
            return False
```

In `_should_follow_candidate`, replace the scheme check block with:

```python
        if not self._is_valid_traversal_url(candidate_url):
            return False
        parsed = urlparse(candidate_url)
        current = urlparse(page_url)
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_download_static_template_and_hash_login_candidates tests/test_url_list_crawler.py::UrlListCrawlerTests::test_candidate_extraction_skips_invalid_url_shapes -q
```

Expected: PASS.

- [ ] **Step 6: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: reject invalid traversal urls"
```

---

### Task 2: Add Per-Domain Topology Circuit Breaker

**Files:**
- Modify: `src/crawler/url_list.py:322-360`
- Modify: `src/crawler/url_list.py:686-829`
- Modify: `src/crawler/url_list.py:831-853`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing tests for 521 circuit breaking**

Add this test to `tests/test_url_list_crawler.py`:

```python
    @patch.object(UrlListCrawler, "_request_url")
    def test_topology_circuit_breaker_stops_repeated_521_domain_failures(self, mock_request_url):
        requested = []

        def fake_request(url):
            requested.append(url)
            return ("blocked", 521, "Origin Down")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://blocked.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "blocked",
                        "name": "Blocked Example",
                        "entry_url": "https://blocked.example.com/",
                        "allowed_hosts": ["blocked.example.com"],
                        "seed_urls": [
                            "https://blocked.example.com/list-1.html",
                            "https://blocked.example.com/list-2.html",
                            "https://blocked.example.com/list-3.html",
                            "https://blocked.example.com/list-4.html",
                        ],
                        "list_url_regex": [r"/list-\d+\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {
                    "topology_max_depth": 1,
                    "max_follow_links_per_page": 10,
                    "domain_failure_threshold": 2,
                },
                config={"site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

        self.assertEqual(bids, [])
        self.assertLessEqual(len(requested), 3)
        self.assertTrue(crawler._is_domain_circuit_open("blocked.example.com"))
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_circuit_breaker_stops_repeated_521_domain_failures -q
```

Expected: FAIL because `_is_domain_circuit_open` and failure threshold behavior do not exist.

- [ ] **Step 3: Add state in `__init__`**

In `UrlListCrawler.__init__`, after `_last_domain_request_at`, add:

```python
        self.domain_failure_threshold = int(
            source_config.get("domain_failure_threshold", config.get("domain_failure_threshold", 3))
        )
        self._domain_failure_counts: Dict[str, int] = {}
        self._domain_circuit_open: set[str] = set()
        self._domain_failure_lock = threading.Lock()
```

- [ ] **Step 4: Add circuit breaker helpers**

Add these methods near `_respect_rate_limit`:

```python
    def _domain_key(self, url: str) -> str:
        return urlparse(url).netloc.lower().split(":")[0]

    def _is_domain_circuit_open(self, host_or_url: str) -> bool:
        host = self._domain_key(host_or_url) if "://" in host_or_url else host_or_url.lower().split(":")[0]
        if not host:
            return False
        with self._domain_failure_lock:
            return host in self._domain_circuit_open

    def _record_domain_fetch_success(self, url: str) -> None:
        host = self._domain_key(url)
        if not host:
            return
        with self._domain_failure_lock:
            self._domain_failure_counts.pop(host, None)

    def _record_domain_fetch_failure(self, url: str, reason: str, status_code: int = 0) -> None:
        host = self._domain_key(url)
        if not host:
            return
        blocked_failure = status_code in {403, 429, 521, 522, 523, 524} or status_code >= 500
        blocked_failure = blocked_failure or any(term in reason.lower() for term in ["timeout", "blocked", "captcha", "origin down"])
        if not blocked_failure:
            return
        with self._domain_failure_lock:
            count = self._domain_failure_counts.get(host, 0) + 1
            self._domain_failure_counts[host] = count
            if count >= self.domain_failure_threshold:
                self._domain_circuit_open.add(host)
                self._emit_info(f"[URL熔断] {self.name}: {host} 连续失败 {count} 次，本轮跳过后续同域请求")
```

- [ ] **Step 5: Wire circuit breaker into topology fetch loop**

In `_crawl_topology_from_url`, after computing `normalized_url` and before adding to `visited`, add:

```python
            if self._is_domain_circuit_open(page_url):
                self._record_diagnostic(
                    page_url,
                    "failed",
                    "domain circuit open after repeated fetch failures",
                    timestamp,
                    cookie_used=cookie_used,
                    rule=self._classify_url(page_url),
                )
                continue
```

After successful non-blocked fetch, before parsing:

```python
                self._record_domain_fetch_success(page_url)
```

In `_record_topology_fetch_failure`, after callback handling, add:

```python
        self._record_domain_fetch_failure(page_url, reason, status_code=status_code)
```

- [ ] **Step 6: Run focused test**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_circuit_breaker_stops_repeated_521_domain_failures -q
```

Expected: PASS.

- [ ] **Step 7: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: stop repeated blocked domain fetches"
```

---

### Task 3: Make Topology Detail Regex Strict On Known Sites

**Files:**
- Modify: `src/crawler/url_list.py:888-938`
- Modify: `src/crawler/url_list.py:1521-1537`
- Modify: `src/crawler/url_list.py:1547-1574`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing tests for strict topology classification**

Add these tests to `tests/test_url_list_crawler.py`:

```python
    def test_topology_detail_regex_blocks_generic_html_fallback_on_same_topology_host(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://www.bidchance.test/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "bidchance-test",
                        "name": "招标网测试",
                        "entry_url": "https://www.bidchance.test/",
                        "allowed_hosts": ["www.bidchance.test", "chance.bidchance.test"],
                        "detail_url_regex": [r"^https://www\.bidchance\.test/info-gonggao-[A-Za-z0-9]+\.html$"],
                        "list_url_regex": [r"/outlinegonggao\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            self.assertEqual(
                crawler._classify_url("https://www.bidchance.test/info-gonggao-ABC.html")["page_type"],
                "detail",
            )
            self.assertNotEqual(
                crawler._classify_url("https://chance.bidchance.test/company-123.html")["page_type"],
                "detail",
            )

    def test_topology_strict_mode_keeps_unknown_external_hosts_generic(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertEqual(crawler._classify_url("https://unknown.example.com/news-1.html")["page_type"], "detail")
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_detail_regex_blocks_generic_html_fallback_on_same_topology_host tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_strict_mode_keeps_unknown_external_hosts_generic -q
```

Expected: first test FAILS because `company-123.html` is still classified as `detail`; second test PASSES.

- [ ] **Step 3: Add strict helper**

Add this method after `_topology_for_url`:

```python
    def _topology_requires_strict_detail_urls(self, topology: Optional[Dict[str, Any]]) -> bool:
        if not topology:
            return False
        strict_value = topology.get("strict_detail_urls")
        if strict_value is not None:
            return bool(strict_value)
        return bool(topology.get("detail_url_regex"))
```

- [ ] **Step 4: Change `_classify_url` fallback behavior**

In `_classify_url`, replace the block after `topology_page_type = ...` with:

```python
        topology_page_type = self._classify_url_by_topology(url, topology)
        if topology_page_type:
            page_type = topology_page_type
        elif topology and self._topology_requires_strict_detail_urls(topology):
            if self._is_api_url(path, query):
                page_type = "api"
            elif self._is_login_url(path, query) or self._is_login_url(path, fragment):
                page_type = "login"
            elif self._is_search_url(path, query, fragment):
                page_type = "search"
            elif self._is_list_url(path):
                page_type = "list"
            elif path in ("", "/") or path.endswith("/index.html"):
                page_type = "home"
            else:
                page_type = "home"
        elif self._is_api_url(path, query):
            page_type = "api"
        elif self._is_login_url(path, query) or self._is_login_url(path, fragment):
            page_type = "login"
        elif self._is_detail_url(path, query):
            page_type = "detail"
        elif self._is_search_url(path, query, fragment):
            page_type = "search"
        elif self._is_list_url(path):
            page_type = "list"
        elif path in ("", "/") or path.endswith("/index.html"):
            page_type = "home"
        else:
            page_type = "home"
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_detail_regex_blocks_generic_html_fallback_on_same_topology_host tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_strict_mode_keeps_unknown_external_hosts_generic -q
```

Expected: PASS.

- [ ] **Step 6: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: enforce topology detail url patterns"
```

---

### Task 4: Reject Known Non-Announcement Pages And SPA Shells

**Files:**
- Modify: `src/crawler/url_list.py:49-126`
- Modify: `src/crawler/url_list.py:1327-1412`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing tests for site-specific bad pages**

Add these tests to `tests/test_url_list_crawler.py`:

```python
    def test_rejects_known_non_announcement_urls(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        rejected = [
            "https://www.chinabidding.com/infoDetail/123-News.html",
            "https://www.plap.mil.cn/freecms/site/juncai/dishonesty.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/suspended.html?id=1",
            "https://www.plap.mil.cn/freecms/site/juncai/warning.html?id=1",
            "https://chance.bidchance.com/company-123.html",
        ]

        for url in rejected:
            with self.subTest(url=url):
                self.assertTrue(crawler._is_known_non_announcement_url(url))

    def test_rejects_platform_shell_title_without_structured_fields(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})
        bid = type(
            "Bid",
            (),
            {
                "title": "国投集团电子采购平台",
                "content": "国投集团电子采购平台 招标公告 项目 服务",
            },
        )()

        self.assertFalse(
            crawler._is_admissible_detail_bid(
                bid,
                "https://www.sdicc.com.cn/cgxx/ggDetail?gcGuid=gc&ggGuid=gg",
            )
        )
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_known_non_announcement_urls tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_platform_shell_title_without_structured_fields -q
```

Expected: FAIL because `_is_known_non_announcement_url` does not exist and shell pages can pass minimal evidence.

- [ ] **Step 3: Add non-announcement URL helper**

Add these constants near URL rejection constants:

```python
NON_ANNOUNCEMENT_URL_PATTERNS = [
    r"chinabidding\.com/.+[-/]News\.html(?:$|\?)",
    r"plap\.mil\.cn/.+/(dishonesty|suspended|warning)\.html(?:$|\?)",
    r"bidchance\.com/company[-/][^?#]+\.html(?:$|\?)",
]

PLATFORM_SHELL_TITLES = {
    "国投集团电子采购平台",
    "中国招标网",
    "军队采购网",
}
```

Add this method before `_is_admissible_detail_bid`:

```python
    def _is_known_non_announcement_url(self, url: str) -> bool:
        return self._matches_any_pattern(url, NON_ANNOUNCEMENT_URL_PATTERNS)
```

- [ ] **Step 4: Wire URL helper into classification and admission**

In `_classify_url`, after `platform`, `handling`, and `reason` have been initialized and before `topology_page_type = self._classify_url_by_topology(url, topology)`, add:

```python
        if self._is_known_non_announcement_url(url):
            return {
                "platform": platform,
                "page_type": "home",
                "handling": "non_announcement",
                "reason": "已知非公告页面，跳过详情入库",
                "topology_id": str(topology.get("id", "")) if topology else "",
            }
```

At the top of `_is_admissible_detail_bid`, after `text = ...`, add:

```python
        if self._is_known_non_announcement_url(page_url):
            return False
        if self._looks_like_platform_shell(bid.title, text):
            return False
```

Add this method before `_has_detail_evidence`:

```python
    def _looks_like_platform_shell(self, title: str, text: str) -> bool:
        normalized_title = self._normalize_space(title)
        if normalized_title not in PLATFORM_SHELL_TITLES:
            return False
        return not self._has_structured_procurement_field(text)

    def _has_structured_procurement_field(self, text: str) -> bool:
        structured_fields = [
            "发布时间",
            "发布日期",
            "采购单位",
            "采购人",
            "招标人",
            "项目编号",
            "项目名称",
            "预算金额",
            "最高限价",
            "投标截止",
            "开标时间",
        ]
        return any(field in text for field in structured_fields)
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_known_non_announcement_urls tests/test_url_list_crawler.py::UrlListCrawlerTests::test_rejects_platform_shell_title_without_structured_fields -q
```

Expected: PASS.

- [ ] **Step 6: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: reject non-announcement detail pages"
```

---

### Task 5: Tighten Detail Evidence For Minimal Admission

**Files:**
- Modify: `src/crawler/url_list.py:1369-1412`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing tests for minimal evidence**

Add these tests to `tests/test_url_list_crawler.py`:

```python
    def test_minimal_detail_evidence_requires_structured_procurement_field(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertFalse(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 本项目采购安防监控系统服务",
                allow_minimal=True,
            )
        )
        self.assertTrue(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 发布时间：2026-07-02 本项目采购安防监控系统服务",
                allow_minimal=True,
            )
        )

    def test_full_detail_evidence_still_accepts_two_structured_fields(self):
        crawler = self.make_crawler_with_source_config("/tmp/missing.txt", None, {})

        self.assertTrue(
            crawler._has_detail_evidence(
                "上海安防工程招标公告 发布时间：2026-07-02 采购单位：上海测试单位",
                allow_minimal=False,
            )
        )
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_minimal_detail_evidence_requires_structured_procurement_field tests/test_url_list_crawler.py::UrlListCrawlerTests::test_full_detail_evidence_still_accepts_two_structured_fields -q
```

Expected: first test FAILS because minimal evidence currently accepts stage plus subject with no structured field.

- [ ] **Step 3: Update `_has_detail_evidence` minimal branch**

Replace the final return in `_has_detail_evidence`:

```python
        return stage_signal and subject_signal and len(text) >= 12
```

with:

```python
        return stage_signal and subject_signal and self._has_structured_procurement_field(text) and len(text) >= 12
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_minimal_detail_evidence_requires_structured_procurement_field tests/test_url_list_crawler.py::UrlListCrawlerTests::test_full_detail_evidence_still_accepts_two_structured_fields -q
```

Expected: PASS.

- [ ] **Step 5: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: require structured fields for detail admission"
```

---

### Task 6: Make AIExtractor JSON And Deadline Parsing Robust

**Files:**
- Modify: `src/results/ai_extractor.py:62-75`
- Modify: `src/results/ai_extractor.py:145-170`
- Modify: `src/results/ai_extractor.py:184-204`
- Test: `tests/test_ai_extractor.py`

- [ ] **Step 1: Write failing tests for JSON snippets and deadline coercion**

Add these tests to `tests/test_ai_extractor.py`:

```python
    def test_parse_json_text_extracts_object_from_wrapped_response(self):
        text = "以下是提取结果：\n{\"region\":\"上海\",\"deadlines\":[]}\n请查收"

        data = AIExtractor({})._parse_json_text(text)

        self.assertEqual(data["region"], "上海")

    def test_deadline_helpers_ignore_non_dict_deadline_items(self):
        data = {
            "region": "上海",
            "deadlines": [
                "2026-07-04 10:00",
                {"type": "submission_deadline", "end_at": "2026-07-05 10:00"},
            ],
        }

        columns = build_column_updates(data)
        urgency = suggest_urgency(data, now=datetime(2026, 7, 2, 9, 0))

        self.assertEqual(columns["submission_deadline"], "2026-07-05 10:00")
        self.assertEqual(columns["deadline_source"], "ai")
        self.assertEqual(urgency["urgency_reference_type"], "submission")
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
pytest tests/test_ai_extractor.py::AIExtractorTests::test_parse_json_text_extracts_object_from_wrapped_response tests/test_ai_extractor.py::AIExtractorTests::test_deadline_helpers_ignore_non_dict_deadline_items -q
```

Expected: FAIL because wrapped JSON is rejected and string deadline entries call `.get()`.

- [ ] **Step 3: Add JSON extraction helper**

In `AIExtractor`, replace `_parse_json_text` with:

```python
    def _parse_json_text(self, text: str) -> dict:
        if not isinstance(text, str):
            raise ValueError("AI response text is missing")
        cleaned = self._extract_json_object_text(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("AI response is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("AI response JSON must be an object")
        return data

    def _extract_json_object_text(self, text: str) -> str:
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        if "{" in cleaned and "}" in cleaned:
            return cleaned[cleaned.find("{"):cleaned.rfind("}") + 1].strip()
        return cleaned
```

- [ ] **Step 4: Add deadline normalization helper**

Add this function before `build_column_updates`:

```python
def _iter_deadline_dicts(ai_data: dict):
    deadlines = (ai_data or {}).get("deadlines") or []
    if isinstance(deadlines, dict):
        deadlines = [deadlines]
    if not isinstance(deadlines, list):
        return
    for deadline in deadlines:
        if isinstance(deadline, dict):
            yield deadline
```

In `build_column_updates`, replace:

```python
    deadlines = (ai_data or {}).get("deadlines") or []
    used_deadlines = False
    for deadline in deadlines:
```

with:

```python
    used_deadlines = False
    for deadline in _iter_deadline_dicts(ai_data):
```

In `suggest_urgency`, replace:

```python
    deadlines = (ai_data or {}).get("deadlines") or []
```

with:

```python
    deadlines = list(_iter_deadline_dicts(ai_data))
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_ai_extractor.py::AIExtractorTests::test_parse_json_text_extracts_object_from_wrapped_response tests/test_ai_extractor.py::AIExtractorTests::test_deadline_helpers_ignore_non_dict_deadline_items -q
```

Expected: PASS.

- [ ] **Step 6: Run AI extractor regression tests**

Run:

```bash
pytest tests/test_ai_extractor.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/results/ai_extractor.py tests/test_ai_extractor.py
git commit -m "fix: tolerate wrapped ai extraction output"
```

---

### Task 7: Return Unknown On AI Guard Errors

**Files:**
- Modify: `src/ai_guard.py:97-145`
- Modify: `src/ai_guard.py:147-281`
- Test: `tests/test_ai_guard.py`

- [ ] **Step 1: Write failing tests for fail-unknown behavior**

Add these tests to `tests/test_ai_guard.py`:

```python
    def test_ambiguous_non_json_response_returns_unknown_reason(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": "模型输出无法判断"}}]}
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", return_value=response):
            relevant, reason = AIGuard(config).check_relevance("平台首页", "欢迎访问")

        self.assertFalse(relevant)
        self.assertIn("AI结果未知", reason)

    def test_network_error_returns_unknown_when_ai_enabled(self):
        config = {
            "enable": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "secret",
            "model": "grok-4.20-fast",
            "endpoint_type": "chat_completions",
        }

        with patch("requests.post", side_effect=Exception("boom")):
            relevant, reason = AIGuard(config).check_relevance("智能化公开招标", "视频监控")

        self.assertFalse(relevant)
        self.assertIn("AI请求异常", reason)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_ai_guard.py::AIGuardTests::test_ambiguous_non_json_response_returns_unknown_reason tests/test_ai_guard.py::AIGuardTests::test_network_error_returns_unknown_when_ai_enabled -q
```

Expected: FAIL because ambiguous text and exceptions currently return relevant.

- [ ] **Step 3: Change ambiguous text fallback**

In `_infer_relevance_from_text`, replace:

```python
        return True
```

with:

```python
        return None
```

In `check_relevance`, in the JSON decode fallback block, replace:

```python
                        if is_relevant:
                            self.log(f"✅ [AI判定] 相关 - {ai_content[:80]}")
                        else:
                            self.log(f"🚫 [AI判定] 不相关 - {ai_content[:80]}")
                        return is_relevant, ai_content[:80]
```

with:

```python
                        if is_relevant is None:
                            self.log(f"⚠️ [AI判定] 未知 - {ai_content[:80]}")
                            return False, f"AI结果未知: {ai_content[:60]}"
                        if is_relevant:
                            self.log(f"✅ [AI判定] 相关 - {ai_content[:80]}")
                        else:
                            self.log(f"🚫 [AI判定] 不相关 - {ai_content[:80]}")
                        return is_relevant, ai_content[:80]
```

- [ ] **Step 4: Change exception returns**

Keep AI disabled and missing key behavior unchanged:

```python
        if not self.enabled:
            return True, "AI未启用"

        if not self.api_key:
            return True, "AI未配置Key"
```

Change network exhausted return from:

```python
                        return True, f"AI网络异常（已重试{max_retries}次）"
```

to:

```python
                        return False, f"AI请求异常: 网络异常（已重试{max_retries}次）"
```

Change missing requests return from:

```python
            return True, "请安装 requests 库: pip install requests"
```

to:

```python
            return False, "AI请求异常: 请安装 requests 库"
```

Change final exception return from:

```python
            return True, f"AI请求异常: {error_msg[:50]}"
```

to:

```python
            return False, f"AI请求异常: {error_msg[:50]}"
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_ai_guard.py::AIGuardTests::test_ambiguous_non_json_response_returns_unknown_reason tests/test_ai_guard.py::AIGuardTests::test_network_error_returns_unknown_when_ai_enabled -q
```

Expected: PASS.

- [ ] **Step 6: Run AI guard regression tests**

Run:

```bash
pytest tests/test_ai_guard.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_guard.py tests/test_ai_guard.py
git commit -m "fix: avoid ai relevance fail open"
```

---

### Task 8: Add Notification Policy For AI Unknown And AI-Only Opportunities

**Files:**
- Modify: `src/monitor_core.py:476-497`
- Test: `tests/test_monitor_core_ai_extraction.py`

- [ ] **Step 1: Write failing tests for notification policies**

Add this fake crawler at file scope in `tests/test_monitor_core_ai_extraction.py`, next to the existing fake crawlers:

```python
class AiOnlyOpportunityCrawler:
    name = "fake"

    def crawl(self, stop_event=None):
        return [BidInfo("消防维保服务采购公告", "https://example.com/c", "2026-07-01", "源", "消防设施维护")]
```

Add these methods inside `MonitorCoreAIExtractionTests`:

```python
    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_ai_only_policy_notifies_ai_relevant_without_keyword_match(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "notification_policy": "keyword_or_ai",
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [AiOnlyOpportunityCrawler()]
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (True, "边界机会")

        with patch("src.monitor_core.enrich_new_bid"):
            result = monitor.run_once()

        self.assertEqual(result["matched_count"], 1)
        storage.mark_notified.assert_not_called()

    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_strict_policy_does_not_notify_on_ai_error(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "notification_policy": "strict_keyword_and_ai",
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [FakeCrawler()]
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (False, "AI请求异常: boom")

        with patch("src.monitor_core.enrich_new_bid"):
            result = monitor.run_once()

        self.assertEqual(result["matched_count"], 0)
        storage.mark_notified.assert_called_once()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_ai_only_policy_notifies_ai_relevant_without_keyword_match tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_strict_policy_does_not_notify_on_ai_error -q
```

Expected: first test FAILS because only keyword-and-AI notification exists; second test should PASS once Task 7 is in place.

- [ ] **Step 3: Add notification policy helper**

In `MonitorCore`, add this method before `_send_notifications`:

```python
    def _should_notify_bid(self, keyword_matched: bool, ai_relevant: bool, ai_reason: str) -> bool:
        policy = (self.config.get("crawler", {}) or {}).get("notification_policy", "strict_keyword_and_ai")
        ai_unknown = str(ai_reason or "").startswith("AI请求异常") or str(ai_reason or "").startswith("AI结果未知")
        if policy == "keyword_or_ai":
            return (keyword_matched or ai_relevant) and not ai_unknown
        if policy == "keyword_only_on_ai_error":
            return keyword_matched if ai_unknown else keyword_matched and ai_relevant
        return keyword_matched and ai_relevant and not ai_unknown
```

In `run_once`, replace:

```python
                    should_notify = result.matched and ai_relevant
```

with:

```python
                    should_notify = self._should_notify_bid(result.matched, ai_relevant, ai_reason)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_ai_only_policy_notifies_ai_relevant_without_keyword_match tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_strict_policy_does_not_notify_on_ai_error -q
```

Expected: PASS.

- [ ] **Step 5: Run MonitorCore AI tests**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/monitor_core.py tests/test_monitor_core_ai_extraction.py
git commit -m "feat: add configurable notification policy"
```

---

### Task 9: Score Candidate Links Before Enqueue

**Files:**
- Modify: `src/crawler/url_list.py:808-827`
- Modify: `src/crawler/url_list.py:854-864`
- Test: `tests/test_url_list_crawler.py`

- [ ] **Step 1: Write failing test for priority sorting**

Add this test to `tests/test_url_list_crawler.py`:

```python
    @patch.object(UrlListCrawler, "_request_url")
    def test_candidate_scoring_prioritizes_detail_links_over_noisy_lists(self, mock_request_url):
        def fake_request(url):
            if url == "https://portal.example.com/":
                return (
                    "<html><body>"
                    "<a href='/company-1.html'>上海测试招标代理有限公司</a>"
                    "<a href='/category/news.html'>政策法规新闻</a>"
                    "<a href='/notice/1.html'>上海安防工程公开招标公告 2026-07-02</a>"
                    "</body></html>",
                    200,
                    "OK",
                )
            if url == "https://portal.example.com/notice/1.html":
                return (
                    "<html><body><h1>上海安防工程公开招标公告</h1>"
                    "<p>发布时间：2026-07-02</p><p>采购单位：上海测试单位</p>"
                    "<p>公告正文：本项目采购安防监控系统。</p></body></html>",
                    200,
                    "OK",
                )
            raise AssertionError(f"unexpected url {url}")

        mock_request_url.side_effect = fake_request

        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            diagnostics_path = os.path.join(tmpdir, "diagnostics.jsonl")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "detail_url_regex": [r"/notice/\d+\.html$"],
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                diagnostics_path,
                {"topology_max_depth": 1, "max_follow_links_per_page": 1},
                config={"site_topologies_path": topology_path},
            )

            bids = crawler.crawl()

        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].url, "https://portal.example.com/notice/1.html")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_candidate_scoring_prioritizes_detail_links_over_noisy_lists -q
```

Expected: FAIL if the first noisy link consumes the only enqueue slot.

- [ ] **Step 3: Add scoring helper**

Add these methods after `_merge_candidate_links`:

```python
    def _score_candidate_link(self, page_url: str, link: Dict[str, str]) -> int:
        url = link.get("url", "")
        title = link.get("title", "")
        rule = self._classify_url(url)
        score = 0
        if rule.get("page_type") == "detail":
            score += 100
        elif rule.get("page_type") in {"list", "search"}:
            score += 30
        if self._has_strong_bid_stage(title):
            score += 40
        if DATE_RE.search(title or ""):
            score += 10
        if any(keyword in title for keyword in ["弱电", "智能化", "安防", "监控", "消防"]):
            score += 10
        lowered = f"{url} {title}".lower()
        if any(keyword in lowered for keyword in NEGATIVE_LINK_KEYWORDS):
            score -= 60
        if self._is_known_non_announcement_url(url):
            score -= 200
        return score

    def _sort_candidate_links(self, page_url: str, links: List[Dict[str, str]]) -> List[Dict[str, str]]:
        return sorted(
            links,
            key=lambda link: self._score_candidate_link(page_url, link),
            reverse=True,
        )
```

- [ ] **Step 4: Sort before slicing**

In `_crawl_topology_from_url`, before:

```python
            for link in candidate_links[: self.max_follow_links_per_page]:
```

add:

```python
            candidate_links = self._sort_candidate_links(page_url, candidate_links)
```

- [ ] **Step 5: Run focused test**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_candidate_scoring_prioritizes_detail_links_over_noisy_lists -q
```

Expected: PASS.

- [ ] **Step 6: Run crawler regression tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/crawler/url_list.py tests/test_url_list_crawler.py
git commit -m "fix: prioritize high value crawl candidates"
```

---

### Task 10: Execute Topology Search Requests For GET And POST Sources

**Files:**
- Modify: `src/crawler/url_list.py:940-954`
- Modify: `src/crawler/url_list.py:1000-1028`
- Modify: `src/crawler/source_adapter.py:67-80`
- Test: `tests/test_url_list_crawler.py`
- Test: `tests/test_source_adapter.py`

- [ ] **Step 1: Write failing tests for POST search execution**

Add this test to `tests/test_url_list_crawler.py`:

```python
    def test_topology_search_request_uses_post_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            urls_path = os.path.join(tmpdir, "urls.txt")
            with open(urls_path, "w", encoding="utf-8") as f:
                f.write("https://portal.example.com/\n")
            topology_path = self.write_topologies(
                tmpdir,
                [
                    {
                        "id": "portal",
                        "name": "Portal",
                        "entry_url": "https://portal.example.com/",
                        "allowed_hosts": ["portal.example.com"],
                        "search": {
                            "method": "POST",
                            "url": "https://portal.example.com/api/search",
                            "params": ["pageNum", "title"],
                            "defaults": {"pageNum": 1, "title": ""},
                        },
                    }
                ],
            )
            crawler = self.make_crawler_with_source_config(
                urls_path,
                None,
                {},
                config={"site_topologies_path": topology_path},
            )

            request = crawler._topology_search_request("https://portal.example.com/")

        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://portal.example.com/api/search")
        self.assertEqual(request["data"], {"pageNum": 1, "title": ""})
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_search_request_uses_post_when_configured -q
```

Expected: FAIL because `_topology_search_request` does not exist.

- [ ] **Step 3: Add search request builder**

Add this method after `_topology_seed_links`:

```python
    def _topology_search_request(self, seed_url: str) -> Optional[Dict[str, Any]]:
        topology = self._topology_for_url(seed_url)
        search = (topology or {}).get("search") or {}
        if not isinstance(search, dict):
            return None
        method = str(search.get("method", "GET")).upper()
        if method not in {"GET", "POST", "GET_OR_POST"}:
            return None
        url = str(search.get("url") or "").strip()
        if not url or "{" in url or "}" in url:
            return None
        defaults = search.get("defaults") if isinstance(search.get("defaults"), dict) else {}
        params = {key: defaults.get(key, "") for key in search.get("params", []) or []}
        if method == "GET_OR_POST":
            method = "GET"
        return {
            "method": method,
            "url": urljoin(seed_url, url),
            "params": params if method == "GET" else {},
            "data": params if method == "POST" else {},
        }
```

- [ ] **Step 4: Add request executor**

Replace `_request_url` internals with a wrapper that delegates to a new method:

```python
    def _request_url(self, url: str) -> Tuple[str, int, str]:
        return self._request_http("GET", url)

    def _request_http(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int, str]:
        if self.session is None:
            raise requests.RequestException("requests is required for HTTP fetching. Install requirements.txt.")
        headers = self._get_headers()
        cookie = self._get_cookie_for_url(url)
        if cookie:
            headers["Cookie"] = cookie
        started_at = time.monotonic()
        method = method.upper()
        self._emit_info(f"[URL请求] {self.name}: HTTP {method} {self._short_url(url)}")
        try:
            if method == "POST":
                response = self.session.post(
                    url,
                    headers=headers,
                    data=data or {},
                    timeout=self.timeout,
                    verify=False,
                    allow_redirects=True,
                )
            else:
                response = self.session.get(
                    url,
                    headers=headers,
                    params=params or {},
                    timeout=self.timeout,
                    verify=False,
                    allow_redirects=True,
                )
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            self._emit_info(f"[URL请求] {self.name}: HTTP异常 {exc.__class__.__name__}，耗时 {elapsed:.1f}s {self._short_url(url)}")
            raise
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        elapsed = time.monotonic() - started_at
        self._emit_info(
            f"[URL请求] {self.name}: HTTP {response.status_code} {response.reason}，"
            f"{len(response.text or '')} 字符，耗时 {elapsed:.1f}s {self._short_url(url)}"
        )
        return response.text, response.status_code, response.reason
```

- [ ] **Step 5: Use search request in topology seed crawl**

In `_crawl_topology_from_url`, before initializing `queue`, build search request:

```python
        queue: List[Tuple[str, int, Optional[str], str]] = [(seed_url, 0, seed_html, "")]
        search_request = self._topology_search_request(seed_url)
        if search_request:
            queue.insert(0, (search_request["url"], 0, None, ""))
```

In the fetch block where `_request_url(page_url)` is called, replace with:

```python
                        request = search_request if search_request and page_url == search_request["url"] else None
                        if request:
                            html, status_code, _status_text = self._request_http(
                                request["method"],
                                request["url"],
                                params=request.get("params"),
                                data=request.get("data"),
                            )
                        else:
                            html, status_code, _status_text = self._request_url(page_url)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/test_url_list_crawler.py::UrlListCrawlerTests::test_topology_search_request_uses_post_when_configured -q
```

Expected: PASS.

- [ ] **Step 7: Run source adapter and crawler tests**

Run:

```bash
pytest tests/test_url_list_crawler.py tests/test_source_adapter.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/crawler/url_list.py src/crawler/source_adapter.py tests/test_url_list_crawler.py tests/test_source_adapter.py
git commit -m "feat: execute topology search requests"
```

---

### Task 11: Skip Low-Value Enrichment Before Detail Fetch

**Files:**
- Modify: `src/monitor_core.py:432-493`
- Test: `tests/test_monitor_core_ai_extraction.py`

- [ ] **Step 1: Write failing test for enrichment gating**

Add this test to `tests/test_monitor_core_ai_extraction.py`:

```python
    @patch("src.monitor_core.Storage")
    @patch("src.monitor_core.get_all_crawlers", return_value={})
    @patch("src.monitor_core.get_default_sites", return_value={})
    def test_non_matching_ai_rejected_bid_does_not_trigger_detail_enrichment_when_gated(self, _sites, _classes, storage_cls):
        storage = Mock(spec=Storage)
        storage.exists.return_value = False
        storage.save.return_value = 123
        storage_cls.return_value = storage
        monitor = MonitorCore(
            keywords=["智能化"],
            crawler_overrides={
                "enabled_sites": [],
                "enrich_only_candidate_results": True,
            },
            ai_config={"enable": False},
        )
        monitor.crawlers = [NonMatchingFakeCrawler()]
        monitor.ai_guard = Mock()
        monitor.ai_guard.check_relevance.return_value = (False, "办公耗材不相关")

        with patch("src.monitor_core.enrich_new_bid") as enrich:
            monitor.run_once()

        enrich.assert_not_called()
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_non_matching_ai_rejected_bid_does_not_trigger_detail_enrichment_when_gated -q
```

Expected: FAIL because enrichment currently runs immediately after save, before AI relevance is checked.

- [ ] **Step 3: Move enrichment after local and AI relevance checks**

In `run_once`, keep saving before AI review, but defer enrichment until after `ai_relevant` is known. Replace the immediate enrichment block:

```python
                            enrich_new_bid(
                                self.storage,
                                result_id,
                                bid,
                                self.ai_config_for_extraction,
                                log_callback=self.log,
                                fetch_config=self.config.get('crawler', {}),
                            )
```

with:

```python
                            pass
```

After AI relevance update and before notification decision, add:

```python
                    should_enrich = bool(result_id)
                    if self.config.get('crawler', {}).get('enrich_only_candidate_results', False):
                        should_enrich = bool(result_id and (result.matched or ai_relevant))
                    if should_enrich:
                        enrich_new_bid(
                            self.storage,
                            result_id,
                            bid,
                            self.ai_config_for_extraction,
                            log_callback=self.log,
                            fetch_config=self.config.get('crawler', {}),
                        )
```

- [ ] **Step 4: Run focused test**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py::MonitorCoreAIExtractionTests::test_non_matching_ai_rejected_bid_does_not_trigger_detail_enrichment_when_gated -q
```

Expected: PASS.

- [ ] **Step 5: Run MonitorCore AI tests**

Run:

```bash
pytest tests/test_monitor_core_ai_extraction.py -q
```

Expected: PASS. If `test_new_saved_bid_triggers_enrichment` fails, keep default `enrich_only_candidate_results` as `False`.

- [ ] **Step 6: Commit**

```bash
git add src/monitor_core.py tests/test_monitor_core_ai_extraction.py
git commit -m "feat: gate detail enrichment for low value results"
```

---

### Task 12: Final Verification

**Files:**
- Verify only; no code edits.

- [ ] **Step 1: Run focused suites**

Run:

```bash
pytest tests/test_url_list_crawler.py tests/test_ai_extractor.py tests/test_ai_guard.py tests/test_monitor_core_ai_extraction.py tests/test_source_adapter.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 3: Inspect crawl behavior manually with mocked tests**

Run:

```bash
pytest tests/test_url_list_crawler.py -q -k "download or circuit or topology or shell or evidence or scoring"
```

Expected: PASS and no unexpected network calls.

- [ ] **Step 4: Review diff for accidental production churn**

Run:

```bash
git diff -- src/crawler/url_list.py src/results/ai_extractor.py src/ai_guard.py src/monitor_core.py src/crawler/source_adapter.py tests/test_url_list_crawler.py tests/test_ai_extractor.py tests/test_ai_guard.py tests/test_monitor_core_ai_extraction.py tests/test_source_adapter.py
```

Expected: diff only contains the planned guards, tests, and policy changes.

- [ ] **Step 5: Commit final verification note if there are documentation changes**

If only code commits already exist, skip this commit. If this plan or release notes changed during execution, run:

```bash
git add docs/superpowers/plans/2026-07-04-bidmonitor-crawl-ai-quality.md
git commit -m "docs: plan crawl and ai quality repairs"
```

---

## Self-Review Checklist

- Spec coverage: Tasks 1-5 cover URL filtering, circuit breaking, topology strictness, non-announcement rejection, SPA shell rejection, and detail evidence tightening. Tasks 6-8 cover AI extraction, AI fail-open, and notification policy. Tasks 9-11 cover candidate scoring, topology search execution, and enrichment cost reduction.
- Type consistency: helper names are stable across tasks: `_is_valid_traversal_url`, `_is_domain_circuit_open`, `_topology_requires_strict_detail_urls`, `_is_known_non_announcement_url`, `_has_structured_procurement_field`, `_iter_deadline_dicts`, `_should_notify_bid`.
- Risk ordering: P0 is Tasks 1-8. P1 is Tasks 9-11. Task 12 verifies all changes together.
