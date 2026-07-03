import os
import sqlite3
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

    def test_storage_migrates_non_empty_crawl_runs_table_missing_source_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "bids.db")
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE crawl_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_name TEXT DEFAULT '',
                        started_at TEXT DEFAULT '',
                        status TEXT DEFAULT 'running'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO crawl_runs (source_name, started_at, status)
                    VALUES (?, ?, ?)
                    """,
                    ("Legacy Source", "2026-07-03T09:00:00", "success"),
                )

            storage = Storage(db_path)
            conn = storage._get_connection()
            column_info = {
                row[1]: row for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()
            }
            row = conn.execute(
                "SELECT source_id, source_name, started_at, status FROM crawl_runs WHERE id = 1"
            ).fetchone()

        self.assertIn("source_id", column_info)
        self.assertIn("candidate_count", column_info)
        self.assertIn("error_message", column_info)
        self.assertEqual(column_info["source_id"][3], 1)
        self.assertEqual(column_info["source_id"][4], "''")
        self.assertIsNotNone(row)
        self.assertEqual(row["source_id"], "")
        self.assertEqual(row["source_name"], "Legacy Source")
        self.assertEqual(row["started_at"], "2026-07-03T09:00:00")
        self.assertEqual(row["status"], "success")

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

    def test_finish_crawl_run_preserves_absent_incremented_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))

            run_id = storage.start_crawl_run("source-a", "Source A")
            storage.increment_crawl_run_counts(
                run_id,
                inserted_delta=2,
                updated_delta=3,
                skipped_delta=4,
            )
            storage.finish_crawl_run(
                run_id,
                "success",
                {
                    "fetched_count": 9,
                    "candidate_count": 8,
                    "parsed_count": 7,
                    "error_count": 0,
                },
            )
            run = storage.get_crawl_run(run_id)

        self.assertEqual(run["inserted_count"], 2)
        self.assertEqual(run["updated_count"], 3)
        self.assertEqual(run["skipped_count"], 4)

    def test_finish_crawl_run_persists_explicit_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))

            run_id = storage.start_crawl_run("source-a", "Source A")
            storage.increment_crawl_run_counts(
                run_id,
                inserted_delta=2,
                updated_delta=3,
                skipped_delta=4,
            )
            storage.finish_crawl_run(
                run_id,
                "success",
                {
                    "inserted_count": 5,
                    "updated_count": 6,
                    "skipped_count": 7,
                },
            )
            run = storage.get_crawl_run(run_id)

        self.assertEqual(run["inserted_count"], 5)
        self.assertEqual(run["updated_count"], 6)
        self.assertEqual(run["skipped_count"], 7)

    def test_get_recent_crawl_runs_returns_newest_limited_runs_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(os.path.join(tmpdir, "bids.db"))

            first_id = storage.start_crawl_run("source-a", "Source A")
            second_id = storage.start_crawl_run("source-b", "Source B")
            third_id = storage.start_crawl_run("source-c", "Source C")
            runs = storage.get_recent_crawl_runs(limit=2)

        self.assertEqual([run["id"] for run in runs], [third_id, second_id])
        self.assertNotIn(first_id, [run["id"] for run in runs])


if __name__ == "__main__":
    unittest.main()
