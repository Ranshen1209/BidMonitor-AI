"""
URL 列表爬虫 - 从 txt/csv 读取公开页面并输出基础招标信息。
"""
import csv
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urljoin, urlparse

try:
    import requests
except ImportError:  # pragma: no cover - exercised through import-time tests
    class _RequestException(Exception):
        pass

    class _Timeout(_RequestException):
        pass

    class _ConnectionError(_RequestException):
        pass

    class _RequestsFallback:
        RequestException = _RequestException
        exceptions = SimpleNamespace(
            Timeout=_Timeout,
            ConnectionError=_ConnectionError,
        )

    requests = _RequestsFallback()

from .base import BaseCrawler, BidInfo
from .source_registry import load_url_sources

DEFAULT_SITE_TOPOLOGIES_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "server", "site_topologies.json")
)
DEFAULT_URL_SOURCES_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "server", "url_sources.json")
)


BLOCKED_SIGNS = [
    "验证码",
    "访问频繁",
    "请求过于频繁",
    "access denied",
    "forbidden",
    "captcha",
    "请先登录",
    "请登录后",
    "登录后查看",
    "安全验证",
    "滑块验证",
    "人机验证",
    "访问被拒绝",
    "请求被禁止",
    "ip被封",
]

BID_LINK_KEYWORDS = [
    "政府采购意向",
    "采购意向",
    "竞争性磋商",
    "竞争性谈判",
    "单一来源",
    "资格预审",
    "预算公开",
    "采购计划",
    "需求调研",
    "需求公示",
    "项目公示",
    "合同公告",
    "验收公告",
    "结果公告",
    "更正公告",
    "变更公告",
    "废标公告",
    "流标公告",
    "中标公告",
    "成交公告",
    "招标公告",
    "询价公告",
    "招标",
    "投标",
    "采购",
    "公告",
    "公示",
    "磋商",
    "竞价",
    "成交",
    "中标",
]

NEGATIVE_LINK_KEYWORDS = [
    "登录",
    "注册",
    "帮助",
    "关于我们",
    "联系我们",
    "政策法规",
    "政府采购法",
    "法律法规",
    "法规",
    "修订草案",
    "征求意见",
    "行业动态",
    "综合要闻",
    "工作动态",
    "新闻",
    "供应商采取措施",
    "财政部：",
    "下载中心",
    "用户协议",
    "法律声明",
    "广告",
    "图片",
    "css",
    "js",
]

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

FIELD_STOP_LABELS = [
    "采购项目名称",
    "招标项目名称",
    "项目名称",
    "预算金额",
    "最高限价",
    "报名截止时间",
    "投标截止时间",
    "开标时间",
    "标书代写",
    "关键信息",
    "代理联系人",
    "正文内容",
    "公告内容",
]

STAGE_KEYWORDS: List[Tuple[str, str]] = [
    ("政府采购意向", "政府采购意向"),
    ("采购意向", "采购意向"),
    ("竞争性磋商公告", "竞争性磋商公告"),
    ("竞争性谈判公告", "竞争性谈判公告"),
    ("单一来源公示", "单一来源公示"),
    ("资格预审公告", "资格预审公告"),
    ("中标公告", "中标公告"),
    ("成交公告", "成交公告"),
    ("结果公告", "结果公告"),
    ("更正公告", "更正公告"),
    ("变更公告", "变更公告"),
    ("废标公告", "废标公告"),
    ("流标公告", "流标公告"),
    ("合同公告", "合同公告"),
    ("验收公告", "验收公告"),
    ("公开招标公告", "招标公告"),
    ("招标公告", "招标公告"),
    ("询价公告", "询价公告"),
    ("招标预告", "招标预告"),
    ("采购计划", "采购计划"),
    ("预算公开", "预算公开"),
    ("预采购", "预采购"),
    ("需求调研", "需求调研"),
    ("需求公示", "需求公示"),
    ("项目公示", "项目公示"),
    ("招标", "招标"),
]

TITLE_FIELDS = ["title", "noticeTitle", "announcementTitle", "name", "projectName", "采购项目名称", "项目名称"]
URL_FIELDS = ["url", "link", "href", "detailUrl", "detail_url", "pageUrl", "articleUrl"]
DATE_FIELDS = ["publishDate", "publishTime", "publishedAt", "date", "time", "发布时间", "发布日期"]
CONTENT_FIELDS = ["content", "noticeContent", "announcementContent", "body", "summary", "正文"]
PURCHASER_FIELDS = ["purchaser", "buyer", "采购人", "招标人", "采购单位"]
TYPE_FIELDS = ["noticeType", "announcementType", "type", "category", "公告类型", "信息类型"]
SOURCE_FIELDS = ["source", "publisher", "发布机构", "发布单位", "来源", "代理机构"]

CONTACT_PERSON_LABELS = ["项目联系人", "采购联系人", "招标联系人", "代理联系人", "联系人姓名", "联系人及电话", "联系人", "经办人"]
CONTACT_METHOD_LABELS = [
    "联系电话",
    "联系人电话",
    "项目联系电话",
    "采购人联系方式",
    "代理机构联系方式",
    "电话",
    "手机",
    "手机号",
    "联系方式",
    "邮箱",
    "电子邮箱",
]
RESPONSIBLE_PERSON_LABELS = ["项目负责人", "采购负责人", "招标负责人", "代理负责人", "经办负责人", "业务负责人", "项目经理", "负责人"]
RESPONSIBLE_METHOD_LABELS = [
    "项目负责人电话",
    "项目负责人联系方式",
    "采购负责人电话",
    "招标负责人电话",
    "代理负责人电话",
    "负责人电话",
    "负责人联系方式",
]
SOURCE_LABELS = ["发布机构", "发布单位", "来源", "代理机构"]
PURCHASER_LABELS = ["采购人", "招标人", "采购单位"]
PUBLISH_DATE_LABELS = ["发布时间", "发布日期", "公告时间", "发文时间", "时间", "日期"]

PHONE_RE = re.compile(
    r"(?<![\dA-Za-z])(?:1[3-9]\d{9}|\(?0\d{2,3}\)?[-\s]?\d{7,8}(?:[-\s]*(?:转|分机|-)?\s*\d{1,6})?)(?!\d)"
)
EMAIL_RE = re.compile(r"(?<![\w.-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
DATE_RE = re.compile(
    r"(?P<year>20\d{2})[-/.年](?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})(?:日)?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
)


class _MiniNode:
    def __init__(self, tag: str, text: str = "", attrs: Optional[Dict[str, str]] = None):
        self.name = tag
        self._text = text
        self.attrs = attrs or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.attrs.get(key, default)

    def get_text(self, separator: str = " ", strip: bool = False) -> str:
        text = self._text
        if strip:
            text = text.strip()
        return re.sub(r"\s+", separator, text) if separator else text

    def decompose(self) -> None:
        self._text = ""
        self.attrs = {}


class _MiniSoup(HTMLParser):
    """Small fallback parser for tests when beautifulsoup4 is unavailable."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self._links: List[_MiniNode] = []
        self._heading_nodes: Dict[str, List[_MiniNode]] = {"h1": [], "h2": [], "title": []}
        self._text_parts: List[str] = []
        self._active_link: Optional[Dict[str, Any]] = None
        self._active_heading: Optional[Dict[str, Any]] = None
        self._container_stack: List[Dict[str, Any]] = []
        self._ignored_depth = 0
        self.feed(html or "")

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in ("li", "tr", "td", "p", "div"):
            self._container_stack.append({"tag": tag, "text": [], "links": []})
        if tag == "a" and attrs_dict.get("href"):
            self._active_link = {"href": attrs_dict["href"], "text": []}
        if tag in self._heading_nodes:
            self._active_heading = {"tag": tag, "text": []}

    def handle_data(self, data: str):
        if self._ignored_depth:
            return
        if self._active_link is not None:
            self._active_link["text"].append(data)
        if self._active_heading is not None:
            self._active_heading["text"].append(data)
        for container in self._container_stack:
            container["text"].append(data)
        if data.strip():
            self._text_parts.append(data)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "a" and self._active_link is not None:
            node = _MiniNode("a", "".join(self._active_link["text"]), {"href": self._active_link["href"]})
            self._links.append(node)
            for container in self._container_stack:
                container["links"].append(node)
            self._active_link = None
        if self._active_heading is not None and tag == self._active_heading["tag"]:
            self._heading_nodes[tag].append(_MiniNode(tag, "".join(self._active_heading["text"])))
            self._active_heading = None
        if self._container_stack and tag == self._container_stack[-1]["tag"]:
            container = self._container_stack.pop()
            context = "".join(container["text"])
            for node in container["links"]:
                if len(context) > len(node.attrs.get("context", "")):
                    node.attrs["context"] = context

    def find_all(self, tag: str, **kwargs) -> List[_MiniNode]:
        if tag == "a" and kwargs.get("href") is True:
            return self._links
        if tag in ("script", "style", "noscript"):
            return []
        return []

    def find(self, tag: str) -> Optional[_MiniNode]:
        nodes = self._heading_nodes.get(tag, [])
        return nodes[0] if nodes else None

    def get_text(self, separator: str = " ", strip: bool = False) -> str:
        text = separator.join(self._text_parts)
        text = re.sub(r"\s+", separator, text)
        return text.strip() if strip else text

    def __call__(self, tags) -> List[_MiniNode]:
        return []


class UrlListCrawler(BaseCrawler):
    """读取 txt/csv URL 清单逐条抓取的通用爬虫。"""

    def __init__(self, config: Dict[str, Any], source_config: Dict[str, Any]):
        config = dict(config)
        config.setdefault("timeout", source_config.get("timeout", 10))
        config.setdefault("max_retries", source_config.get("max_retries", 1))
        config.setdefault("request_delay", source_config.get("request_delay", 0))
        self.source_config = source_config
        self._name = source_config.get("name") or "URL列表"
        self.file_path = self._resolve_builtin_data_path(
            source_config.get("file_path", ""),
            DEFAULT_URL_SOURCES_PATH,
            "url_sources.json",
        )
        self.diagnostics_path = (
            source_config.get("diagnostics_path")
            or config.get("diagnostics_path")
            or os.path.join("logs", "url_crawl_diagnostics.jsonl")
        )
        self.log_callback = config.get("log_callback")
        self.max_links_per_page = int(config.get("url_list_max_links_per_page", 50))
        self.topology_max_depth = int(source_config.get("topology_max_depth", config.get("topology_max_depth", 3)))
        self.max_follow_links_per_page = int(
            source_config.get("max_follow_links_per_page", config.get("max_follow_links_per_page", 25))
        )
        self.max_detail_pages_per_seed = int(
            source_config.get("max_detail_pages_per_seed", config.get("max_detail_pages_per_seed", 15))
        )
        self.url_concurrency = max(1, int(source_config.get("concurrency", config.get("url_list_concurrency", 1))))
        self.domain_delay = float(source_config.get("domain_delay", config.get("domain_delay", 0)))
        self.auth_cookies = source_config.get("auth_cookies", config.get("auth_cookies", []))
        self.preserve_missing_publish_date = bool(config.get("preserve_missing_publish_date"))
        self._last_domain_request_at: Dict[str, float] = {}
        self.domain_failure_threshold = int(
            source_config.get("domain_failure_threshold", config.get("domain_failure_threshold", 3))
        )
        self._domain_failure_counts: Dict[str, int] = {}
        self._domain_circuit_open: set[str] = set()
        self._domain_failure_lock = threading.Lock()
        self._topology_fetch_gates: Dict[str, threading.Lock] = {}
        self._topology_fetch_gates_guard = threading.Lock()
        self._domain_locks: Dict[str, threading.Lock] = {}
        self._domain_locks_guard = threading.Lock()
        self._diagnostics_lock = threading.Lock()
        self._browser_fetch_lock = threading.Lock()
        topology_path = self._resolve_builtin_data_path(
            source_config.get("site_topologies_path")
            or config.get("site_topologies_path")
            or DEFAULT_SITE_TOPOLOGIES_PATH,
            DEFAULT_SITE_TOPOLOGIES_PATH,
            "site_topologies.json",
        )
        self.site_topologies = self._load_site_topologies(topology_path)
        super().__init__(config)

    @property
    def name(self) -> str:
        return self._name

    def get_list_urls(self) -> List[str]:
        if not self.file_path or not os.path.exists(self.file_path):
            self._emit_log(f"[WARN] [{self.name}] URL清单文件不存在: {self.file_path}")
            return []

        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == ".csv":
            raw_urls = self._read_csv_urls()
        elif ext == ".json" or self.source_config.get("source_type") in {"json", "bookmarks_html"}:
            raw_urls = [source.url for source in load_url_sources(self.file_path)]
        elif ext in {".html", ".htm"}:
            raw_urls = [source.url for source in load_url_sources(self.file_path)]
        else:
            raw_urls = self._read_txt_urls()

        urls = []
        seen = set()
        for raw_url in raw_urls:
            url = self._clean_url(raw_url)
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def _resolve_builtin_data_path(self, path: str, fallback_path: str, filename: str) -> str:
        if not path:
            return path
        normalized = os.path.normpath(str(path))
        if os.path.exists(normalized):
            return normalized
        if os.path.basename(normalized) != filename:
            return path
        parts = set(normalized.replace("\\", "/").split("/"))
        if "BidMonitor-AI" in parts or "server" in parts:
            return fallback_path
        return path

    def _emit_log(self, message: str) -> None:
        self.logger.warning(message)
        if self.log_callback:
            self.log_callback(message)

    def _emit_info(self, message: str) -> None:
        self.logger.info(message)
        if self.log_callback:
            self.log_callback(message)

    def _short_url(self, url: str, limit: int = 140) -> str:
        url = str(url or "")
        return url if len(url) <= limit else f"{url[:limit - 3]}..."

    def parse(self, html: str) -> List[BidInfo]:
        return self._parse_page(html, self.base_url, datetime.now().isoformat(timespec="seconds"))

    def _fallback_publish_date(self) -> str:
        return "" if self.preserve_missing_publish_date else datetime.now().strftime("%Y-%m-%d")

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        urls = self.get_list_urls()
        all_bids: List[BidInfo] = []
        self.logger.info(f"[{self.name}] Starting URL list crawl, {len(urls)} URL(s)")
        self._emit_info(f"[URL进度] {self.name}: 准备抓取 {len(urls)} 个入口URL")

        if not urls:
            self.logger.info(f"[{self.name}] URL list crawl done, got 0 item(s)")
            return []

        concurrency = min(self.url_concurrency, len(urls))
        if concurrency <= 1:
            for index, url in enumerate(urls, 1):
                all_bids.extend(self._crawl_one_entry(index, len(urls), url, stop_event=stop_event))
        else:
            self._emit_info(f"[URL并发] {self.name}: 启用 {concurrency} 个入口并发，同域仍按 {self.domain_delay:g}s 限频")
            with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="url-crawl") as executor:
                future_to_url = {
                    executor.submit(self._crawl_one_entry, index, len(urls), url, stop_event): url
                    for index, url in enumerate(urls, 1)
                }
                for future in as_completed(future_to_url):
                    if stop_event and stop_event.is_set():
                        break
                    try:
                        all_bids.extend(future.result())
                    except Exception as exc:
                        url = future_to_url[future]
                        self._emit_log(f"[URL诊断] {self.name} | failed | {url} | 并发任务异常: {exc}")

        self.logger.info(f"[{self.name}] URL list crawl done, got {len(all_bids)} item(s)")
        return all_bids

    def _crawl_one_entry(self, index: int, total: int, url: str, stop_event=None) -> List[BidInfo]:
        entry_bids: List[BidInfo] = []
        if stop_event and stop_event.is_set():
            self.logger.info(f"[{self.name}] Crawl interrupted by stop signal")
            return entry_bids

        entry_started_at = time.monotonic()
        timestamp = datetime.now().isoformat(timespec="seconds")
        cookie_used = self._get_cookie_for_url(url) is not None
        try:
            self._emit_info(f"[URL进度] {self.name}: {index}/{total} {self._short_url(url)}")
            rule = self._classify_url(url)
            self._emit_info(
                f"[URL分类] {self.name}: {rule.get('platform')} | {rule.get('page_type')} | "
                f"{rule.get('handling')} | {self._short_url(url)}"
            )
            if self._should_skip_before_fetch(rule):
                self._record_diagnostic(
                    url,
                    "skipped_with_reason",
                    rule["reason"],
                    timestamp,
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids

            self._respect_rate_limit(url)
            browser_first = self._prefers_browser_fetch(url)
            browser_result = self._request_url_with_browser(url) if browser_first else None
            if browser_result:
                html, status_code, status_text = browser_result
            else:
                try:
                    html, status_code, status_text = self._request_url(url)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.RequestException):
                    if not self._should_retry_browser_for_fetch_failure(url):
                        raise
                    browser_result = self._request_url_with_browser(url)
                    if not browser_result:
                        raise
                    html, status_code, status_text = browser_result
            if status_code in (401, 403):
                seed_bids = self._try_topology_seed_fallback(url, timestamp, rule, cookie_used, stop_event=stop_event)
                if seed_bids:
                    entry_bids.extend(seed_bids)
                    self._record_diagnostic(
                        url,
                        "success",
                        f"入口 HTTP {status_code}，已按站点拓扑种子继续并生成 {len(seed_bids)} 条 BidInfo",
                        timestamp,
                        status_code,
                        item_count=len(seed_bids),
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    return entry_bids
                self._record_diagnostic(
                    url,
                    "failed",
                    "HTTP 403/401: 疑似反爬或需要登录；如有授权 Cookie，请在配置中更新后重试",
                    timestamp,
                    status_code,
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids
            if status_code == 404 or status_code >= 500:
                seed_bids = self._try_topology_seed_fallback(url, timestamp, rule, cookie_used, stop_event=stop_event)
                if seed_bids:
                    entry_bids.extend(seed_bids)
                    self._record_diagnostic(
                        url,
                        "success",
                        f"入口 HTTP {status_code}，已按站点拓扑种子继续并生成 {len(seed_bids)} 条 BidInfo",
                        timestamp,
                        status_code,
                        item_count=len(seed_bids),
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    return entry_bids
                self._record_diagnostic(
                    url,
                    "failed",
                    "HTTP 404/5xx: 页面不存在或源站异常",
                    timestamp,
                    status_code,
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids
            if self._contains_blocked_sign(html, url):
                blocked_reason = self._blocked_reason(html, url)
                seed_bids = self._try_topology_seed_fallback(url, timestamp, rule, cookie_used, stop_event=stop_event)
                if seed_bids:
                    entry_bids.extend(seed_bids)
                    self._record_diagnostic(
                        url,
                        "success",
                        f"入口受限（{blocked_reason}），已按站点拓扑种子继续并生成 {len(seed_bids)} 条 BidInfo",
                        timestamp,
                        status_code,
                        item_count=len(seed_bids),
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    return entry_bids
                self._record_diagnostic(
                    url,
                    "failed",
                    blocked_reason,
                    timestamp,
                    status_code,
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids

            bids = self._crawl_topology_from_url(url, html, timestamp, rule, cookie_used, stop_event=stop_event)
            if not bids:
                self._record_diagnostic(
                    url,
                    "failed",
                    "页面可访问但无可识别公告链接/正文: 解析规则不足",
                    timestamp,
                    status_code,
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids

            entry_bids.extend(bids)
            self._record_diagnostic(
                url,
                "success",
                f"OK: 生成 {len(bids)} 条 BidInfo",
                timestamp,
                status_code,
                item_count=len(bids),
                cookie_used=cookie_used,
                rule=rule,
            )
            self.logger.info(f"[{self.name}] OK {url} -> {len(bids)} item(s)")
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            rule = locals().get("rule") or self._classify_url(url)
            seed_bids = self._try_topology_seed_fallback(url, timestamp, rule, cookie_used, stop_event=stop_event)
            if seed_bids:
                entry_bids.extend(seed_bids)
                self._record_diagnostic(
                    url,
                    "success",
                    f"入口请求异常（{exc.__class__.__name__}），已按站点拓扑种子继续并生成 {len(seed_bids)} 条 BidInfo",
                    timestamp,
                    item_count=len(seed_bids),
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids
            self._record_diagnostic(
                url,
                "failed",
                f"timeout/connection error: 网络不可达或站点不稳定 ({exc.__class__.__name__})",
                timestamp,
                cookie_used=cookie_used,
                rule=locals().get("rule"),
            )
            self.logger.warning(f"[{self.name}] Network failed {url}: {exc}")
        except requests.RequestException as exc:
            rule = locals().get("rule") or self._classify_url(url)
            seed_bids = self._try_topology_seed_fallback(url, timestamp, rule, cookie_used, stop_event=stop_event)
            if seed_bids:
                entry_bids.extend(seed_bids)
                self._record_diagnostic(
                    url,
                    "success",
                    f"入口请求异常（{exc.__class__.__name__}），已按站点拓扑种子继续并生成 {len(seed_bids)} 条 BidInfo",
                    timestamp,
                    item_count=len(seed_bids),
                    cookie_used=cookie_used,
                    rule=rule,
                )
                return entry_bids
            self._record_diagnostic(
                url,
                "failed",
                f"timeout/connection error: 网络不可达或站点不稳定 ({exc.__class__.__name__})",
                timestamp,
                cookie_used=cookie_used,
                rule=locals().get("rule"),
            )
            self.logger.warning(f"[{self.name}] Request failed {url}: {exc}")
        except Exception as exc:
            self._record_diagnostic(
                url,
                "failed",
                f"页面可访问但无可识别公告链接/正文: 解析规则不足 ({exc})",
                timestamp,
                cookie_used=cookie_used,
                rule=locals().get("rule"),
            )
            self.logger.warning(f"[{self.name}] Parse failed {url}: {exc}")
        finally:
            elapsed = time.monotonic() - entry_started_at
            self._emit_info(
                f"[URL进度] {self.name}: 完成 {index}/{total}，耗时 {elapsed:.1f}s，本入口 {len(entry_bids)} 条"
            )
        return entry_bids

    def _try_topology_seed_fallback(
        self,
        url: str,
        timestamp: str,
        rule: Dict[str, str],
        cookie_used: bool,
        stop_event=None,
    ) -> List[BidInfo]:
        if not self._topology_seed_links(url):
            return []
        return self._crawl_topology_from_url(url, "", timestamp, rule, cookie_used, stop_event=stop_event)

    def _crawl_topology_from_url(
        self,
        seed_url: str,
        seed_html: str,
        timestamp: str,
        seed_rule: Dict[str, str],
        cookie_used: bool = False,
        stop_event=None,
    ) -> List[BidInfo]:
        bids: List[BidInfo] = []
        queue: List[Tuple[str, int, Optional[str], str]] = [(seed_url, 0, seed_html, "")]
        visited: set[str] = set()
        self._emit_info(
            f"[URL拓扑] {self.name}: 开始 {self._short_url(seed_url)}，"
            f"最大详情 {self.max_detail_pages_per_seed}，每页候选 {self.max_follow_links_per_page}"
        )

        while queue and len(bids) < self.max_detail_pages_per_seed:
            if stop_event and stop_event.is_set():
                self.logger.info(f"[{self.name}] Topology crawl interrupted by stop signal")
                break
            page_url, depth, prefetched_html, expected_title = queue.pop(0)
            normalized_url = page_url.split("#", 1)[0]
            if normalized_url in visited:
                continue
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
            visited.add(normalized_url)
            self._emit_info(
                f"[URL拓扑] {self.name}: depth={depth} visited={len(visited)} "
                f"queue={len(queue)} bids={len(bids)}/{self.max_detail_pages_per_seed} "
                f"{self._short_url(page_url)}"
            )

            if prefetched_html is None:
                fetched = self._fetch_topology_page_with_domain_gate(page_url, timestamp, cookie_used)
                if fetched is None:
                    continue
                html, status_code, _status_text = fetched
            else:
                html = prefetched_html

            parsed_bids = self._parse_page(html, page_url, timestamp)
            if self._should_retry_browser_after_no_progress(page_url, prefetched_html) and not self._has_topology_progress(parsed_bids, page_url):
                self._emit_info(f"[URL浏览器] {self.name}: HTTP无进展，尝试浏览器 {self._short_url(page_url)}")
                browser_result = self._request_url_with_browser(page_url)
                if browser_result:
                    browser_html, browser_status, _browser_text = browser_result
                    if browser_status < 400 and not self._contains_blocked_sign(browser_html, page_url):
                        html = browser_html
                        parsed_bids = self._parse_page(html, page_url, timestamp)
            detail_bids: List[BidInfo] = []
            candidate_links: List[Dict[str, str]] = []

            for bid in parsed_bids:
                if bid.url == page_url and self._is_admissible_detail_bid(bid, page_url):
                    if self._should_use_candidate_title(bid.title, expected_title, page_url):
                        bid.title = expected_title
                    detail_bids.append(bid)
                    continue
                if bid.url != page_url:
                    candidate_links.append({"title": bid.title, "url": bid.url})

            self._emit_info(
                f"[URL解析] {self.name}: 当前页详情 {len(detail_bids)} 条，候选 {len(candidate_links)} 条，"
                f"{self._short_url(page_url)}"
            )

            for detail_bid in detail_bids:
                if len(bids) >= self.max_detail_pages_per_seed:
                    break
                bids.append(detail_bid)

            if depth >= self.topology_max_depth:
                continue

            candidate_links = self._merge_candidate_links(
                candidate_links,
                self._extract_candidate_links_from_html(html, page_url),
            )
            if depth == 0:
                candidate_links = self._merge_candidate_links(self._topology_seed_links(seed_url), candidate_links)
            enqueued = 0
            for link in candidate_links[: self.max_follow_links_per_page]:
                candidate_url = link.get("url", "")
                if not candidate_url or candidate_url.split("#", 1)[0] in visited:
                    continue
                if not self._should_follow_candidate(page_url, candidate_url, depth):
                    continue
                queue.append((candidate_url, depth + 1, None, link.get("title", "")))
                enqueued += 1
            if candidate_links:
                self._emit_info(
                    f"[URL拓扑] {self.name}: 入队 {enqueued}/{min(len(candidate_links), self.max_follow_links_per_page)}，"
                    f"队列剩余 {len(queue)}"
                )

        return bids

    def _topology_fetch_failure_reason(
        self,
        page_url: str,
        html: str,
        status_code: int,
        status_text: str,
    ) -> str:
        if status_code >= 400:
            return f"HTTP {status_code}: {status_text or 'detail fetch failed'}"
        return self._blocked_reason(html, page_url)

    def _fetch_topology_page_with_domain_gate(
        self,
        page_url: str,
        timestamp: str,
        cookie_used: bool,
    ) -> Optional[Tuple[str, int, str]]:
        with self._topology_fetch_gate(page_url):
            if self._is_domain_circuit_open(page_url):
                self._record_diagnostic(
                    page_url,
                    "failed",
                    "domain circuit open after repeated fetch failures",
                    timestamp,
                    cookie_used=cookie_used,
                    rule=self._classify_url(page_url),
                )
                return None
            browser_first = self._prefers_browser_fetch(page_url)
            browser_result = self._request_url_with_browser(page_url) if browser_first else None
            if browser_result:
                html, status_code, status_text = browser_result
            else:
                try:
                    self._respect_rate_limit(page_url)
                    html, status_code, status_text = self._request_url(page_url)
                except Exception as exc:
                    reason = f"{exc.__class__.__name__}: {exc}"
                    if self._should_retry_browser_for_fetch_failure(page_url):
                        browser_result = self._request_url_with_browser(page_url)
                        if browser_result:
                            html, status_code, status_text = browser_result
                        else:
                            self.logger.debug(f"[{self.name}] topology browser fallback failed {page_url}: {exc}")
                            self._record_topology_fetch_failure(page_url, reason, exc=exc)
                            return None
                    else:
                        self.logger.debug(f"[{self.name}] topology fetch failed {page_url}: {exc}")
                        self._record_topology_fetch_failure(page_url, reason, exc=exc)
                        return None
            if status_code >= 400 or self._contains_blocked_sign(html, page_url):
                failure_reason = self._topology_fetch_failure_reason(page_url, html, status_code, status_text)
                if self._should_retry_browser_for_fetch_failure(page_url):
                    browser_result = self._request_url_with_browser(page_url)
                    if browser_result:
                        html, status_code, status_text = browser_result
                        if status_code >= 400 or self._contains_blocked_sign(html, page_url):
                            self._record_topology_fetch_failure(
                                page_url,
                                self._topology_fetch_failure_reason(page_url, html, status_code, status_text),
                                status_code,
                                html=html,
                            )
                            return None
                    else:
                        self._record_topology_fetch_failure(
                            page_url,
                            failure_reason,
                            status_code,
                            html=html,
                        )
                        return None
                else:
                    self._record_topology_fetch_failure(
                        page_url,
                        failure_reason,
                        status_code,
                        html=html,
                    )
                    return None
            self._record_domain_fetch_success(page_url)
            return html, status_code, status_text

    def _record_topology_fetch_failure(
        self,
        page_url: str,
        reason: str,
        status_code: int = 0,
        html: str = "",
        exc: Exception | None = None,
    ) -> None:
        callback = getattr(self, "_topology_fetch_failure_callback", None)
        if callable(callback):
            callback(page_url, reason, status_code=status_code, html=html, exc=exc)
        self._record_domain_fetch_failure(page_url, reason, status_code=status_code)

    def _merge_candidate_links(self, *groups: List[Dict[str, str]]) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = []
        seen: set[str] = set()
        for group in groups:
            for link in group or []:
                url = (link.get("url") or "").split("#", 1)[0]
                if not url or url in seen:
                    continue
                seen.add(url)
                merged.append(link)
        return merged

    def _has_topology_progress(self, parsed_bids: List[BidInfo], page_url: str) -> bool:
        for bid in parsed_bids:
            if bid.url != page_url:
                return True
            if self._is_admissible_detail_bid(bid, page_url):
                return True
        return False

    def _load_site_topologies(self, path: str) -> List[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            self.logger.warning(f"[{self.name}] Failed to load site topologies {path}: {exc}")
            return []
        records = payload.get("sites") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        return [record for record in records if isinstance(record, dict)]

    def _topology_for_url(self, url: str) -> Optional[Dict[str, Any]]:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        if not host:
            return None
        best: Optional[Dict[str, Any]] = None
        best_score = -1
        for topology in self.site_topologies:
            hosts = self._topology_allowed_hosts(topology)
            score = 0
            if any(self._host_matches(host, allowed) for allowed in hosts):
                score = 1
            entry_host = urlparse(str(topology.get("entry_url", ""))).netloc.lower().split(":")[0]
            if entry_host and host == entry_host:
                score = 3
            if score > best_score:
                best = topology
                best_score = score
        return best if best_score > 0 else None

    def _topology_requires_strict_detail_urls(self, topology: Optional[Dict[str, Any]]) -> bool:
        if not topology:
            return False
        strict_value = topology.get("strict_detail_urls")
        if strict_value is not None:
            return bool(strict_value)
        return bool(topology.get("detail_url_regex"))

    def _topology_allowed_hosts(self, topology: Dict[str, Any]) -> List[str]:
        hosts = [str(host).lower() for host in topology.get("allowed_hosts", []) if host]
        for key in ("entry_url", "url"):
            entry_host = urlparse(str(topology.get(key, ""))).netloc.lower().split(":")[0]
            if entry_host:
                hosts.append(entry_host)
        return list(dict.fromkeys(hosts))

    def _host_matches(self, host: str, allowed: str) -> bool:
        allowed = allowed.lower().strip()
        if not allowed:
            return False
        if allowed.startswith("*."):
            suffix = allowed[1:]
            return host.endswith(suffix)
        return host == allowed

    def _is_allowed_topology_host(self, source_url: str, candidate_url: str) -> bool:
        source_host = urlparse(source_url).netloc.lower().split(":")[0]
        candidate_host = urlparse(candidate_url).netloc.lower().split(":")[0]
        if not source_host or not candidate_host:
            return False
        if source_host == candidate_host:
            return True
        topology = self._topology_for_url(source_url) or self._topology_for_url(candidate_url)
        if not topology:
            return False
        allowed_hosts = self._topology_allowed_hosts(topology)
        return any(self._host_matches(source_host, allowed) for allowed in allowed_hosts) and any(
            self._host_matches(candidate_host, allowed) for allowed in allowed_hosts
        )

    def _topology_seed_links(self, seed_url: str) -> List[Dict[str, str]]:
        topology = self._topology_for_url(seed_url)
        if not topology:
            return []
        links: List[Dict[str, str]] = []
        for raw_url in topology.get("seed_urls", []) or []:
            if not raw_url:
                continue
            if "{" in str(raw_url) or "}" in str(raw_url):
                continue
            url = urljoin(seed_url, str(raw_url))
            if url.rstrip("/") == seed_url.rstrip("/"):
                continue
            links.append({"title": str(raw_url), "url": url})
        return links

    def _read_txt_urls(self) -> List[str]:
        with open(self.file_path, "r", encoding="utf-8-sig") as f:
            return [line.strip() for line in f]

    def _read_csv_urls(self) -> List[str]:
        urls: List[str] = []
        with open(self.file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return urls

            url_field = self._find_url_column(reader.fieldnames)
            for row in reader:
                if url_field:
                    urls.append(row.get(url_field, ""))
                    continue
                for value in row.values():
                    if self._looks_like_url(value):
                        urls.append(value)
                        break
        return urls

    def _find_url_column(self, fieldnames: List[str]) -> Optional[str]:
        for field in fieldnames:
            if field and field.strip().lower() == "url":
                return field
        return None

    def _clean_url(self, value: Any) -> Optional[str]:
        if not value:
            return None
        value = str(value).strip().strip('"').strip("'")
        if not self._looks_like_url(value):
            return None
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return value

    def _looks_like_url(self, value: Any) -> bool:
        if not value:
            return False
        return bool(re.match(r"^https?://[^\s]+$", str(value).strip(), re.IGNORECASE))

    def _request_url(self, url: str) -> Tuple[str, int, str]:
        if self.session is None:
            raise requests.RequestException("requests is required for HTTP fetching. Install requirements.txt.")
        headers = self._get_headers()
        cookie = self._get_cookie_for_url(url)
        if cookie:
            headers["Cookie"] = cookie

        started_at = time.monotonic()
        self._emit_info(f"[URL请求] {self.name}: HTTP GET {self._short_url(url)}")
        try:
            response = self.session.get(
                url,
                headers=headers,
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

    def _request_url_with_browser(self, url: str) -> Optional[Tuple[str, int, str]]:
        try:
            from crawler.browser import create_browser_crawler
        except Exception as exc:
            self.logger.debug(f"[{self.name}] browser backend import failed: {exc}")
            return None

        with self._browser_fetch_lock:
            crawler = create_browser_crawler(self.config, self.name, url, headless=True)
            if crawler is None:
                return None
            self._emit_info(f"[URL浏览器] {self.name}: 开始渲染 {self._short_url(url)}")
            started_at = time.monotonic()
            html = crawler.fetch(url)
            if not html:
                self._emit_info(f"[URL浏览器] {self.name}: 渲染失败，耗时 {time.monotonic() - started_at:.1f}s {self._short_url(url)}")
                return None
            self._emit_info(
                f"[URL浏览器] {self.name}: 渲染完成，{len(html)} 字符，耗时 {time.monotonic() - started_at:.1f}s {self._short_url(url)}"
            )
            return html, 200, "Browser"

    def _browser_mode_enabled(self) -> bool:
        browser_backend = self.config.get("browser_backend") or {}
        mode = browser_backend.get("mode")
        return bool(self.config.get("use_selenium") or mode in {"browser_auto", "browser", "browser_cloak", "browser_selenium"})

    def _prefers_browser_fetch(self, url: str) -> bool:
        if not self._browser_mode_enabled():
            return False
        browser_backend = self.config.get("browser_backend") or {}
        mode = browser_backend.get("mode")
        if mode in {"browser", "browser_cloak", "browser_selenium"}:
            return True
        topology = self._topology_for_url(url)
        preferred_fetch = str((topology or {}).get("preferred_fetch", "")).lower()
        return "browser" in preferred_fetch

    def _should_retry_browser_after_no_progress(self, url: str, prefetched_html: Optional[str]) -> bool:
        if not self._browser_mode_enabled():
            return False
        if prefetched_html == "" and self._topology_seed_links(url):
            return False
        topology = self._topology_for_url(url)
        if not topology:
            return True
        if self._prefers_browser_fetch(url):
            return True
        rule = self._classify_url(url)
        return rule.get("handling") == "js_rendered_limited"

    def _should_retry_browser_for_fetch_failure(self, url: str) -> bool:
        if not self._browser_mode_enabled():
            return False
        if self._prefers_browser_fetch(url):
            return True
        topology = self._topology_for_url(url)
        if not topology:
            return True
        rule = self._classify_url(url)
        if rule.get("page_type") == "detail":
            return True
        return rule.get("handling") == "js_rendered_limited"

    def _fetch_and_extract_candidate_links(self, url: str, timestamp: str, cookie_used: bool = False) -> List[Dict[str, str]]:
        self._respect_rate_limit(url)
        html, status_code, _status_text = self._request_url(url)
        links: List[Dict[str, str]] = []
        if status_code < 400 and not self._contains_blocked_sign(html, url):
            links = self._extract_candidate_links_from_html(html, url)
        if not links and self._browser_mode_enabled():
            browser_result = self._request_url_with_browser(url)
            if browser_result:
                browser_html, browser_status, _browser_text = browser_result
                if browser_status < 400 and not self._contains_blocked_sign(browser_html, url):
                    links = self._extract_candidate_links_from_html(browser_html, url)
        return links[: self.max_follow_links_per_page]

    def _get_cookie_for_url(self, url: str) -> Optional[str]:
        host = urlparse(url).netloc.lower().split(":")[0]
        for item in self.auth_cookies:
            if not item.get("enabled", True):
                continue
            domain = str(item.get("domain", "")).lower().lstrip(".")
            cookie = item.get("cookie", "")
            if domain and cookie and (host == domain or host.endswith(f".{domain}")):
                return cookie
        return None

    def _respect_rate_limit(self, url: str) -> None:
        if self.domain_delay <= 0:
            return

        host = urlparse(url).netloc.lower().split(":")[0]
        if not host:
            return

        with self._domain_lock(host):
            now = time.monotonic()
            last_seen = self._last_domain_request_at.get(host)
            if last_seen is not None:
                wait_seconds = self.domain_delay - (now - last_seen)
                if wait_seconds > 0:
                    self._emit_info(f"[URL限频] {self.name}: {host} 等待 {wait_seconds:.1f}s")
                    time.sleep(wait_seconds)
            self._last_domain_request_at[host] = time.monotonic()

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
        blocked_failure = blocked_failure or any(
            term in reason.lower() for term in ["timeout", "blocked", "captcha", "origin down"]
        )
        if not blocked_failure:
            return
        message = None
        with self._domain_failure_lock:
            count = self._domain_failure_counts.get(host, 0) + 1
            self._domain_failure_counts[host] = count
            if count >= self.domain_failure_threshold:
                self._domain_circuit_open.add(host)
                message = f"[URL熔断] {self.name}: {host} 连续失败 {count} 次，本轮跳过后续同域请求"
        if message:
            self._emit_info(message)

    def _topology_fetch_gate(self, url: str) -> threading.Lock:
        host = self._domain_key(url)
        if not host:
            return threading.Lock()
        with self._topology_fetch_gates_guard:
            gate = self._topology_fetch_gates.get(host)
            if gate is None:
                gate = threading.Lock()
                self._topology_fetch_gates[host] = gate
            return gate

    def _domain_lock(self, host: str) -> threading.Lock:
        with self._domain_locks_guard:
            lock = self._domain_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._domain_locks[host] = lock
            return lock

    def _parse_page(self, html: str, page_url: str, timestamp: str) -> List[BidInfo]:
        rule = self._classify_url(page_url)
        api_bids = self._parse_json_records(html, page_url, timestamp, rule)
        if api_bids:
            return api_bids

        soup = self._parse_html_document(html)
        if rule["page_type"] == "detail":
            detail_bid = self._extract_detail_bid(soup, page_url, timestamp, rule)
            if detail_bid:
                return [detail_bid]

        link_bids = self._extract_announcement_links(soup, page_url, timestamp, rule)
        if link_bids and rule["page_type"] != "detail":
            return link_bids

        if rule["page_type"] != "detail":
            return []

        title = self._extract_title(soup, page_url)
        content = self._extract_content_summary(soup)
        if not title and not content:
            return []

        fields = self._extract_text_fields(f"{title}\n{content}")
        fields.setdefault("project_stage", self._detect_project_stage([rule.get("platform", ""), title, content]))
        return [
            BidInfo(
                title=title or page_url,
                url=page_url,
                publish_date=fields.get("publish_date") or self._fallback_publish_date(),
                source=self.name,
                content=self._with_metadata(content, page_url, timestamp, fields, rule),
                purchaser=fields.get("purchaser", ""),
            )
        ]

    def _extract_candidate_links_from_html(self, html: str, page_url: str) -> List[Dict[str, str]]:
        soup = self._parse_html_document(html)
        rule = self._classify_url(page_url)
        candidates: List[Dict[str, str]] = []
        seen: set[str] = set()
        for bid in self._extract_announcement_links(soup, page_url, datetime.now().isoformat(timespec="seconds"), rule):
            if not self._is_valid_traversal_url(bid.url):
                continue
            if bid.url in seen:
                continue
            seen.add(bid.url)
            candidates.append({"title": bid.title, "url": bid.url})

        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            href = a.get("href", "").strip()
            if not href or href.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            full_url = urljoin(page_url, href)
            if not self._is_valid_traversal_url(full_url):
                continue
            if full_url in seen:
                continue
            if self._is_traversal_link(text, full_url, page_url):
                seen.add(full_url)
                candidates.append({"title": text or full_url, "url": full_url})
        for link in self._extract_topology_attribute_links(html, page_url):
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            candidates.append(link)
        return candidates

    def _extract_topology_attribute_links(self, html: str, page_url: str) -> List[Dict[str, str]]:
        topology = self._topology_for_url(page_url)
        if not topology or not html:
            return []
        candidates: List[Dict[str, str]] = []
        seen: set[str] = set()
        attr_re = re.compile(
            r"(?P<attr>href|rec_link|data-url|data-href)\s*=\s*['\"](?P<url>[^'\"]+)['\"]",
            re.IGNORECASE,
        )
        title_re = re.compile(
            r"(?:rec_title|title|data-title)\s*=\s*['\"](?P<title>[^'\"]+)['\"]",
            re.IGNORECASE,
        )
        for match in attr_re.finditer(html):
            raw_url = match.group("url").strip()
            if not raw_url or raw_url.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            full_url = urljoin(page_url, raw_url)
            if not self._is_valid_traversal_url(full_url):
                continue
            if full_url in seen or not self._is_allowed_topology_host(page_url, full_url):
                continue
            if not self._classify_url_by_topology(full_url, topology) and not self._is_traversal_link("", full_url, page_url):
                continue
            tag_start = html.rfind("<", 0, match.start())
            tag_end = html.find(">", match.end())
            tag_text = html[tag_start:tag_end + 1] if tag_start >= 0 and tag_end >= 0 else ""
            title_match = title_re.search(tag_text)
            title = title_match.group("title").strip() if title_match else full_url
            seen.add(full_url)
            candidates.append({"title": title, "url": full_url})
        for match in re.finditer(
            r"urlChange\(\s*['\"](?P<gg>[^'\"]+)['\"]\s*,\s*['\"](?P<gc>[^'\"]+)['\"]\s*\)",
            html,
            re.IGNORECASE,
        ):
            detail_url = urljoin(page_url, f"/cgxx/ggDetail?gcGuid={match.group('gc')}&ggGuid={match.group('gg')}")
            if detail_url in seen or not self._is_allowed_topology_host(page_url, detail_url):
                continue
            if not self._classify_url_by_topology(detail_url, topology):
                continue
            title = self._text_near_html_match(html, match.start(), match.end()) or detail_url
            seen.add(detail_url)
            candidates.append({"title": title, "url": detail_url})
        for match in re.finditer(
            r"noticeDetail\(\s*['\"](?P<id>[A-Za-z0-9_-]+)['\"]\s*\)",
            html,
            re.IGNORECASE,
        ):
            detail_url = urljoin(page_url, f"/baseinfor/notice/informationShow?id={match.group('id')}")
            if detail_url in seen or not self._is_allowed_topology_host(page_url, detail_url):
                continue
            if not self._classify_url_by_topology(detail_url, topology):
                continue
            title = self._text_near_html_match(html, match.start(), match.end()) or detail_url
            seen.add(detail_url)
            candidates.append({"title": title, "url": detail_url})
        for match in re.finditer(r"['\"](?P<url>https?://[^'\"]+)['\"]", html, re.IGNORECASE):
            full_url = match.group("url").strip()
            if not self._is_valid_traversal_url(full_url):
                continue
            if full_url in seen or not self._is_allowed_topology_host(page_url, full_url):
                continue
            if not self._classify_url_by_topology(full_url, topology):
                continue
            title = self._title_near_json_url(html, match.start(), match.end()) or full_url
            seen.add(full_url)
            candidates.append({"title": title, "url": full_url})
        return candidates

    def _text_near_html_match(self, html: str, start: int, end: int) -> str:
        tag_start = html.rfind("<", 0, start)
        tag_end = html.find(">", end)
        if tag_start < 0 or tag_end < 0:
            return ""
        snippet = html[tag_start:tag_end + 1]
        text = re.sub(r"<[^>]+>", " ", snippet)
        return self._normalize_space(text)

    def _title_near_json_url(self, html: str, start: int, end: int) -> str:
        window = html[max(0, start - 500):min(len(html), end + 500)]
        for pattern in [
            r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            r"['\"]noticeTitle['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            r"['\"]projectName['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        ]:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                return self._normalize_space(match.group(1))
        return ""

    def _is_valid_traversal_url(self, url: str) -> bool:
        if not url:
            return False
        if "{" in url or "}" in url or "${" in url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        path_lower = parsed.path.lower()
        query_lower = parsed.query.lower()
        fragment_lower = parsed.fragment.lower()
        if self._is_login_route(path_lower, query_lower, fragment_lower):
            return False
        _, ext = os.path.splitext(path_lower.rstrip("/"))
        if ext in STATIC_OR_BINARY_EXTENSIONS:
            return False
        raw_query_values = [
            part.partition("=")[2] if "=" in part else part
            for part in parsed.query.split("&")
            if part
        ]
        decoded_query_values = [value for _, value in parse_qsl(parsed.query, keep_blank_values=True)]
        for value in raw_query_values + decoded_query_values:
            for candidate in {value, unquote(value)}:
                candidate_path = urlparse(candidate).path.lower()
                _, candidate_ext = os.path.splitext(candidate_path.rstrip("/"))
                if candidate_ext in STATIC_OR_BINARY_EXTENSIONS:
                    return False
        path_and_query = f"{path_lower}?{query_lower}"
        if any(term in path_and_query for term in DOWNLOAD_PATH_TERMS):
            return False
        return True

    def _is_traversal_link(self, text: str, url: str, page_url: str) -> bool:
        if not self._is_valid_traversal_url(url):
            return False
        parsed = urlparse(url)
        seed = urlparse(page_url)
        if parsed.netloc and seed.netloc and not self._is_allowed_topology_host(page_url, url):
            return False
        lowered = f"{parsed.path.lower()}?{parsed.query.lower()}"
        if self._is_detail_url(parsed.path.lower(), parsed.query.lower()):
            return True
        if any(term in lowered for term in ["/search", "keyword", "category", "/list", "/notice", "/cggg/", "/zb", "/bidweb", "/cgxx"]):
            return True
        if any(term in (text or "") for term in ["招标", "采购", "公告", "中标", "结果", "项目", "工程", "安防", "弱电", "监控"]):
            return not any(keyword in text.lower() for keyword in NEGATIVE_LINK_KEYWORDS)
        return any(keyword in text for keyword in BID_LINK_KEYWORDS) and not any(
            keyword in text.lower() for keyword in NEGATIVE_LINK_KEYWORDS
        )

    def _should_follow_candidate(self, page_url: str, candidate_url: str, depth: int) -> bool:
        if not self._is_valid_traversal_url(candidate_url):
            return False
        if not self._is_allowed_topology_host(page_url, candidate_url):
            return False
        rule = self._classify_url(candidate_url)
        if rule.get("page_type") == "login" or rule.get("handling") == "requires_login":
            return False
        return rule.get("page_type") in {"detail", "list", "search", "home"} or depth + 1 <= self.topology_max_depth

    def _is_admissible_detail_bid(self, bid: BidInfo, page_url: str) -> bool:
        rule = self._classify_url(page_url)
        text = self._normalize_space(f"{bid.title} {bid.content}")
        if self._contains_blocked_sign(text, page_url):
            return False
        if self._looks_like_navigation_page(text):
            return False
        if rule.get("page_type") != "detail":
            return False
        if rule.get("page_type") == "detail":
            return self._has_detail_evidence(text, allow_minimal=True)
        return False

    def _should_use_candidate_title(self, current_title: str, candidate_title: str, page_url: str) -> bool:
        candidate_title = self._normalize_space(candidate_title)
        current_title = self._normalize_space(current_title)
        if len(candidate_title) < 6 or not self._has_strong_bid_stage(candidate_title):
            return False
        if not current_title or current_title == page_url or self._looks_like_url(current_title):
            return True
        if self._has_strong_bid_stage(current_title):
            return False
        return True

    def _has_strong_bid_stage(self, text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "公开招标",
                "招标公告",
                "采购公告",
                "中标公告",
                "成交公告",
                "结果公告",
                "更正公告",
                "竞争性磋商",
                "竞争性谈判",
                "询价公告",
                "采购意向",
            ]
        )

    def _has_detail_evidence(self, text: str, allow_minimal: bool = False) -> bool:
        if not text:
            return False
        title_signal = any(keyword in text for keyword in BID_LINK_KEYWORDS)
        field_signals = [
            "发布时间",
            "发布日期",
            "采购单位",
            "采购人",
            "招标人",
            "项目编号",
            "项目名称",
            "预算金额",
            "公告正文",
            "正文内容",
            "投标截止",
            "开标时间",
        ]
        field_count = sum(1 for field in field_signals if field in text)
        if title_signal and field_count >= 2:
            return True
        if not allow_minimal or not title_signal:
            return False

        stage_signal = self._has_strong_bid_stage(text)
        subject_signal = any(
            keyword in text
            for keyword in [
                "本项目",
                "项目",
                "工程",
                "系统",
                "设备",
                "服务",
                "预算",
                "安防",
                "监控",
                "门禁",
                "弱电",
                "智能化",
                "综合布线",
            ]
        )
        return stage_signal and subject_signal and len(text) >= 12

    def _looks_like_navigation_page(self, text: str) -> bool:
        nav_terms = [
            "首页",
            "招标中心",
            "项目中心",
            "数据中心",
            "服务中心",
            "高级搜索",
            "热点搜索",
            "上一页",
            "下一页",
            "尾页",
            "共",
            "搜索",
        ]
        return sum(1 for term in nav_terms if term in text) >= 4

    def _parse_html_document(self, html: str):
        try:
            return self.parse_html(html)
        except RuntimeError:
            return _MiniSoup(html)

    def _classify_url(self, url: str) -> Dict[str, str]:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        path = parsed.path.lower()
        query = parsed.query.lower()
        fragment = parsed.fragment.lower()
        host_key = host[4:] if host.startswith("www.") else host
        topology = self._topology_for_url(url)

        platform_map = {
            "zfcg.sh.gov.cn": "上海政府采购",
            "home.zfcg.sh.gov.cn": "上海政府采购云平台",
            "shzfcg.gov.cn": "上海政府采购",
            "ccgp-shanghai.gov.cn": "上海政府采购",
            "ccgp.gov.cn": "中国政府采购网",
            "cgzx.jgj.sh.gov.cn": "上海市政府采购中心",
            "zcb.sjtu.edu.cn": "上海交通大学采购平台",
            "jiading.gov.cn": "嘉定教育通知公告",
            "qianlima.com": "千里马招标网",
            "bidcenter.com.cn": "采招网",
            "chinabidding.com": "中国采购与招标网",
            "bidchance.com": "中国招标网",
            "cebpubservice.com": "中国招标投标公共服务平台",
            "chnenergybidding.com.cn": "国家能源招标网",
            "plap.mil.cn": "军队采购网",
            "cg.95306.cn": "国铁采购平台",
            "neep.shop": "国能 e 购",
            "sdicc.com.cn": "国投集团电子采购平台",
            "jianyu360.com": "剑鱼招标订阅",
            "bidizhaobiao.com": "比地招标网",
            "jszhaobiao.com.cn": "建设招标网",
            "jszhaobiao.com": "建设招标网",
            "okcis.cn": "导航网",
            "tianyancha.com": "天眼查招投标",
            "rccchina.com": "RCC 瑞达恒",
            "afzhan.com": "安防展览网",
            "case.afzhan.com": "安防案例",
            "caigou.com.cn": "教育装备采购网",
            "newproduct.caigou.com.cn": "教育装备新品",
            "solution.caigou.com.cn": "教育装备方案",
            "ecta.org.cn": "教育技术协会",
            "project.ecta.org.cn": "教育技术项目",
            "ceiea.org.cn": "中国教育装备行业协会",
            "zy.ceiea.org.cn": "教育装备资源",
            "architect.org.cn": "建筑项目参考",
            "chinabuilding.com.cn": "中国建筑信息",
            "ciac.sh.cn": "上海建设行业",
            "cpta.com.cn": "考试资讯",
            "eol.cn": "中国教育在线",
            "sheitc.gov.cn": "上海经信委",
            "biaozhilian.com": "标志链",
            "biaoshu.xiaoxiaoai.cn": "AI 标书工具",
            "xiquebiaoshu.com": "AI 标书工具",
            "mp.weixin.qq.com": "微信文章",
            "wenshu.court.gov.cn": "裁判文书网",
            "sd-portygzc.com": "山东港口阳光采购",
            "cooperation.ceic.com": "国家能源集团生态协作平台",
            "sxtsrm.sngbs.com.cn": "陕西天然气 SRM",
        }
        platform = str(topology.get("name")) if topology and topology.get("name") else platform_map.get(
            host_key, platform_map.get(host, host or "未知平台")
        )

        handling = "public_crawl"
        reason = "公开页面，按 URL 清单通用规则抓取公告链接或详情"
        is_login_route = self._is_login_route(path, query, fragment)
        if host_key in {"biaoshu.xiaoxiaoai.cn", "xiquebiaoshu.com"}:
            handling = "low_value_reference"
            reason = "AI 标书工具页面，不是公告源；仅记录为低价值参考并尝试公开链接 fallback"
        elif host_key in {"wenshu.court.gov.cn"}:
            handling = "low_value_reference"
            reason = "裁判文书站点不是招投标公告源，作为低价值参考处理"
        elif host_key in {"sd-portygzc.com", "cooperation.ceic.com", "sxtsrm.sngbs.com.cn"} or is_login_route:
            handling = "requires_login"
            reason = "登录/SSO 页面，需要账号授权；不绕过登录或验证码"
        elif host_key in {"tianyancha.com", "rccchina.com"}:
            handling = "commercial_limited"
            reason = "商业聚合平台，公开内容有限；只抓公开链接，不绕过会员限制"
        elif host == "user.bidcenter.com.cn" or "customdessearch" in fragment:
            handling = "js_rendered_limited"
            reason = "前端路由搜索页，保留查询参数并仅用静态 HTML/公开链接 fallback"
        elif host_key in {"neep.shop", "cg.95306.cn"}:
            handling = "js_rendered_limited"
            reason = "行业电子采购平台可能依赖前端渲染；静态可见内容优先，失败则诊断"

        topology_page_type = self._classify_url_by_topology(url, topology)
        if topology_page_type:
            page_type = topology_page_type
        elif topology and self._topology_requires_strict_detail_urls(topology):
            if self._is_api_url(path, query):
                page_type = "api"
            elif is_login_route:
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
        elif is_login_route:
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

        return {
            "platform": platform,
            "page_type": page_type,
            "handling": handling,
            "reason": reason,
            "topology_id": str(topology.get("id", "")) if topology else "",
        }

    def _classify_url_by_topology(self, url: str, topology: Optional[Dict[str, Any]]) -> Optional[str]:
        if not topology:
            return None
        if self._matches_any_pattern(url, topology.get("detail_url_regex")):
            return "detail"
        if self._matches_any_pattern(url, topology.get("list_url_regex")):
            return "list"
        if self._matches_any_pattern(url, topology.get("search_url_regex")):
            return "search"
        return None

    def _matches_any_pattern(self, value: str, patterns: Any) -> bool:
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list):
            return False
        parsed = urlparse(value)
        targets = [value, parsed.path, f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path]
        for pattern in patterns:
            if not pattern:
                continue
            try:
                compiled = re.compile(str(pattern), re.IGNORECASE)
            except re.error:
                continue
            if any(compiled.search(target) for target in targets):
                return True
        return False

    def _is_api_url(self, path: str, query: str) -> bool:
        return "/api/" in path or path.endswith(".json") or "format=json" in query

    def _is_login_url(self, path: str, query: str) -> bool:
        return self._matches_login_route(path) or "response_type=code" in query

    def _is_login_route(self, path: str, query: str, fragment: str) -> bool:
        return (
            self._matches_login_route(path)
            or self._matches_login_route(fragment)
            or "response_type=code" in query
            or "response_type=code" in fragment
        )

    def _matches_login_route(self, route: str) -> bool:
        segments = self._route_segments(route)
        if not segments:
            return False
        single_segment_terms = {"login", "signin", "auth", "sso", "login_bidder", "memberlogin"}
        if any(segment in single_segment_terms for segment in segments):
            return True
        multi_segment_terms = [("user", "login"), ("default", "login")]
        return any(self._has_segment_window(segments, term) for term in multi_segment_terms)

    def _route_segments(self, route: str) -> List[str]:
        normalized = route.lower().strip().replace("\\", "/")
        segments = []
        for segment in re.split(r"[/?#&=]+", normalized):
            if not segment:
                continue
            basename, ext = os.path.splitext(segment)
            if ext in {".htm", ".html", ".jsp", ".aspx"} and basename:
                segments.append(basename)
            else:
                segments.append(segment)
        return segments

    def _has_segment_window(self, segments: List[str], term: Tuple[str, ...]) -> bool:
        width = len(term)
        return any(tuple(segments[index:index + width]) == term for index in range(len(segments) - width + 1))

    def _is_detail_url(self, path: str, query: str) -> bool:
        filename = os.path.basename(path.rstrip("/"))
        if filename in {"index.htm", "index.html", "notice.html", "list.html", "search.html"}:
            return False
        if re.match(r"index_\d+\.html?$", filename):
            return False
        detail_terms = [
            "/detail",
            "articledetail",
            "articleid=",
            "informationshow",
            "ggdetail",
            "noticedetail",
            "notice-detail",
            "result-detail",
            "bid-",
            "news-",
            "/info-",
            "/t20",
            ".htm",
            ".html",
        ]
        if path in ("", "/", "/index.html"):
            return False
        return any(term in f"{path}?{query}" for term in detail_terms)

    def _is_search_url(self, path: str, query: str, fragment: str) -> bool:
        search_text = f"{path}?{query}#{fragment}"
        return any(term in search_text for term in ["search", "keyword", "keywords", "customdessearch", "bidding"])

    def _is_list_url(self, path: str) -> bool:
        list_terms = [
            "/cggg/",
            "/tzgg/",
            "/gg",
            "/bidweb",
            "/projects",
            "/zby",
            "/notice",
            "/list",
            "/zbgg",
            "/zbmf",
            "/zbpage",
            "/site/category",
            "/baseinfor/notice/tobuynoticemore",
            "/cgxx/cgxxlist",
            "/freecms-glht/",
        ]
        return any(term in path for term in list_terms)

    def _should_skip_before_fetch(self, rule: Dict[str, str]) -> bool:
        return rule.get("handling") == "requires_login" and rule.get("page_type") == "login"

    def _parse_json_records(
        self, raw_text: str, page_url: str, timestamp: str, rule: Dict[str, str]
    ) -> List[BidInfo]:
        text = (raw_text or "").strip()
        if not text or text[0] not in "[{":
            return []
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return []

        records = self._find_json_records(payload)
        bids: List[BidInfo] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            title = self._first_json_value(record, TITLE_FIELDS)
            if not title:
                continue
            detail_url = self._first_json_value(record, URL_FIELDS) or page_url
            detail_url = urljoin(page_url, str(detail_url))
            content = self._first_json_value(record, CONTENT_FIELDS) or ""
            notice_type = self._first_json_value(record, TYPE_FIELDS) or ""
            publisher = self._first_json_value(record, SOURCE_FIELDS) or ""
            fields = self._extract_text_fields(f"{notice_type}\n{publisher}\n{title}\n{content}")
            fields["project_stage"] = self._detect_project_stage([notice_type, title, content])
            if publisher:
                fields["publisher"] = str(publisher)
            fields["page_type"] = rule["page_type"]
            fields["handling"] = rule["handling"]
            fields["platform"] = rule["platform"]

            publish_date = self._normalize_date(self._first_json_value(record, DATE_FIELDS)) or fields.get("publish_date")
            purchaser = self._first_json_value(record, PURCHASER_FIELDS) or fields.get("purchaser", "")
            bids.append(
                BidInfo(
                    title=str(title).strip(),
                    url=detail_url,
                    publish_date=publish_date or self._fallback_publish_date(),
                    source=self.name,
                    content=self._with_metadata(str(content), page_url, timestamp, fields, rule),
                    purchaser=str(purchaser).strip(),
                )
            )
            if len(bids) >= self.max_links_per_page:
                break
        return bids

    def _find_json_records(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        for key in ("records", "list", "items", "rows", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._find_json_records(value)
                if nested:
                    return nested
        return [payload] if self._first_json_value(payload, TITLE_FIELDS) else []

    def _first_json_value(self, record: Dict[str, Any], fields: List[str]) -> str:
        lowered = {str(key).lower(): value for key, value in record.items()}
        for field in fields:
            if field in record and record[field] not in (None, ""):
                return str(record[field])
            value = lowered.get(field.lower())
            if value not in (None, ""):
                return str(value)
        return ""

    def _extract_detail_bid(self, soup, page_url: str, timestamp: str, rule: Dict[str, str]) -> Optional[BidInfo]:
        title = self._extract_title(soup, page_url)
        content = self._extract_content_summary(soup, limit=6000)
        if not title and not content:
            return None

        fields = self._extract_text_fields(f"{title}\n{content}")
        fields["project_stage"] = self._detect_project_stage([rule.get("platform", ""), title, content])
        fields["page_type"] = rule["page_type"]
        fields["handling"] = rule["handling"]
        fields["platform"] = rule["platform"]
        publish_date = fields.get("publish_date") or self._fallback_publish_date()
        return BidInfo(
            title=title or page_url,
            url=page_url,
            publish_date=publish_date,
            source=self.name,
            content=self._with_metadata(content, page_url, timestamp, fields, rule),
            purchaser=fields.get("purchaser", ""),
        )

    def _extract_announcement_links(
        self, soup, page_url: str, timestamp: str, rule: Optional[Dict[str, str]] = None
    ) -> List[BidInfo]:
        bids: List[BidInfo] = []
        seen = set()
        rule = rule or self._classify_url(page_url)
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if len(text) < 6:
                continue
            if any(keyword in text.lower() for keyword in NEGATIVE_LINK_KEYWORDS):
                continue
            if not any(keyword in text for keyword in BID_LINK_KEYWORDS):
                continue

            href = a.get("href", "").strip()
            if not href or href.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            full_url = urljoin(page_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            context = self._node_context_text(a)
            publish_date = self._extract_date(context) or self._fallback_publish_date()
            fields = {
                "project_stage": self._detect_project_stage([text, context, rule.get("platform", "")]),
                "page_type": rule["page_type"],
                "handling": rule["handling"],
                "platform": rule["platform"],
            }
            bids.append(
                BidInfo(
                    title=text,
                    url=full_url,
                    publish_date=publish_date,
                    source=self.name,
                    content=self._with_metadata("", page_url, timestamp, fields, rule),
                )
            )
            if len(bids) >= self.max_links_per_page:
                break
        return bids

    def _extract_title(self, soup, page_url: str) -> str:
        for selector in ["h1", "title", "h2"]:
            node = soup.find(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    text = re.sub(r"[-_]\s*(中国政府采购网|上海政府采购网|上海政府采购)", "", text).strip()
                    return text
        return page_url

    def _extract_content_summary(self, soup, limit: int = 3000) -> str:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:limit]

    def _extract_text_fields(self, text: str) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        clean_text = self._normalize_space(text)
        publish_date = self._extract_labeled_value(clean_text, PUBLISH_DATE_LABELS, value_pattern=DATE_RE.pattern)
        fields["publish_date"] = self._normalize_date(publish_date) or self._extract_date(clean_text)

        publisher = self._extract_labeled_value(clean_text, SOURCE_LABELS)
        if publisher:
            fields["publisher"] = publisher

        purchaser = self._extract_labeled_value(clean_text, PURCHASER_LABELS)
        if purchaser:
            fields["purchaser"] = purchaser

        contact_person = self._extract_person_values(clean_text, CONTACT_PERSON_LABELS)
        if contact_person:
            fields["contact_person"] = self._join_unique(contact_person)

        contact_methods = self._extract_contact_methods(clean_text, CONTACT_METHOD_LABELS)
        if contact_methods:
            fields["contact_phone"] = self._join_unique(contact_methods)

        responsible_person = self._extract_person_values(clean_text, RESPONSIBLE_PERSON_LABELS)
        if responsible_person:
            fields["responsible_person"] = self._join_unique(responsible_person)

        responsible_methods = self._extract_contact_methods(clean_text, RESPONSIBLE_METHOD_LABELS)
        if responsible_methods:
            fields["responsible_phone"] = self._join_unique(responsible_methods)
        return {key: value for key, value in fields.items() if value}

    def _extract_labeled_value(self, text: str, labels: List[str], value_pattern: Optional[str] = None) -> str:
        for label in labels:
            if value_pattern:
                pattern = rf"{re.escape(label)}\s*[:：]?\s*({value_pattern})"
            else:
                pattern = rf"{re.escape(label)}\s*[:：]?\s*([^。；;，,\n\r]+)"
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                value = self._stop_at_next_label(value)
                value = self._strip_field_value(value)
                return "" if self._is_masked_value(value) else value
        return ""

    def _extract_person_values(self, text: str, labels: List[str]) -> List[str]:
        values: List[str] = []
        for label in labels:
            pattern = rf"{re.escape(label)}\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z·、,，；;\s]{{2,40}})"
            for match in re.finditer(pattern, text):
                value = re.split(r"(?:联系电话|电话|手机|联系方式|邮箱|电子邮箱|负责人电话|负责人联系方式)[:：]?", match.group(1))[0]
                for part in re.split(r"[、,，；;\s]+", value):
                    part = self._strip_field_value(part)
                    if self._looks_like_person_name(part) and not self._is_masked_value(part):
                        values.append(part)
        return values

    def _extract_contact_methods(self, text: str, labels: List[str]) -> List[str]:
        values: List[str] = []
        include_following_email = any(label in RESPONSIBLE_METHOD_LABELS for label in labels)
        for label in labels:
            pattern = rf"{re.escape(label)}\s*[:：]?"
            for match in re.finditer(pattern, text):
                if self._is_embedded_generic_contact_label(text, match.start(), label):
                    continue
                segment = self._segment_after_label(text, match.end(), include_following_email=include_following_email)
                values.extend(self._extract_phones_and_emails(segment))
        return values

    def _extract_phones_and_emails(self, text: str) -> List[str]:
        if self._is_masked_value(text):
            return []
        values: List[str] = []
        for match in PHONE_RE.finditer(text):
            phone = re.sub(r"\s+", "", match.group(0))
            phone = phone.replace("转", "-").replace("分机", "-")
            if self._looks_like_phone(phone):
                values.append(phone)
        values.extend(match.group(0) for match in EMAIL_RE.finditer(text))
        return values

    def _looks_like_phone(self, value: str) -> bool:
        digits = re.sub(r"\D", "", value)
        if len(digits) < 7 or len(digits) > 17:
            return False
        if re.fullmatch(r"20\d{6,12}", digits):
            return False
        return True

    def _looks_like_person_name(self, value: str) -> bool:
        if not value or len(value) > 12:
            return False
        if any(term in value for term in ["联系电话", "联系方式", "电话", "手机", "邮箱", "项目", "采购", "招标", "截止", "标书", "信息", "联系人"]):
            return False
        return bool(re.search(r"[\u4e00-\u9fa5A-Za-z]", value))

    def _is_masked_value(self, value: str) -> bool:
        return any(term in (value or "") for term in ["点击查看", "登录后查看", "会员查看", "****", "保密"])

    def _extract_date(self, text: str) -> str:
        match = DATE_RE.search(text or "")
        if not match:
            return ""
        return self._normalize_date(match.group(0))

    def _normalize_date(self, value: Any) -> str:
        if not value:
            return ""
        match = DATE_RE.search(str(value))
        if not match:
            return ""
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def _detect_project_stage(self, candidates: List[str]) -> str:
        for candidate in candidates:
            if not candidate:
                continue
            for keyword, stage in STAGE_KEYWORDS:
                if keyword in candidate:
                    return stage
        return ""

    def _node_context_text(self, node) -> str:
        texts = [node.get_text(" ", strip=True), node.get("context", "")]
        parent = getattr(node, "parent", None)
        if parent is not None:
            try:
                texts.append(parent.get_text(" ", strip=True))
            except Exception:
                pass
        return self._normalize_space(" ".join(texts))

    def _normalize_space(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _strip_field_value(self, value: str) -> str:
        return str(value or "").strip(" ：:，,；;。[]【】 ")

    def _segment_after_label(self, text: str, start: int, include_following_email: bool = False) -> str:
        labels = (
            PUBLISH_DATE_LABELS
            + SOURCE_LABELS
            + PURCHASER_LABELS
            + CONTACT_PERSON_LABELS
            + CONTACT_METHOD_LABELS
            + RESPONSIBLE_PERSON_LABELS
            + RESPONSIBLE_METHOD_LABELS
            + FIELD_STOP_LABELS
        )
        next_positions = []
        for label in labels:
            if include_following_email and label in {"邮箱", "电子邮箱"}:
                continue
            match = re.search(rf"\s{re.escape(label)}\s*[:：]?", text[start:])
            if match:
                next_positions.append(start + match.start())
        end = min(next_positions) if next_positions else len(text)
        return text[start:end]

    def _is_embedded_generic_contact_label(self, text: str, start: int, label: str) -> bool:
        if label not in {"电话", "手机", "手机号", "联系方式", "邮箱", "电子邮箱"}:
            return False
        prefix = text[max(0, start - 10):start]
        return any(term in prefix for term in ["负责人", "项目负责人", "采购负责人", "招标负责人", "代理负责人"]) or bool(
            re.search(r"负责人(?:电话|联系方式)[:：]?\s*\(?0?\d", prefix)
        )

    def _stop_at_next_label(self, value: str) -> str:
        labels = (
            PUBLISH_DATE_LABELS
            + SOURCE_LABELS
            + PURCHASER_LABELS
            + CONTACT_PERSON_LABELS
            + CONTACT_METHOD_LABELS
            + RESPONSIBLE_PERSON_LABELS
            + RESPONSIBLE_METHOD_LABELS
            + FIELD_STOP_LABELS
        )
        pattern = r"\s+(?:" + "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True)) + r")\s*[:：]?"
        return re.split(pattern, value, maxsplit=1)[0]

    def _join_unique(self, values: List[str]) -> str:
        result: List[str] = []
        seen = set()
        for value in values:
            value = self._strip_field_value(value)
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return "；".join(result)

    def _with_metadata(
        self,
        content: str,
        original_url: str,
        timestamp: str,
        fields: Optional[Dict[str, str]] = None,
        rule: Optional[Dict[str, str]] = None,
    ) -> str:
        fields = fields or {}
        rule = rule or self._classify_url(original_url)
        metadata_parts = [
            f"original_url: {original_url}",
            f"crawl_timestamp: {timestamp}",
            f"platform: {rule.get('platform', '')}",
            f"page_type: {rule.get('page_type', '')}",
            f"handling: {rule.get('handling', '')}",
        ]
        for key in [
            "publisher",
            "contact_person",
            "contact_phone",
            "responsible_person",
            "responsible_phone",
            "project_stage",
        ]:
            if fields.get(key):
                metadata_parts.append(f"{key}: {fields[key]}")
        metadata = "\n".join(metadata_parts)
        if content:
            return f"{metadata}\n{content}"
        return metadata

    def _contains_blocked_sign(self, html: str, url: str = "") -> bool:
        return bool(self._matched_blocked_sign(html, url))

    def _blocked_reason(self, html: str, url: str = "") -> str:
        matched_sign = self._matched_blocked_sign(html, url)
        signal_text = f"{self._visible_text_for_blocking(html).lower()} {matched_sign.lower()}"
        if any(sign in signal_text for sign in ["captcha", "验证码", "安全验证", "滑块验证", "人机验证"]):
            return "页面包含验证码/安全验证组件: 需要人工验证或授权 Cookie；不自动绕过验证码"
        if any(sign in signal_text for sign in ["access denied", "forbidden", "访问被拒绝", "请求被禁止", "ip被封"]):
            return "页面包含访问拒绝/Forbidden/IP 限制提示: 疑似反爬或访问限制"
        if any(sign in signal_text for sign in ["请先登录", "请登录后", "登录后查看"]):
            return "页面内容提示需登录后查看: 需要授权账号或 Cookie；不绕过登录"
        if any(sign in signal_text for sign in ["访问频繁", "请求过于频繁"]):
            return "页面提示访问频繁: 建议降低频率或稍后重试"
        if matched_sign:
            return f"页面命中站点拓扑阻断信号 {matched_sign}: 不入库，继续保留为诊断"
        return "页面包含访问限制信号: 已跳过以避免误抓受限内容"

    def _blocked_signs_for_url(self, url: str = "") -> List[str]:
        signs = list(BLOCKED_SIGNS)
        topology = self._topology_for_url(url) if url else None
        if topology:
            for key in ("blocked_phrases", "blocked_permission_phrases"):
                values = topology.get(key)
                if isinstance(values, str):
                    signs.append(values)
                elif isinstance(values, list):
                    signs.extend(str(value) for value in values if value)
            action_only = set()
            for key in ("action_only_phrases", "non_blocking_phrases"):
                values = topology.get(key)
                if isinstance(values, str):
                    action_only.add(values.lower())
                elif isinstance(values, list):
                    action_only.update(str(value).lower() for value in values if value)
            if action_only:
                signs = [sign for sign in signs if sign.lower() not in action_only]
        return signs

    def _matched_blocked_sign(self, html: str, url: str = "") -> str:
        visible_lower = self._visible_text_for_blocking(html).lower()
        for sign in self._blocked_signs_for_url(url):
            sign_lower = str(sign).lower()
            if sign and sign_lower in visible_lower:
                if self._is_non_blocking_login_hint(sign_lower, visible_lower):
                    continue
                return str(sign)
        return ""

    def _is_non_blocking_login_hint(self, sign: str, visible_lower: str) -> bool:
        if sign not in {"请登录", "登录"}:
            return False
        hard_login_contexts = [
            "请先登录",
            "请登录后",
            "登录后查看",
            "登录即可",
            "登录才能",
            "登录以查看",
            "auth-center",
            "统一认证",
            "会员登录",
        ]
        if any(context in visible_lower for context in hard_login_contexts):
            return False
        return self._has_public_crawl_evidence(visible_lower)

    def _visible_text_for_blocking(self, html: str) -> str:
        without_scripts = re.sub(
            r"(?is)<(script|style|noscript|template|svg)\b[^>]*>.*?</\1>",
            " ",
            html or "",
        )
        text = re.sub(r"(?is)<[^>]+>", " ", without_scripts)
        return self._normalize_space(text)

    def _has_public_crawl_evidence(self, text: str) -> bool:
        clean = self._normalize_space(text)
        if self._has_detail_evidence(clean, allow_minimal=True):
            return True
        has_stage = self._has_strong_bid_stage(clean)
        has_subject = any(term in clean for term in ["项目", "工程", "采购", "招标", "中标", "公告"])
        return has_stage and has_subject and len(clean) >= 40

    def _record_diagnostic(
        self,
        url: str,
        status: str,
        reason: str,
        timestamp: str,
        status_code: Optional[int] = None,
        item_count: int = 0,
        cookie_used: bool = False,
        rule: Optional[Dict[str, str]] = None,
    ) -> None:
        rule = rule or self._classify_url(url)
        entry = {
            "timestamp": timestamp,
            "source": self.name,
            "url": url,
            "status": status,
            "reason": reason,
            "status_code": status_code,
            "item_count": item_count,
            "cookie_used": cookie_used,
            "platform": rule.get("platform", ""),
            "page_type": rule.get("page_type", ""),
            "handling": rule.get("handling", ""),
        }
        with self._diagnostics_lock:
            os.makedirs(os.path.dirname(self.diagnostics_path) or ".", exist_ok=True)
            with open(self.diagnostics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.logger.info(f"[{self.name}] {status.upper()} {url} - {reason}")
        if callable(self.log_callback):
            self.log_callback(f"[URL诊断] {self.name} | {status} | {url} | {reason}")
