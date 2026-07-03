"""
数据存储模块 - 使用 SQLite 存储招标信息

优化说明（v1.1.1）：
- 使用线程本地存储复用数据库连接，提升性能
- 所有公开方法签名保持不变，完全向后兼容
"""
import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


RESULT_CENTER_COLUMNS = {
    "fit_status": "TEXT DEFAULT 'pending'",
    "follow_decision": "TEXT DEFAULT 'pending'",
    "urgency": "TEXT DEFAULT ''",
    "urgency_source": "TEXT DEFAULT ''",
    "project_stage": "TEXT DEFAULT 'lead'",
    "amount": "TEXT DEFAULT ''",
    "amount_unit": "TEXT DEFAULT ''",
    "region": "TEXT DEFAULT ''",
    "category": "TEXT DEFAULT ''",
    "project_type": "TEXT DEFAULT ''",
    "nature": "TEXT DEFAULT ''",
    "registration_deadline": "TEXT DEFAULT ''",
    "submission_deadline": "TEXT DEFAULT ''",
    "bid_opening_time": "TEXT DEFAULT ''",
    "deadline_source": "TEXT DEFAULT ''",
    "urgency_reference_time": "TEXT DEFAULT ''",
    "urgency_reference_type": "TEXT DEFAULT ''",
    "ai_extract_status": "TEXT DEFAULT 'pending'",
    "detail_fetch_status": "TEXT DEFAULT 'pending'",
    "detail_fetched_at": "TEXT DEFAULT ''",
    "detail_text": "TEXT DEFAULT ''",
    "ai_extracted_data": "TEXT DEFAULT '{}'",
    "manual_overrides": "TEXT DEFAULT '{}'",
    "non_follow_reasons": "TEXT DEFAULT '[]'",
    "review_notes": "TEXT DEFAULT ''",
    "ai_recommendation": "TEXT DEFAULT ''",
    "ai_extract_error": "TEXT DEFAULT ''",
    "detail_fetch_error": "TEXT DEFAULT ''",
    # SQLite ALTER TABLE only accepts constant defaults, so migrations use an
    # empty string here and the application sets updated_at on writes.
    "updated_at": "TEXT DEFAULT ''",
}

RESULT_QUERY_FILTERS = {
    "id": "id",
    "unique_id": "unique_id",
    "title": "title",
    "url": "url",
    "publish_date": "publish_date",
    "source": "source",
    "purchaser": "purchaser",
    "notified": "notified",
    "fit_status": "fit_status",
    "follow_decision": "follow_decision",
    "urgency": "urgency",
    "urgency_source": "urgency_source",
    "project_stage": "project_stage",
    "amount": "amount",
    "amount_unit": "amount_unit",
    "region": "region",
    "category": "category",
    "project_type": "project_type",
    "nature": "nature",
    "registration_deadline": "registration_deadline",
    "submission_deadline": "submission_deadline",
    "bid_opening_time": "bid_opening_time",
    "deadline_source": "deadline_source",
    "urgency_reference_time": "urgency_reference_time",
    "urgency_reference_type": "urgency_reference_type",
    "ai_extract_status": "ai_extract_status",
    "detail_fetch_status": "detail_fetch_status",
    "detail_fetched_at": "detail_fetched_at",
    "review_notes": "review_notes",
    "ai_recommendation": "ai_recommendation",
    "ai_extract_error": "ai_extract_error",
    "detail_fetch_error": "detail_fetch_error",
    "updated_at": "updated_at",
}

CRAWL_RUN_COLUMNS = {
    "source_id": "TEXT NOT NULL",
    "source_name": "TEXT DEFAULT ''",
    "started_at": "TEXT DEFAULT ''",
    "finished_at": "TEXT DEFAULT ''",
    "status": "TEXT DEFAULT 'running'",
    "fetched_count": "INTEGER DEFAULT 0",
    "candidate_count": "INTEGER DEFAULT 0",
    "parsed_count": "INTEGER DEFAULT 0",
    "inserted_count": "INTEGER DEFAULT 0",
    "updated_count": "INTEGER DEFAULT 0",
    "skipped_count": "INTEGER DEFAULT 0",
    "error_count": "INTEGER DEFAULT 0",
    "error_message": "TEXT DEFAULT ''",
}

CRAWL_RUN_MIGRATION_COLUMNS = {
    **CRAWL_RUN_COLUMNS,
    "source_id": "TEXT NOT NULL DEFAULT ''",
}


@dataclass
class BidInfo:
    """招标信息数据类"""

    title: str
    url: str
    publish_date: str
    source: str
    content: str = ""
    purchaser: str = ""
    id: Optional[int] = None
    notified: bool = False
    created_at: str = ""
    fit_status: str = "pending"
    follow_decision: str = "pending"
    urgency: str = ""
    urgency_source: str = ""
    project_stage: str = "lead"
    amount: str = ""
    amount_unit: str = ""
    region: str = ""
    category: str = ""
    project_type: str = ""
    nature: str = ""
    registration_deadline: str = ""
    submission_deadline: str = ""
    bid_opening_time: str = ""
    deadline_source: str = ""
    urgency_reference_time: str = ""
    urgency_reference_type: str = ""
    ai_extract_status: str = "pending"
    detail_fetch_status: str = "pending"
    detail_fetched_at: str = ""
    detail_text: str = ""
    ai_extracted_data: dict[str, Any] = None
    manual_overrides: dict[str, Any] = None
    non_follow_reasons: list[str] = None
    review_notes: str = ""
    ai_recommendation: str = ""
    ai_extract_error: str = ""
    detail_fetch_error: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if self.ai_extracted_data is None:
            self.ai_extracted_data = {}
        if self.manual_overrides is None:
            self.manual_overrides = {}
        if self.non_follow_reasons is None:
            self.non_follow_reasons = []

    @property
    def unique_id(self) -> str:
        """生成唯一标识（基于URL的MD5）"""
        return hashlib.md5(self.url.encode()).hexdigest()


class Storage:
    """SQLite 数据存储类

    使用线程本地存储管理数据库连接，每个线程复用同一个连接，
    避免频繁创建和关闭连接带来的性能开销。
    """

    def __init__(self, db_path: str = "data/bids.db"):
        self.db_path = db_path
        self._local = threading.local()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（复用机制）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self):
        """关闭当前线程的数据库连接（用于清理资源）"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bids (
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    source_name TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    finished_at TEXT DEFAULT '',
                    status TEXT DEFAULT 'running',
                    fetched_count INTEGER DEFAULT 0,
                    candidate_count INTEGER DEFAULT 0,
                    parsed_count INTEGER DEFAULT 0,
                    inserted_count INTEGER DEFAULT 0,
                    updated_count INTEGER DEFAULT 0,
                    skipped_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    error_message TEXT DEFAULT ''
                )
                """
            )
            self._migrate_schema(conn)
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_unique_id ON bids(unique_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notified ON bids(notified)
                """
            )
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection):
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(bids)").fetchall()
        }
        for column, definition in RESULT_CENTER_COLUMNS.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE bids ADD COLUMN {column} {definition}")
        crawl_run_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()
        }
        for column, definition in CRAWL_RUN_MIGRATION_COLUMNS.items():
            if column not in crawl_run_columns:
                conn.execute(f"ALTER TABLE crawl_runs ADD COLUMN {column} {definition}")

    def _json_dumps(self, value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    def _json_loads(self, value: Any, default: Any):
        if value in (None, ""):
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def _row_to_bid(self, row: sqlite3.Row) -> BidInfo:
        return BidInfo(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            publish_date=row["publish_date"] or "",
            source=row["source"] or "",
            content=row["content"] or "",
            purchaser=row["purchaser"] or "",
            notified=bool(row["notified"]),
            created_at=row["created_at"] or "",
            fit_status=row["fit_status"] or "pending",
            follow_decision=row["follow_decision"] or "pending",
            urgency=row["urgency"] or "",
            urgency_source=row["urgency_source"] or "",
            project_stage=row["project_stage"] or "lead",
            amount=row["amount"] or "",
            amount_unit=row["amount_unit"] or "",
            region=row["region"] or "",
            category=row["category"] or "",
            project_type=row["project_type"] or "",
            nature=row["nature"] or "",
            registration_deadline=row["registration_deadline"] or "",
            submission_deadline=row["submission_deadline"] or "",
            bid_opening_time=row["bid_opening_time"] or "",
            deadline_source=row["deadline_source"] or "",
            urgency_reference_time=row["urgency_reference_time"] or "",
            urgency_reference_type=row["urgency_reference_type"] or "",
            ai_extract_status=row["ai_extract_status"] or "pending",
            detail_fetch_status=row["detail_fetch_status"] or "pending",
            detail_fetched_at=row["detail_fetched_at"] or "",
            detail_text=row["detail_text"] or "",
            ai_extracted_data=self._json_loads(row["ai_extracted_data"], {}),
            manual_overrides=self._json_loads(row["manual_overrides"], {}),
            non_follow_reasons=self._json_loads(row["non_follow_reasons"], []),
            review_notes=row["review_notes"] or "",
            ai_recommendation=row["ai_recommendation"] or "",
            ai_extract_error=row["ai_extract_error"] or "",
            detail_fetch_error=row["detail_fetch_error"] or "",
            updated_at=row["updated_at"] or "",
        )

    def exists(self, bid: BidInfo) -> bool:
        """检查招标信息是否已存在"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM bids WHERE unique_id = ?", (bid.unique_id,))
        return cursor.fetchone() is not None

    def save(self, bid: BidInfo, notified: bool = False):
        """保存招标信息，返回新记录行 id，重复时返回 False。"""
        if self.exists(bid):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bids (
                unique_id, title, url, publish_date, source, content, purchaser, notified,
                fit_status, follow_decision, urgency, urgency_source, project_stage,
                amount, amount_unit, region, category, project_type, nature,
                registration_deadline, submission_deadline, bid_opening_time,
                deadline_source, urgency_reference_time, urgency_reference_type,
                ai_extract_status, detail_fetch_status, detail_fetched_at, detail_text,
                ai_extracted_data, manual_overrides, non_follow_reasons, review_notes,
                ai_recommendation, ai_extract_error, detail_fetch_error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bid.unique_id,
                bid.title,
                bid.url,
                bid.publish_date,
                bid.source,
                bid.content,
                bid.purchaser,
                1 if notified else 0,
                bid.fit_status or "pending",
                bid.follow_decision or "pending",
                bid.urgency or "",
                bid.urgency_source or "",
                bid.project_stage or "lead",
                bid.amount or "",
                bid.amount_unit or "",
                bid.region or "",
                bid.category or "",
                bid.project_type or "",
                bid.nature or "",
                bid.registration_deadline or "",
                bid.submission_deadline or "",
                bid.bid_opening_time or "",
                bid.deadline_source or "",
                bid.urgency_reference_time or "",
                bid.urgency_reference_type or "",
                bid.ai_extract_status or "pending",
                bid.detail_fetch_status or "pending",
                bid.detail_fetched_at or "",
                bid.detail_text or "",
                self._json_dumps(bid.ai_extracted_data),
                self._json_dumps(bid.manual_overrides),
                json.dumps(bid.non_follow_reasons or [], ensure_ascii=False),
                bid.review_notes or "",
                bid.ai_recommendation or "",
                bid.ai_extract_error or "",
                bid.detail_fetch_error or "",
                bid.updated_at or datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def mark_notified(self, bids):
        """标记招标信息已发送通知

        Args:
            bids: 可以是单个BidInfo、BidInfo列表、或URL列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if isinstance(bids, BidInfo):
            cursor.execute("UPDATE bids SET notified = 1 WHERE unique_id = ?", (bids.unique_id,))
        elif isinstance(bids, list) and len(bids) > 0:
            if isinstance(bids[0], BidInfo):
                for bid in bids:
                    cursor.execute("UPDATE bids SET notified = 1 WHERE unique_id = ?", (bid.unique_id,))
            elif isinstance(bids[0], str):
                for url in bids:
                    unique_id = hashlib.md5(url.encode()).hexdigest()
                    cursor.execute("UPDATE bids SET notified = 1 WHERE unique_id = ?", (unique_id,))

        conn.commit()

    def get_unnotified(self) -> list[BidInfo]:
        """获取未通知的招标信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bids WHERE notified = 0")
        return [self._row_to_bid(row) for row in cursor.fetchall()]

    def get_recent(self, days: int = 7) -> list[BidInfo]:
        """获取最近几天的招标信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM bids
            WHERE datetime(created_at) > datetime('now', ?)
            ORDER BY created_at DESC
            """,
            (f"-{days} days",),
        )
        return [self._row_to_bid(row) for row in cursor.fetchall()]

    def get_all(self) -> list[BidInfo]:
        """获取所有招标信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bids ORDER BY created_at DESC")
        return [self._row_to_bid(row) for row in cursor.fetchall()]

    def get_by_id(self, result_id: int) -> Optional[BidInfo]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bids WHERE id = ?", (result_id,))
        row = cursor.fetchone()
        return self._row_to_bid(row) if row else None

    def query_results(
        self,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BidInfo], int]:
        filters = filters or {}
        where_parts = []
        params = []

        for key, value in filters.items():
            column = RESULT_QUERY_FILTERS.get(key)
            if column is None:
                raise ValueError(f"Unsupported query filter: {key}")
            where_parts.append(f"{column} = ?")
            params.append(value)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM bids {where_clause}", params)
        total = cursor.fetchone()[0]
        cursor.execute(
            f"SELECT * FROM bids {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        return [self._row_to_bid(row) for row in cursor.fetchall()], total

    def update_review(self, result_ids: list[int], update: dict) -> None:
        if not result_ids or not update:
            return

        assignments = []
        params = []
        for key, value in update.items():
            assignments.append(f"{key} = ?")
            if key == "non_follow_reasons":
                params.append(json.dumps(value or [], ensure_ascii=False))
            else:
                params.append(value)
        assignments.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat(timespec="seconds"))
        placeholders = ",".join(["?"] * len(result_ids))
        params.extend(result_ids)

        conn = self._get_connection()
        conn.execute(
            f"UPDATE bids SET {', '.join(assignments)} WHERE id IN ({placeholders})",
            params,
        )
        conn.commit()

    def update_manual_overrides(self, result_id: int, overrides: dict) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE bids
            SET manual_overrides = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                self._json_dumps(overrides or {}),
                datetime.utcnow().isoformat(timespec="seconds"),
                result_id,
            ),
        )
        conn.commit()

    def update_ai_extraction(
        self,
        result_id: int,
        status: str,
        ai_data: Optional[dict],
        columns: Optional[dict],
        error: Optional[str] = None,
    ) -> None:
        columns = columns or {}
        assignments = [
            "ai_extract_status = ?",
            "ai_extracted_data = ?",
            "ai_extract_error = ?",
            "updated_at = ?",
        ]
        params = [
            status,
            self._json_dumps(ai_data or {}),
            error or "",
            datetime.utcnow().isoformat(timespec="seconds"),
        ]
        for key, value in columns.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        params.append(result_id)

        conn = self._get_connection()
        conn.execute(
            f"UPDATE bids SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()

    def update_detail_fetch(
        self,
        result_id: int,
        status: str,
        detail_text: str = "",
        error: Optional[str] = None,
    ) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE bids
            SET detail_fetch_status = ?, detail_fetched_at = ?, detail_text = ?,
                detail_fetch_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                datetime.utcnow().isoformat(timespec="seconds"),
                detail_text,
                error or "",
                datetime.utcnow().isoformat(timespec="seconds"),
                result_id,
            ),
        )
        conn.commit()

    def start_crawl_run(self, source_id: str, source_name: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT INTO crawl_runs (source_id, source_name, started_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, source_name, now, "running"),
        )
        conn.commit()
        return cursor.lastrowid

    def finish_crawl_run(self, run_id: int, status: str, counts: Optional[dict] = None) -> None:
        counts = counts or {}
        assignments = [
            "finished_at = ?",
            "status = ?",
            "error_message = ?",
        ]
        params = [
            datetime.utcnow().isoformat(timespec="seconds"),
            status,
            str(counts.get("error_message", ""))[:500],
        ]
        for column in (
            "fetched_count",
            "candidate_count",
            "parsed_count",
            "inserted_count",
            "updated_count",
            "skipped_count",
            "error_count",
        ):
            if column in counts:
                assignments.append(f"{column} = ?")
                params.append(int(counts[column]))
        params.append(run_id)
        conn = self._get_connection()
        conn.execute(
            f"UPDATE crawl_runs SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()

    def increment_crawl_run_counts(
        self,
        run_id: int,
        inserted_delta: int = 0,
        updated_delta: int = 0,
        skipped_delta: int = 0,
    ) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE crawl_runs
            SET inserted_count = inserted_count + ?,
                updated_count = updated_count + ?,
                skipped_count = skipped_count + ?
            WHERE id = ?
            """,
            (inserted_delta, updated_delta, skipped_delta, run_id),
        )
        conn.commit()

    def get_crawl_run(self, run_id: int) -> Optional[dict]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_recent_crawl_runs(self, limit: int = 50) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM crawl_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_all(self) -> int:
        """获取总记录数"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bids")
        return cursor.fetchone()[0]

    def clear_all(self):
        """清空所有数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bids")
        conn.commit()
