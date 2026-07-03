"""URL source registry loading for topology-driven crawling."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, List
from urllib.parse import urlparse

from .source_models import Source


@dataclass(frozen=True)
class UrlSource:
    id: str
    name: str
    url: str
    enabled: bool = True


class _BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._active_href = attrs_dict.get("href")
        self._active_text = []

    def handle_data(self, data: str):
        if self._active_href is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() != "a" or self._active_href is None:
            return
        self.links.append(("".join(self._active_text).strip(), self._active_href.strip()))
        self._active_href = None
        self._active_text = []


def _looks_like_url(value: Any) -> bool:
    if not value:
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _slugify(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").lower()).strip("-")
    return cleaned or fallback


def _dedupe_sources(items: Iterable[UrlSource]) -> List[UrlSource]:
    result: list[UrlSource] = []
    seen_urls: set[str] = set()
    used_ids: set[str] = set()
    for item in items:
        if not item.enabled or not _looks_like_url(item.url):
            continue
        if item.url in seen_urls:
            continue
        source_id = item.id
        if source_id in used_ids:
            suffix = 2
            while f"{source_id}-{suffix}" in used_ids:
                suffix += 1
            source_id = f"{source_id}-{suffix}"
        seen_urls.add(item.url)
        used_ids.add(source_id)
        result.append(UrlSource(id=source_id, name=item.name or item.url, url=item.url, enabled=True))
    return result


def _load_json_sources(path: Path) -> List[UrlSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    items: list[UrlSource] = []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            continue
        url = str(record.get("url", "")).strip()
        name = str(record.get("name") or record.get("title") or url).strip()
        source_id = str(record.get("id") or _slugify(urlparse(url).netloc, f"source-{index}")).strip()
        items.append(
            UrlSource(
                id=source_id,
                name=name,
                url=url,
                enabled=bool(record.get("enabled", True)),
            )
        )
    return _dedupe_sources(items)


def _load_bookmark_sources(path: Path) -> List[UrlSource]:
    parser = _BookmarkParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    items: list[UrlSource] = []
    for index, (title, href) in enumerate(parser.links, 1):
        if not _looks_like_url(href):
            continue
        host = urlparse(href).netloc.lower().split(":")[0]
        items.append(
            UrlSource(
                id=_slugify(host[4:] if host.startswith("www.") else host, f"bookmark-{index}"),
                name=title or href,
                url=href,
                enabled=True,
            )
        )
    return _dedupe_sources(items)


def load_url_sources(path: str) -> List[UrlSource]:
    source_path = Path(path)
    if not source_path.exists():
        return []
    suffix = source_path.suffix.lower()
    if suffix == ".json":
        return _load_json_sources(source_path)
    if suffix in {".html", ".htm"}:
        return _load_bookmark_sources(source_path)
    return []


def load_site_topologies(path: str) -> dict[str, dict[str, Any]]:
    topology_path = Path(path)
    if not path or not topology_path.exists():
        return {}
    try:
        payload = json.loads(topology_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
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
