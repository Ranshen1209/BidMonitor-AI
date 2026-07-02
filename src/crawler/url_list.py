"""
URL 列表爬虫 - 从 txt/csv 读取公开页面并输出基础招标信息。
"""
import csv
import json
import os
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

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
        self.file_path = source_config.get("file_path", "")
        self.diagnostics_path = (
            source_config.get("diagnostics_path")
            or config.get("diagnostics_path")
            or os.path.join("logs", "url_crawl_diagnostics.jsonl")
        )
        self.log_callback = config.get("log_callback")
        self.max_links_per_page = int(config.get("url_list_max_links_per_page", 50))
        self.domain_delay = float(source_config.get("domain_delay", config.get("domain_delay", 0)))
        self.auth_cookies = source_config.get("auth_cookies", config.get("auth_cookies", []))
        self._last_domain_request_at: Dict[str, float] = {}
        super().__init__(config)

    @property
    def name(self) -> str:
        return self._name

    def get_list_urls(self) -> List[str]:
        if not self.file_path or not os.path.exists(self.file_path):
            self.logger.warning(f"[{self.name}] URL list file not found: {self.file_path}")
            return []

        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == ".csv":
            raw_urls = self._read_csv_urls()
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

    def parse(self, html: str) -> List[BidInfo]:
        return self._parse_page(html, self.base_url, datetime.now().isoformat(timespec="seconds"))

    def crawl(self, stop_event=None) -> Optional[List[BidInfo]]:
        urls = self.get_list_urls()
        all_bids: List[BidInfo] = []
        self.logger.info(f"[{self.name}] Starting URL list crawl, {len(urls)} URL(s)")

        for url in urls:
            if stop_event and stop_event.is_set():
                self.logger.info(f"[{self.name}] Crawl interrupted by stop signal")
                break

            timestamp = datetime.now().isoformat(timespec="seconds")
            cookie_used = self._get_cookie_for_url(url) is not None
            try:
                rule = self._classify_url(url)
                if self._should_skip_before_fetch(rule):
                    self._record_diagnostic(
                        url,
                        "skipped_with_reason",
                        rule["reason"],
                        timestamp,
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    continue

                self._respect_rate_limit(url)
                html, status_code, status_text = self._request_url(url)
                if status_code in (401, 403):
                    self._record_diagnostic(
                        url,
                        "failed",
                        "HTTP 403/401: 疑似反爬或需要登录；如有授权 Cookie，请在配置中更新后重试",
                        timestamp,
                        status_code,
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    continue
                if status_code == 404 or status_code >= 500:
                    self._record_diagnostic(
                        url,
                        "failed",
                        "HTTP 404/5xx: 页面不存在或源站异常",
                        timestamp,
                        status_code,
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    continue
                if self._contains_blocked_sign(html):
                    blocked_reason = self._blocked_reason(html)
                    self._record_diagnostic(
                        url,
                        "failed",
                        blocked_reason,
                        timestamp,
                        status_code,
                        cookie_used=cookie_used,
                        rule=rule,
                    )
                    continue

                bids = self._parse_page(html, url, timestamp)
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
                    continue

                all_bids.extend(bids)
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

        self.logger.info(f"[{self.name}] URL list crawl done, got {len(all_bids)} item(s)")
        return all_bids

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

        response = self.session.get(
            url,
            headers=headers,
            timeout=self.timeout,
            verify=False,
            allow_redirects=True,
        )
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text, response.status_code, response.reason

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

        now = time.monotonic()
        last_seen = self._last_domain_request_at.get(host)
        if last_seen is not None:
            wait_seconds = self.domain_delay - (now - last_seen)
            if wait_seconds > 0:
                self.logger.info(f"[{self.name}] Rate limit {host}, sleep {wait_seconds:.1f}s")
                time.sleep(wait_seconds)
        self._last_domain_request_at[host] = time.monotonic()

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
                publish_date=fields.get("publish_date") or datetime.now().strftime("%Y-%m-%d"),
                source=self.name,
                content=self._with_metadata(content, page_url, timestamp, fields, rule),
                purchaser=fields.get("purchaser", ""),
            )
        ]

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
        platform = platform_map.get(host_key, platform_map.get(host, host or "未知平台"))

        handling = "public_crawl"
        reason = "公开页面，按 URL 清单通用规则抓取公告链接或详情"
        if host_key in {"biaoshu.xiaoxiaoai.cn", "xiquebiaoshu.com"}:
            handling = "low_value_reference"
            reason = "AI 标书工具页面，不是公告源；仅记录为低价值参考并尝试公开链接 fallback"
        elif host_key in {"wenshu.court.gov.cn"}:
            handling = "low_value_reference"
            reason = "裁判文书站点不是招投标公告源，作为低价值参考处理"
        elif host_key in {"sd-portygzc.com", "cooperation.ceic.com", "sxtsrm.sngbs.com.cn"} or "login" in path or "sso" in path:
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

        if self._is_api_url(path, query):
            page_type = "api"
        elif self._is_login_url(path, query):
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
        }

    def _is_api_url(self, path: str, query: str) -> bool:
        return "/api/" in path or path.endswith(".json") or "format=json" in query

    def _is_login_url(self, path: str, query: str) -> bool:
        login_terms = ["login", "memberlogin", "sso", "login_bidder", "default/login"]
        return any(term in path for term in login_terms) or "response_type=code" in query

    def _is_detail_url(self, path: str, query: str) -> bool:
        detail_terms = ["/detail", "articleid=", "bid-", "news-", "/t20", ".htm", ".html"]
        if path in ("", "/", "/index.html"):
            return False
        return any(term in f"{path}?{query}" for term in detail_terms)

    def _is_search_url(self, path: str, query: str, fragment: str) -> bool:
        search_text = f"{path}?{query}#{fragment}"
        return any(term in search_text for term in ["search", "keyword", "keywords", "customdessearch", "bidding"])

    def _is_list_url(self, path: str) -> bool:
        list_terms = ["/cggg/", "/tzgg/", "/gg", "/bidweb", "/projects", "/zby", "/notice", "/list"]
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
                    publish_date=publish_date or datetime.now().strftime("%Y-%m-%d"),
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
        publish_date = fields.get("publish_date") or datetime.now().strftime("%Y-%m-%d")
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
            publish_date = self._extract_date(context) or datetime.now().strftime("%Y-%m-%d")
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

    def _contains_blocked_sign(self, html: str) -> bool:
        html_lower = html.lower()
        return any(sign.lower() in html_lower for sign in BLOCKED_SIGNS)

    def _blocked_reason(self, html: str) -> str:
        html_lower = html.lower()
        if any(sign in html_lower for sign in ["captcha", "验证码", "安全验证", "滑块验证", "人机验证"]):
            return "页面包含验证码/安全验证组件: 需要人工验证或授权 Cookie；不自动绕过验证码"
        if any(sign in html_lower for sign in ["access denied", "forbidden", "访问被拒绝", "请求被禁止", "ip被封"]):
            return "页面包含访问拒绝/Forbidden/IP 限制提示: 疑似反爬或访问限制"
        if any(sign in html_lower for sign in ["请先登录", "请登录后", "登录后查看"]):
            return "页面内容提示需登录后查看: 需要授权账号或 Cookie；不绕过登录"
        if any(sign in html_lower for sign in ["访问频繁", "请求过于频繁"]):
            return "页面提示访问频繁: 建议降低频率或稍后重试"
        return "页面包含访问限制信号: 已跳过以避免误抓受限内容"

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
        os.makedirs(os.path.dirname(self.diagnostics_path) or ".", exist_ok=True)
        with open(self.diagnostics_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.logger.info(f"[{self.name}] {status.upper()} {url} - {reason}")
        if callable(self.log_callback):
            self.log_callback(f"[URL诊断] {self.name} | {status} | {url} | {reason}")
