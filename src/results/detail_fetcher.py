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


def fetch_detail_text(url: str, timeout: int = 30) -> tuple[bool, str, str | None]:
    if not hasattr(requests, "get"):
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
