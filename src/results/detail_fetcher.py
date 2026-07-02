from __future__ import annotations

import re

try:
    import requests
except ImportError:  # pragma: no cover
    class _RequestsShim:
        get = None

    requests = _RequestsShim()

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


BLOCKED_DETAIL_PHRASES = [
    "请输入验证码",
    "验证码",
    "安全验证",
    "滑块验证",
    "人机验证",
    "doVerify.php",
    "access verification",
    "access denied",
    "forbidden",
    "访问被拒绝",
    "请求过于频繁",
    "访问频繁",
    "请先登录",
    "请登录后",
    "登录后查看",
    "登录即可免费查看完整信息",
    "登录 即可查看",
    "今日次数已用完",
    "免费查看完整信息",
    "会员查看",
    "VIP",
    "需要项目通权限",
]


def _blocked_detail_reason(text: str) -> str | None:
    lowered = (text or "").lower()
    for phrase in BLOCKED_DETAIL_PHRASES:
        if phrase.lower() in lowered:
            return f"blocked detail body: {phrase}"
    return None


def _browser_mode_enabled(config: dict | None) -> bool:
    config = config or {}
    browser_backend = config.get("browser_backend") or {}
    return bool(config.get("use_selenium") or browser_backend.get("mode") in {"browser_auto", "browser", "browser_cloak", "browser_selenium"})


def _browser_first_enabled(config: dict | None) -> bool:
    config = config or {}
    browser_backend = config.get("browser_backend") or {}
    return browser_backend.get("mode") in {"browser_auto", "browser", "browser_cloak", "browser_selenium"}


def _fetch_detail_html_with_browser(url: str, config: dict | None, timeout: int) -> tuple[bool, str, str | None]:
    try:
        from crawler.browser import create_browser_crawler
    except Exception as exc:
        return False, "", f"browser backend unavailable: {exc}"

    browser_config = dict(config or {})
    browser_config.setdefault("timeout", timeout)
    crawler = create_browser_crawler(browser_config, "detail-fetch", url, headless=True)
    if crawler is None:
        return False, "", "no browser backend available"
    try:
        html = crawler.fetch(url)
    except Exception as exc:
        return False, "", str(exc)[:200]
    if not html:
        return False, "", "browser returned empty page"
    return True, html, None


def fetch_detail_text(url: str, timeout: int = 30, fetch_config: dict | None = None) -> tuple[bool, str, str | None]:
    if not hasattr(requests, "get"):
        return False, "", "requests is not installed"
    http_error = None
    if _browser_first_enabled(fetch_config):
        ok, html, browser_error = _fetch_detail_html_with_browser(url, fetch_config, timeout)
        if ok:
            text = clean_html_to_text(html)
            blocked_reason = _blocked_detail_reason(text)
            if blocked_reason:
                return False, "", blocked_reason
            if text:
                return True, text, None
            http_error = "browser detail page returned no readable text"
        else:
            http_error = browser_error

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 BidMonitor/1.0"},
            verify=False,
        )
        if response.status_code >= 400:
            http_error = f"HTTP {response.status_code}"
        else:
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
            text = clean_html_to_text(response.text)
            blocked_reason = _blocked_detail_reason(text)
            if blocked_reason:
                http_error = blocked_reason
            elif text and len(text) >= 80:
                return True, text, None
            else:
                http_error = "detail page returned too little text"
    except Exception as exc:
        http_error = str(exc)[:200]

    if _browser_mode_enabled(fetch_config):
        ok, html, browser_error = _fetch_detail_html_with_browser(url, fetch_config, timeout)
        if ok:
            text = clean_html_to_text(html)
            blocked_reason = _blocked_detail_reason(text)
            if blocked_reason:
                return False, "", blocked_reason
            if text:
                return True, text, None
            return False, "", "browser detail page returned no readable text"
        return False, "", browser_error or http_error

    return False, "", http_error
