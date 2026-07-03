import os
import tempfile
import unittest

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from database.storage import Storage


class CrawlRunStorageTests(unittest.TestCase):
    def test_storage_migrates_crawl_runs_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))
            conn = storage._get_connection()

            columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()}

        self.assertIn("source_id", columns)
        self.assertIn("candidate_count", columns)
        self.assertIn("inserted_count", columns)
        self.assertIn("error_message", columns)

    def test_start_finish_increment_and_read_crawl_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))

            run_id = storage.start_crawl_run("source-a", "源 A")
            storage.increment_crawl_run_counts(run_id, inserted_delta=2, skipped_delta=1)
            storage.finish_crawl_run(
                run_id,
                "partial",
                {
                    "fetched_count": 3,
                    "candidate_count": 4,
                    "parsed_count": 2,
                    "error_count": 1,
                    "error_message": "one detail failed",
                },
            )
            run = storage.get_crawl_run(run_id)

        self.assertEqual(run["source_id"], "source-a")
        self.assertEqual(run["source_name"], "源 A")
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["fetched_count"], 3)
        self.assertEqual(run["candidate_count"], 4)
        self.assertEqual(run["parsed_count"], 2)
        self.assertEqual(run["inserted_count"], 2)
        self.assertEqual(run["skipped_count"], 1)
        self.assertEqual(run["error_count"], 1)
        self.assertEqual(run["error_message"], "one detail failed")
        self.assertTrue(run["started_at"])
        self.assertTrue(run["finished_at"])


if __name__ == "__main__":
    unittest.main()
