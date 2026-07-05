"""Runner facade for configured source-backed crawls."""
from __future__ import annotations

from typing import Any, Callable, Iterable

try:
    from .source_adapter import TopologySourceAdapter
    from .source_models import CrawlResult, Source
except ImportError:  # pragma: no cover
    from crawler.source_adapter import TopologySourceAdapter
    from crawler.source_models import CrawlResult, Source


class CrawlRunner:
    def __init__(self, storage, adapter=None, log_callback=None):
        self.storage = storage
        self.adapter = adapter or TopologySourceAdapter()
        self.log_callback = log_callback

    def run_source(self, source: Source, stop_event=None):
        run_id = self.storage.start_crawl_run(source.id, source.name)
        try:
            result = self.adapter.collect(
                source,
                stop_event=stop_event,
                notice_exists=lambda notice: self.storage.exists(notice.to_bid_info()),
            )
        except Exception as exc:
            self.storage.finish_crawl_run(run_id, "failed", counts=self._failure_counts(error=exc))
            return []

        bids = []
        try:
            for notice in result.notices:
                bid = notice.to_bid_info()
                bid.crawl_run_id = run_id
                bid.source_id = source.id
                bids.append(bid)
        except Exception as exc:
            self.storage.finish_crawl_run(run_id, "failed", counts=self._failure_counts(result, exc))
            return []

        status = self._status_for(result)
        self.storage.finish_crawl_run(run_id, status, counts=self._counts_for(result))
        return bids

    def _status_for(self, result: CrawlResult) -> str:
        has_notices = bool(result.notices)
        has_errors = bool(result.error_count or result.errors)
        if has_errors and has_notices:
            return "partial"
        if has_errors:
            return "failed"
        if not has_notices:
            return "skipped"
        return "success"

    def _counts_for(self, result: CrawlResult) -> dict[str, Any]:
        error_message = "; ".join(result.errors)[:500]
        return {
            "fetched_count": result.fetched_count,
            "candidate_count": result.candidate_count,
            "parsed_count": result.parsed_count,
            "skipped_count": result.skipped_count,
            "error_count": result.error_count,
            "error_message": error_message,
        }

    def _failure_counts(self, result: CrawlResult | None = None, error: Exception | None = None) -> dict[str, Any]:
        counts = self._counts_for(result) if result is not None else {}
        existing_errors = list(result.errors) if result is not None else []
        if error is not None:
            existing_errors.append(str(error))
        counts["error_count"] = (result.error_count if result is not None else 0) + 1
        counts["error_message"] = "; ".join(existing_errors)[:500]
        return counts


class SourceBackedCrawler:
    name = "配置数据源"

    def __init__(
        self,
        sources: Iterable[Source],
        config: dict[str, Any],
        storage_provider,
        adapter_factory: Callable[[dict[str, Any]], Any] | None = None,
        log_callback=None,
    ):
        self.sources = list(sources)
        self.config = dict(config or {})
        self.storage_provider = storage_provider
        self.adapter_factory = adapter_factory or (lambda config: TopologySourceAdapter(config))
        self.log_callback = log_callback

    def crawl(self, stop_event=None):
        storage = self.storage_provider()
        bids = []
        for source in self.sources:
            if stop_event and stop_event.is_set():
                break
            adapter = self.adapter_factory(dict(self.config))
            runner = CrawlRunner(storage, adapter=adapter, log_callback=self.log_callback)
            bids.extend(runner.run_source(source, stop_event=stop_event))
        return bids
