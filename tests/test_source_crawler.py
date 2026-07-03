import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_crawler import CrawlRunner, SourceBackedCrawler
from crawler.source_models import CrawlResult, Notice, Source


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def collect(self, source, stop_event=None):
        self.calls.append((source, stop_event))
        return self.result


class FakeStorage:
    def __init__(self):
        self.started = []
        self.finished = []
        self._next_run_id = 100

    def start_crawl_run(self, source_id, source_name):
        self._next_run_id += 1
        self.started.append((source_id, source_name))
        return self._next_run_id

    def finish_crawl_run(self, run_id, status, counts=None):
        self.finished.append((run_id, status, counts or {}))


def make_source(source_id="source-a", name="Source A"):
    return Source(
        id=source_id,
        name=name,
        url=f"https://{source_id}.example.com/notices",
    )


def make_notice(source):
    return Notice(
        source_id=source.id,
        source_name=source.name,
        title=f"{source.name} bid",
        detail_url=f"{source.url}/1",
        publish_date="2026-07-03",
        purchaser="Purchaser",
        region="Shanghai",
        content="Procurement content",
        raw={"id": 1},
    )


class CrawlRunnerTests(unittest.TestCase):
    def test_run_source_records_successful_run_and_tags_legacy_bids(self):
        source = make_source()
        notice = make_notice(source)
        result = CrawlResult(
            notices=[notice],
            fetched_count=2,
            candidate_count=3,
            parsed_count=1,
            skipped_count=0,
            error_count=0,
        )
        storage = FakeStorage()
        adapter = FakeAdapter(result)
        runner = CrawlRunner(storage, adapter=adapter)

        bids = runner.run_source(source)

        self.assertEqual(storage.started, [("source-a", "Source A")])
        self.assertEqual(adapter.calls, [(source, None)])
        self.assertEqual(len(storage.finished), 1)
        run_id, status, counts = storage.finished[0]
        self.assertEqual(run_id, 101)
        self.assertEqual(status, "success")
        self.assertEqual(
            counts,
            {
                "fetched_count": 2,
                "candidate_count": 3,
                "parsed_count": 1,
                "skipped_count": 0,
                "error_count": 0,
                "error_message": "",
            },
        )
        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0].title, "Source A bid")
        self.assertEqual(bids[0].source, "Source A")
        self.assertEqual(bids[0].region, "Shanghai")
        self.assertIn("raw:", bids[0].content)
        self.assertEqual(bids[0].crawl_run_id, 101)
        self.assertEqual(bids[0].source_id, "source-a")

    def test_run_source_marks_error_only_result_failed_and_returns_no_bids(self):
        source = make_source()
        result = CrawlResult(
            notices=[],
            fetched_count=1,
            candidate_count=0,
            parsed_count=0,
            skipped_count=0,
            error_count=1,
            errors=["source fetch failed"],
        )
        storage = FakeStorage()
        runner = CrawlRunner(storage, adapter=FakeAdapter(result))

        bids = runner.run_source(source)

        self.assertEqual(bids, [])
        self.assertEqual(len(storage.finished), 1)
        _run_id, status, counts = storage.finished[0]
        self.assertEqual(status, "failed")
        self.assertEqual(counts["error_count"], 1)
        self.assertEqual(counts["error_message"], "source fetch failed")


class SourceBackedCrawlerTests(unittest.TestCase):
    def test_crawl_runs_all_sources_and_returns_all_tagged_bids(self):
        sources = [make_source("source-a", "Source A"), make_source("source-b", "Source B")]
        storage = FakeStorage()
        adapters = []

        def adapter_factory(config):
            source = sources[len(adapters)]
            adapter = FakeAdapter(CrawlResult(notices=[make_notice(source)], parsed_count=1))
            adapters.append((config, adapter))
            return adapter

        crawler = SourceBackedCrawler(
            sources,
            {"request_delay": 0},
            lambda: storage,
            adapter_factory=adapter_factory,
        )

        bids = crawler.crawl()

        self.assertEqual(crawler.name, "配置数据源")
        self.assertEqual(storage.started, [("source-a", "Source A"), ("source-b", "Source B")])
        self.assertEqual([finished[0] for finished in storage.finished], [101, 102])
        self.assertEqual([finished[1] for finished in storage.finished], ["success", "success"])
        self.assertEqual(len(bids), 2)
        self.assertEqual([bid.source_id for bid in bids], ["source-a", "source-b"])
        self.assertEqual([bid.crawl_run_id for bid in bids], [101, 102])
        self.assertEqual([call[0] for _config, adapter in adapters for call in adapter.calls], sources)
        self.assertEqual([config for config, _adapter in adapters], [{"request_delay": 0}, {"request_delay": 0}])


if __name__ == "__main__":
    unittest.main()
