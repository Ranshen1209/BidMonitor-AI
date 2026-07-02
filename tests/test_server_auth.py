import os
import asyncio
import json
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
SRC_DIR = os.path.join(ROOT_DIR, "src")
for path in [SERVER_DIR, SRC_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

import app
from database.auth_storage import AuthStorage


class AsgiResponse:
    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.text = body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


class MiniAsgiClient:
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app
        self.cookies = {}

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, json_body=None):
        body = b""
        headers = []
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers.append((b"content-type", b"application/json"))
        return self.request("POST", path, body=body, headers=headers)

    def request(self, method, path, body=b"", headers=None):
        response = asyncio.run(self._request(method, path, body, headers or []))
        set_cookie = response.headers.get("set-cookie")
        if set_cookie:
            pair = set_cookie.split(";", 1)[0]
            if "=" in pair:
                name, value = pair.split("=", 1)
                if value:
                    self.cookies[name] = value
                else:
                    self.cookies.pop(name, None)
        return response

    async def _request(self, method, path, body, headers):
        response_start = {}
        response_body = bytearray()
        request_sent = False
        encoded_headers = list(headers)
        if self.cookies:
            cookie = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            encoded_headers.append((b"cookie", cookie.encode("utf-8")))

        parsed_url = urlsplit(path)
        path_only = parsed_url.path or path
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path_only,
            "raw_path": path_only.encode("utf-8"),
            "query_string": parsed_url.query.encode("utf-8"),
            "headers": encoded_headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                response_start.update(message)
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        await self.asgi_app(scope, receive, send)
        raw_headers = response_start.get("headers", [])
        parsed_headers = {}
        for key, value in raw_headers:
            parsed_headers[key.decode("latin1").lower()] = value.decode("latin1")
        return AsgiResponse(response_start["status"], parsed_headers, bytes(response_body))


class ServerAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.auth_db = os.path.join(self.tmpdir.name, "auth.db")
        self.patcher = patch.object(app, "auth_storage", AuthStorage(self.auth_db))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        app.auth_storage.ensure_admin_user("admin", "secret123")
        app.app_state.config = app.load_config()
        self.client = MiniAsgiClient(app.app)

    def login(self, username="admin", password="secret123"):
        return self.client.post(
            "/api/auth/login",
            json_body={"username": username, "password": password},
        )

    def test_protected_api_returns_json_401_without_basic_auth_challenge(self):
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("content-type").split(";")[0], "application/json")
        self.assertNotIn("www-authenticate", {k.lower(): v for k, v in response.headers.items()})
        self.assertEqual(response.json()["detail"], "未登录或会话已失效")

    def test_login_sets_http_only_session_cookie_and_me_returns_user(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("bidmonitor_session=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["username"], "admin")
        self.assertEqual(me.json()["user"]["role"], "admin")

    def test_logout_deletes_session_cookie(self):
        self.login()

        response = self.client.post("/api/auth/logout")
        me = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertIn("bidmonitor_session=", response.headers.get("set-cookie", ""))
        self.assertEqual(me.status_code, 401)

    def test_admin_can_create_user_but_regular_user_cannot(self):
        self.login()
        created = self.client.post(
            "/api/users",
            json_body={"username": "sales", "password": "secret123", "role": "user"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["user"]["username"], "sales")

        self.client.post("/api/auth/logout")
        self.login("sales", "secret123")
        forbidden = self.client.post(
            "/api/users",
            json_body={"username": "ops", "password": "secret123", "role": "user"},
        )

        self.assertEqual(forbidden.status_code, 403)

    def test_static_frontend_root_does_not_trigger_basic_auth_prompt(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("www-authenticate", {k.lower(): v for k, v in response.headers.items()})
        self.assertIn("BidMonitor", response.text)

    def test_default_bootstrap_admin_uses_requested_admin_credentials(self):
        empty_auth_db = os.path.join(self.tmpdir.name, "empty-auth.db")
        with patch.object(app, "auth_storage", AuthStorage(empty_auth_db)):
            app.ensure_bootstrap_admin()

            user = app.auth_storage.verify_password("Admin", "123654")

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "admin")


if __name__ == "__main__":
    unittest.main()
