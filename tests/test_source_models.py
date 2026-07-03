import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from crawler.source_models import Notice, NoticeDeduplicator, normalize_notice_url


class SourceModelsTests(unittest.TestCase):
    def test_normalize_notice_url_lowercases_scheme_host_and_drops_default_port(self):
        normalized = normalize_notice_url(
            "HTTPS://Example.COM:443/Notice?id=2&utm_source=x&b=2&a=1#section"
        )

        self.assertEqual(normalized, "https://example.com/Notice?a=1&b=2&id=2")

    def test_normalize_notice_url_preserves_non_default_port(self):
        normalized = normalize_notice_url("HTTP://Example.COM:8080/Notice?from=feed&id=7")

        self.assertEqual(normalized, "http://example.com:8080/Notice?id=7")

    def test_deduplicator_normalizes_date_in_weak_key(self):
        deduplicator = NoticeDeduplicator()
        first = Notice(
            source_id="src",
            source_name="Source",
            title=" Smart City Bid ",
            detail_url="",
            purchaser=" Buyer ",
            publish_date=" 2026-07-03 ",
            region=" Shanghai ",
        )
        duplicate = Notice(
            source_id="src",
            source_name="Source",
            title="smart   city bid",
            detail_url="",
            purchaser="buyer",
            publish_date="2026-07-03",
            region="shanghai",
        )

        self.assertTrue(deduplicator.add(first))
        self.assertFalse(deduplicator.add(duplicate))

    def test_notice_to_bid_info_preserves_region(self):
        notice = Notice(
            source_id="src",
            source_name="Source",
            title="Bid",
            detail_url="https://example.com/bid",
            region="Shanghai",
        )

        bid = notice.to_bid_info()

        self.assertEqual(bid.region, "Shanghai")


if __name__ == "__main__":
    unittest.main()
