import os
import tempfile
import unittest

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from database.auth_storage import AuthStorage


class AuthStorageTests(unittest.TestCase):
    def test_bootstrap_admin_creates_first_active_admin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AuthStorage(os.path.join(tmpdir, "auth.db"))

            user = storage.ensure_admin_user("admin", "secret123")

            self.assertEqual(user["username"], "admin")
            self.assertEqual(user["role"], "admin")
            self.assertTrue(user["is_active"])
            self.assertTrue(storage.verify_password("admin", "secret123"))
            self.assertFalse(storage.verify_password("admin", "wrong"))

    def test_create_user_hashes_password_and_rejects_duplicate_username(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AuthStorage(os.path.join(tmpdir, "auth.db"))

            user = storage.create_user("sales", "secret123", role="user")

            self.assertEqual(user["username"], "sales")
            self.assertEqual(user["role"], "user")
            raw = storage._get_connection().execute(
                "SELECT password_hash FROM users WHERE username = ?",
                ("sales",),
            ).fetchone()[0]
            self.assertNotIn("secret123", raw)
            with self.assertRaises(ValueError):
                storage.create_user("sales", "another123", role="user")

    def test_session_lifecycle_returns_user_then_expires_on_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AuthStorage(os.path.join(tmpdir, "auth.db"))
            user = storage.create_user("sales", "secret123", role="user")

            token = storage.create_session(user["id"])
            session_user = storage.get_user_by_session(token)
            storage.delete_session(token)

            self.assertEqual(session_user["username"], "sales")
            self.assertEqual(session_user["role"], "user")
            self.assertIsNone(storage.get_user_by_session(token))

    def test_inactive_user_cannot_authenticate_or_use_existing_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AuthStorage(os.path.join(tmpdir, "auth.db"))
            user = storage.create_user("sales", "secret123", role="user")
            token = storage.create_session(user["id"])

            storage.set_user_active(user["id"], False)

            self.assertFalse(storage.verify_password("sales", "secret123"))
            self.assertIsNone(storage.get_user_by_session(token))


if __name__ == "__main__":
    unittest.main()
