import json
import os
import sqlite3
import tempfile
import unittest

from src.database.storage import BidInfo, Storage


class StorageResultsCenterTests(unittest.TestCase):
    def make_storage(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        return Storage(os.path.join(tmpdir.name, "bids.db"))

    def test_new_database_has_results_center_columns(self):
        storage = self.make_storage()
        conn = sqlite3.connect(storage.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(bids)").fetchall()}

        for column in [
            "fit_status",
            "follow_decision",
            "urgency",
            "urgency_source",
            "project_stage",
            "amount",
            "amount_unit",
            "region",
            "category",
            "project_type",
            "nature",
            "registration_deadline",
            "submission_deadline",
            "bid_opening_time",
            "deadline_source",
            "urgency_reference_time",
            "urgency_reference_type",
            "ai_extract_status",
            "detail_fetch_status",
            "detail_fetched_at",
            "detail_text",
            "ai_extracted_data",
            "manual_overrides",
            "non_follow_reasons",
            "review_notes",
            "ai_recommendation",
            "ai_extract_error",
            "detail_fetch_error",
            "updated_at",
        ]:
            self.assertIn(column, columns)

    def test_existing_database_is_migrated_without_losing_rows(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "bids.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE bids (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    publish_date TEXT,
                    source TEXT,
                    content TEXT,
                    purchaser TEXT,
                    notified INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO bids (unique_id, title, url, publish_date, source) VALUES (?, ?, ?, ?, ?)",
                ("u1", "旧项目", "https://example.com/1", "2026-07-01", "测试源"),
            )

        storage = Storage(db_path)
        bid = storage.get_all()[0]

        self.assertEqual(bid.title, "旧项目")
        self.assertEqual(bid.fit_status, "pending")
        self.assertEqual(bid.follow_decision, "pending")
        self.assertEqual(bid.project_stage, "lead")
        self.assertEqual(bid.ai_extract_status, "pending")

    def test_save_returns_row_id_and_defaults_review_fields(self):
        storage = self.make_storage()
        result_id = storage.save(
            BidInfo(
                title="上海智能化公开招标",
                url="https://example.com/result/1",
                publish_date="2026-07-01",
                source="测试源",
                content="弱电智能化项目",
            )
        )

        self.assertIsInstance(result_id, int)
        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.fit_status, "pending")
        self.assertEqual(bid.follow_decision, "pending")
        self.assertEqual(bid.project_stage, "lead")
        self.assertEqual(bid.ai_extract_status, "pending")
        self.assertEqual(storage.save(bid), False)

    def test_query_update_review_and_manual_overrides(self):
        storage = self.make_storage()
        result_id = storage.save(BidInfo("项目A", "https://example.com/a", "2026-07-01", "源"))

        storage.update_review(
            [result_id],
            {
                "fit_status": "not_fit",
                "follow_decision": "not_follow",
                "urgency": "high",
                "urgency_source": "manual",
                "project_stage": "screening",
                "non_follow_reasons": ["地域问题", "其它"],
                "review_notes": "外省项目，先不跟进",
            },
        )
        storage.update_manual_overrides(result_id, {"organization": "人工单位", "amount": "120000"})

        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.fit_status, "not_fit")
        self.assertEqual(bid.follow_decision, "not_follow")
        self.assertEqual(bid.urgency, "high")
        self.assertEqual(bid.non_follow_reasons, ["地域问题", "其它"])
        self.assertEqual(bid.manual_overrides["organization"], "人工单位")

        rows, total = storage.query_results({"follow_decision": "not_follow"}, limit=10, offset=0)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].id, result_id)

    def test_update_ai_extraction_syncs_columns_and_json(self):
        storage = self.make_storage()
        result_id = storage.save(BidInfo("项目A", "https://example.com/a", "2026-07-01", "源"))

        ai_data = {
            "organization": "上海某单位",
            "amount": "50",
            "amount_unit": "万元",
            "region": "上海",
            "category": "弱电智能化",
            "project_type": "公开招标",
            "nature": "服务",
            "deadlines": [
                {"type": "submission_deadline", "end_at": "2026-07-05 10:00", "raw_text": "投标截止"},
            ],
        }
        storage.update_ai_extraction(
            result_id,
            "extracted",
            ai_data,
            {
                "amount": "50",
                "amount_unit": "万元",
                "region": "上海",
                "category": "弱电智能化",
                "project_type": "公开招标",
                "nature": "服务",
                "submission_deadline": "2026-07-05 10:00",
                "deadline_source": "ai",
            },
        )

        bid = storage.get_by_id(result_id)
        self.assertEqual(bid.ai_extract_status, "extracted")
        self.assertEqual(bid.region, "上海")
        self.assertEqual(bid.submission_deadline, "2026-07-05 10:00")
        self.assertEqual(bid.ai_extracted_data["organization"], "上海某单位")
