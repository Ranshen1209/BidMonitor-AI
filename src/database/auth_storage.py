"""
轻量多用户认证存储。

使用 SQLite 保存用户和 session；密码使用 PBKDF2-HMAC-SHA256 哈希，
避免为当前小型部署引入额外认证服务依赖。
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional


PBKDF2_ITERATIONS = 260000
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
MIN_PASSWORD_LENGTH = 4
ALLOWED_ROLES = {"admin", "user"}


class AuthStorage:
    """SQLite-backed user and session store."""

    def __init__(self, db_path: str = "data/auth.db"):
        self.db_path = db_path
        self._local = threading.local()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
            conn.commit()

    def ensure_admin_user(self, username: str, password: str) -> Dict:
        """Create the first admin only when no active admin exists."""
        username = self._normalize_username(username)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM users WHERE role = 'admin' AND is_active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            return self._public_user(row)
        return self.create_user(username, password, role="admin")

    def create_user(self, username: str, password: str, role: str = "user") -> Dict:
        username = self._normalize_username(username)
        role = self._normalize_role(role)
        self._validate_password(password)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, updated_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (username, self._hash_password(password), role, self._now()),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc

        return self.get_user_by_id(cursor.lastrowid)

    def verify_password(self, username: str, password: str) -> Optional[Dict]:
        username = self._normalize_username(username)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        if not row or not self._verify_hash(password, row["password_hash"]):
            return None
        return self._public_user(row)

    def create_session(self, user_id: int, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + ttl_seconds
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()
        return token

    def get_user_by_session(self, token: Optional[str]) -> Optional[Dict]:
        if not token:
            return None
        self.delete_expired_sessions()
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
              AND sessions.expires_at > ?
              AND users.is_active = 1
            """,
            (token, time.time()),
        ).fetchone()
        return self._public_user(row) if row else None

    def delete_session(self, token: Optional[str]) -> None:
        if not token:
            return
        conn = self._get_connection()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

    def delete_expired_sessions(self) -> None:
        conn = self._get_connection()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        conn.commit()

    def list_users(self) -> List[Dict]:
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [self._public_user(row) for row in rows]

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(row) if row else None

    def update_user(
        self,
        user_id: int,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> Dict:
        updates = []
        params = []
        if role is not None:
            updates.append("role = ?")
            params.append(self._normalize_role(role))
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        if password:
            self._validate_password(password)
            updates.append("password_hash = ?")
            params.append(self._hash_password(password))

        if not updates:
            user = self.get_user_by_id(user_id)
            if not user:
                raise ValueError("用户不存在")
            return user

        updates.append("updated_at = ?")
        params.append(self._now())
        params.append(user_id)
        conn = self._get_connection()
        cursor = conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise ValueError("用户不存在")
        user = self.get_user_by_id(user_id)
        if user and is_active is False:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
        return user

    def set_user_active(self, user_id: int, is_active: bool) -> Dict:
        return self.update_user(user_id, is_active=is_active)

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS,
        ).hex()
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"

    def _verify_hash(self, password: str, password_hash: str) -> bool:
        try:
            scheme, iterations, salt, expected = password_hash.split("$", 3)
            if scheme != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            ).hex()
            return hmac.compare_digest(digest, expected)
        except Exception:
            return False

    def _public_user(self, row) -> Dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _normalize_username(self, username: str) -> str:
        username = (username or "").strip()
        if len(username) < 2 or len(username) > 64:
            raise ValueError("用户名长度需为 2-64 个字符")
        return username

    def _normalize_role(self, role: str) -> str:
        role = (role or "user").strip().lower()
        if role not in ALLOWED_ROLES:
            raise ValueError("角色只能是 admin 或 user")
        return role

    def _validate_password(self, password: str) -> None:
        if not password or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 位")

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
