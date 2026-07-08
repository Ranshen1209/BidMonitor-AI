"""
BidMonitor 服务器端主应用
基于 FastAPI 构建的 RESTful API 服务
"""
import os
import sys
import json
import asyncio
import inspect
import logging
import threading
import copy
from http.cookies import SimpleCookie
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request, Response, Body
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # pragma: no cover - exercised through import-time tests
    class HTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str = "", headers=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    class _StubRequest:
        def __init__(self, scope=None):
            self.scope = scope or {}
            self.cookies = {}
            for key, value in self.scope.get("headers", []):
                if key.lower() == b"cookie":
                    parsed = SimpleCookie(value.decode("latin1"))
                    self.cookies.update({name: morsel.value for name, morsel in parsed.items()})

    class _StubResponse:
        def __init__(self, content=None, status_code=200, headers=None, media_type=None):
            self.content = content
            self.status_code = status_code
            self.headers = headers.copy() if isinstance(headers, dict) else {}
            self.media_type = media_type
            if isinstance(content, str) and os.path.exists(content):
                with open(content, "r", encoding="utf-8") as f:
                    self.content = f.read()
                self.media_type = self.media_type or "text/html"

        def set_cookie(
            self,
            key,
            value,
            max_age=None,
            httponly=False,
            secure=False,
            samesite=None,
            path="/",
        ):
            parts = [f"{key}={value}"]
            if max_age is not None:
                parts.append(f"Max-Age={max_age}")
            if path:
                parts.append(f"Path={path}")
            if httponly:
                parts.append("HttpOnly")
            if secure:
                parts.append("Secure")
            if samesite:
                parts.append(f"SameSite={samesite}")
            self.headers["set-cookie"] = "; ".join(parts)

        def delete_cookie(self, key, path="/"):
            parts = [f"{key}=", "Max-Age=0"]
            if path:
                parts.append(f"Path={path}")
            self.headers["set-cookie"] = "; ".join(parts)

    class _StubApp:
        def __init__(self, *args, **kwargs):
            self.routes = {}

        def add_middleware(self, *args, **kwargs):
            return None

        def mount(self, *args, **kwargs):
            return None

        def _route(self, method, path):
            def decorator(fn):
                self.routes[(method, path)] = fn
                return fn
            return decorator

        def get(self, *args, **kwargs):
            return self._route("GET", args[0])

        def post(self, *args, **kwargs):
            return self._route("POST", args[0])

        def delete(self, *args, **kwargs):
            return self._route("DELETE", args[0])

        def patch(self, *args, **kwargs):
            return self._route("PATCH", args[0])

        async def __call__(self, scope, receive, send):
            if scope.get("type") != "http":
                raise RuntimeError("Stub FastAPI only supports HTTP ASGI scopes")

            endpoint = self.routes.get((scope.get("method"), scope.get("path")))
            if endpoint is None:
                await self._send_json(send, 404, {"detail": "Not Found"})
                return

            request = _StubRequest(scope)
            response = _StubResponse()
            body = await self._read_body(receive)
            try:
                payload = json.loads(body.decode("utf-8")) if body else None
            except json.JSONDecodeError:
                payload = None

            try:
                result = endpoint(**self._build_kwargs(endpoint, request, response, payload))
                if inspect.isawaitable(result):
                    result = await result
            except HTTPException as exc:
                await self._send_json(send, exc.status_code, {"detail": exc.detail}, headers=exc.headers)
                return

            if isinstance(result, _StubResponse):
                await self._send_response(send, result.status_code, result.content, result.headers, result.media_type)
                return
            await self._send_json(send, response.status_code, result, headers=response.headers)

        async def _read_body(self, receive):
            chunks = []
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            return b"".join(chunks)

        def _build_kwargs(self, endpoint, request, response, payload):
            kwargs = {}
            for name, param in inspect.signature(endpoint).parameters.items():
                default = param.default
                annotation = param.annotation
                if name == "request" or annotation is _StubRequest:
                    kwargs[name] = request
                elif name == "response" or annotation is _StubResponse:
                    kwargs[name] = response
                elif callable(default) and getattr(default, "__name__", "") == "get_current_user":
                    kwargs[name] = default(request)
                elif callable(default) and getattr(default, "__name__", "") == "require_admin":
                    kwargs[name] = default(get_current_user(request))
                elif payload is not None and self._is_body_model(annotation):
                    kwargs[name] = annotation(**payload)
                elif payload is not None and (default is Ellipsis or annotation is Any):
                    kwargs[name] = payload
            return kwargs

        def _is_body_model(self, annotation):
            try:
                return inspect.isclass(annotation) and issubclass(annotation, BaseModel)
            except NameError:
                return False

        async def _send_json(self, send, status, payload, headers=None):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            response_headers = {"content-type": "application/json", **(headers or {})}
            await self._send_raw(send, status, response_headers, body)

        async def _send_response(self, send, status, content, headers=None, media_type=None):
            if isinstance(content, bytes):
                body = content
            elif content is None:
                body = b""
            else:
                body = str(content).encode("utf-8")
            response_headers = headers or {}
            if media_type and "content-type" not in response_headers:
                response_headers = {"content-type": media_type, **response_headers}
            await self._send_raw(send, status, response_headers, body)

        async def _send_raw(self, send, status, headers, body):
            encoded_headers = [
                (key.lower().encode("latin1"), value.encode("latin1"))
                for key, value in (headers or {}).items()
            ]
            await send({"type": "http.response.start", "status": status, "headers": encoded_headers})
            await send({"type": "http.response.body", "body": body})

    class _StubStaticFiles:
        def __init__(self, *args, **kwargs):
            pass

    FastAPI = _StubApp
    StaticFiles = _StubStaticFiles
    HTMLResponse = _StubResponse
    FileResponse = _StubResponse
    CORSMiddleware = object
    BackgroundTasks = object
    Request = _StubRequest
    Response = _StubResponse

    def Depends(value):
        return value

    def Body(default=None):
        return default

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - exercised through import-time tests
    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def dict(self, exclude_unset=False):
            return self.__dict__.copy()
import secrets

# 添加 src 目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:  # pragma: no cover - exercised through import-time tests
    class AsyncIOScheduler:
        running = False

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

        def add_job(self, *args, **kwargs):
            return None

        def remove_job(self, *args, **kwargs):
            return None

        def reschedule_job(self, *args, **kwargs):
            return None

    class IntervalTrigger:
        def __init__(self, *args, **kwargs):
            pass

# 导入原有模块
from monitor_core import MonitorCore, get_default_sites
from database.storage import Storage, BidInfo
from database.auth_storage import AuthStorage, SESSION_TTL_SECONDS
from ai_guard import AIGuard
from utils.logging_text import strip_log_icons
from results.review import (
    DEFAULT_NON_FOLLOW_REASON_TAGS,
    FIT_STATUSES,
    FOLLOW_DECISIONS,
    PROJECT_STAGES,
    URGENCIES,
    resolve_result_data,
    validate_review_update,
)
from crawler.qianlima_vip import QIANLIMA_MEMBER_INFO_ENDPOINT, has_qianlima_cookie, parse_membership_payload
from crawler.url_list import UrlListCrawler

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局状态
class AppState:
    def __init__(self):
        self.is_running = False
        self.monitor_core: Optional[MonitorCore] = None
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.last_run_time: Optional[datetime] = None
        self.next_run_time: Optional[datetime] = None
        self.logs: List[str] = []
        self.config: Dict[str, Any] = {}
        self.storage = Storage()
        self.stop_event = threading.Event()  # 停止事件，用于中断正在运行的任务
        self.current_task_running = False  # 标记当前是否有任务正在执行
        self.today_rounds = 0  # 今日监控轮数
        self.today_date = datetime.now().strftime('%Y-%m-%d')  # 今日日期
        # 进度跟踪
        self.progress_current = 0  # 当前爬取的网站序号
        self.progress_total = 0    # 总网站数
        self.progress_site = ""    # 当前正在爬取的网站名称
        
    def add_log(self, message: str):
        message = strip_log_icons(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        # 细粒度爬取日志较多，保留更长的最近窗口供前端排查。
        if len(self.logs) > LOG_MEMORY_LIMIT:
            self.logs = self.logs[-LOG_MEMORY_LIMIT:]
        logger.info(message)

app_state = AppState()

# 配置文件路径
CONFIG_FILE = os.path.join(BASE_DIR, 'server', 'server_config.json')
LOG_MEMORY_LIMIT = 20000
LOG_API_LIMIT = 20000
DEFAULT_URL_LIST_PATH = '/Users/cervine/Documents/Rule-Project/projects/opportunity-collection/output/materials/bid_related_url_list.txt'
DEFAULT_URL_SOURCES_PATH = os.path.join(BASE_DIR, 'server', 'url_sources.json')
DEFAULT_SITE_TOPOLOGIES_PATH = os.path.join(BASE_DIR, 'server', 'site_topologies.json')
AUTH_DB_FILE = os.environ.get("BIDMONITOR_AUTH_DB", os.path.join(BASE_DIR, "data", "auth.db"))
SESSION_COOKIE_NAME = "bidmonitor_session"
COOKIE_SECURE = os.environ.get("BIDMONITOR_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
auth_storage = AuthStorage(AUTH_DB_FILE)
QIANLIMA_CRAWLER_CONFIG_KEYS = (
    'qianlima_vip_search_enabled',
    'qianlima_backfill_enabled',
    'qianlima_num_per_page',
    'qianlima_max_pages_per_keyword',
    'qianlima_backfill_max_pages_per_keyword',
    'qianlima_stop_after_duplicate_pages',
    'qianlima_max_results_per_run',
    'qianlima_time_type',
    'qianlima_sort_type',
    'qianlima_search_endpoint',
    'qianlima_member_info_endpoint',
)

KEYWORD_LIBRARY_DB_FILE = os.environ.get(
    "BIDMONITOR_KW_DB", os.path.join(BASE_DIR, "data", "keyword_library.db")
)

# 默认关键词库（首次启动自动种入）
DEFAULT_KEYWORD_LIBRARY = [
    # 音视频会议
    {"business_direction":"音视频会议","sub_category":"","keyword":"音视频","synonyms":"音视频系统","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"会议系统","synonyms":"视频会议,会议室,无纸化会议","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"会议扩声","synonyms":"会议音响,会议摄像机,会议终端","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"会议平板","synonyms":"会议一体机,智能会议室","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"多功能厅","synonyms":"报告厅,阶梯教室","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"录播教室","synonyms":"录播系统,精品录播,常态化录播","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"扩声系统","synonyms":"音频系统,调音台,功放,音箱","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"麦克风","synonyms":"无线话筒,鹅颈话筒","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"中控系统","synonyms":"矩阵切换器,视频矩阵,分布式坐席,分布式系统","match_scope":"title_content","note":""},
    {"business_direction":"音视频会议","sub_category":"","keyword":"同声传译","synonyms":"远程会议,智慧会议,会议预约,会议管理平台","match_scope":"title_content","note":""},
    # 显示大屏与指挥中心
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"大屏","synonyms":"LED显示屏,LCD拼接屏,液晶拼接屏,DLP大屏","match_scope":"title_content","note":""},
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"显示系统","synonyms":"可视化大屏","match_scope":"title_content","note":""},
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"指挥中心","synonyms":"调度中心,应急指挥,作战指挥","match_scope":"title_content","note":""},
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"融媒体中心","synonyms":"监控中心,值班室,控制室","match_scope":"title_content","note":""},
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"可视化平台","synonyms":"信息发布屏,信息发布系统","match_scope":"title_content","note":""},
    {"business_direction":"显示大屏与指挥中心","sub_category":"","keyword":"触控一体机","synonyms":"电子班牌,导览屏,数字标牌","match_scope":"title_content","note":""},
    # AI视频与智能分析
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"AI视频","synonyms":"智能视频分析,视频智能分析,视频结构化","match_scope":"title_content","note":""},
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"行为分析","synonyms":"周界识别,人脸识别,车辆识别","match_scope":"title_content","note":""},
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"算法平台","synonyms":"视觉识别,视频算法,智能预警","match_scope":"title_content","note":""},
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"AI管理平台","synonyms":"智能管理平台,智慧监管平台","match_scope":"title_content","note":""},
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"视频联网平台","synonyms":"视频汇聚平台,视频云平台","match_scope":"title_content","note":""},
    {"business_direction":"AI视频与智能分析","sub_category":"","keyword":"安防智能化","synonyms":"图像识别,客流分析,人员轨迹,异常行为识别","match_scope":"title_content","note":""},
    # 基础弱电/智能化工程
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"弱电","synonyms":"弱电工程,基础弱电","match_scope":"title_content","note":""},
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"智能化","synonyms":"建筑智能化,楼宇智能化,智能化工程,智能化系统","match_scope":"title_content","note":""},
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"信息化","synonyms":"信息化建设,信息化改造","match_scope":"title_content","note":""},
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"智慧校园","synonyms":"智慧园区,智慧楼宇,智慧社区","match_scope":"title_content","note":""},
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"系统集成","synonyms":"集成服务,工程改造","match_scope":"title_content","note":""},
    {"business_direction":"基础弱电/智能化工程","sub_category":"","keyword":"设备采购及安装","synonyms":"维保,运维,维修,改造,升级,扩容","match_scope":"title_content","note":""},
    # 安防监控
    {"business_direction":"安防监控","sub_category":"","keyword":"安防","synonyms":"安防系统,安全防护","match_scope":"title_content","note":""},
    {"business_direction":"安防监控","sub_category":"","keyword":"监控","synonyms":"视频监控,监控系统,CCTV","match_scope":"title_content","note":""},
    {"business_direction":"安防监控","sub_category":"","keyword":"摄像头","synonyms":"摄像机,高清摄像,网络摄像","match_scope":"title_content","note":""},
    {"business_direction":"安防监控","sub_category":"","keyword":"安防工程","synonyms":"安防建设,安防改造","match_scope":"title_content","note":""},
    # 门禁一卡通
    {"business_direction":"门禁一卡通","sub_category":"","keyword":"门禁","synonyms":"门禁系统,门禁控制","match_scope":"title_content","note":""},
    {"business_direction":"门禁一卡通","sub_category":"","keyword":"一卡通","synonyms":"智慧一卡通,校园一卡通","match_scope":"title_content","note":""},
    {"business_direction":"门禁一卡通","sub_category":"","keyword":"人行通道","synonyms":"闸机,翼闸,三辊闸","match_scope":"title_content","note":""},
    # 综合布线/网络/机房
    {"business_direction":"综合布线/网络/机房","sub_category":"","keyword":"综合布线","synonyms":"网络布线,结构化布线","match_scope":"title_content","note":""},
    {"business_direction":"综合布线/网络/机房","sub_category":"","keyword":"网络工程","synonyms":"局域网,无线网络,WiFi覆盖","match_scope":"title_content","note":""},
    {"business_direction":"综合布线/网络/机房","sub_category":"","keyword":"机房","synonyms":"数据中心,IDC,机房建设","match_scope":"title_content","note":""},
    # 可做杂项
    {"business_direction":"可做杂项","sub_category":"","keyword":"采购意向","synonyms":"招标公告,竞争性磋商,公开招标","match_scope":"title_content","note":""},
    {"business_direction":"可做杂项","sub_category":"","keyword":"广播","synonyms":"广播系统,IP广播,校园广播","match_scope":"title_content","note":""},
]


class KeywordLibraryStorage:
    """关键词库 SQLite 存储"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._seed_defaults()

    def _conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS keyword_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    business_direction TEXT NOT NULL DEFAULT '',
                    sub_category TEXT NOT NULL DEFAULT '',
                    keyword TEXT NOT NULL DEFAULT '',
                    synonyms TEXT NOT NULL DEFAULT '',
                    match_scope TEXT NOT NULL DEFAULT 'title_content',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()

    def _seed_defaults(self):
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM keyword_library").fetchone()[0]
            if count == 0:
                for i, entry in enumerate(DEFAULT_KEYWORD_LIBRARY):
                    conn.execute(
                        "INSERT INTO keyword_library (enabled,business_direction,sub_category,keyword,synonyms,match_scope,note,sort_order) VALUES (?,?,?,?,?,?,?,?)",
                        (1, entry["business_direction"], entry.get("sub_category",""), entry["keyword"],
                         entry.get("synonyms",""), entry.get("match_scope","title_content"), entry.get("note",""), i)
                    )
                conn.commit()

    def list_all(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id,enabled,business_direction,sub_category,keyword,synonyms,match_scope,note,sort_order FROM keyword_library ORDER BY sort_order,id"
            ).fetchall()
        return [dict(r) for r in rows]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO keyword_library (enabled,business_direction,sub_category,keyword,synonyms,match_scope,note) VALUES (?,?,?,?,?,?,?)",
                (int(bool(data.get("enabled", True))), data.get("business_direction",""),
                 data.get("sub_category",""), data.get("keyword",""),
                 data.get("synonyms",""), data.get("match_scope","title_content"), data.get("note",""))
            )
            conn.commit()
            row = conn.execute("SELECT * FROM keyword_library WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def update(self, entry_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fields = []
        values = []
        for key in ("enabled","business_direction","sub_category","keyword","synonyms","match_scope","note","sort_order"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(int(bool(data[key])) if key == "enabled" else data[key])
        if not fields:
            return None
        values.append(entry_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE keyword_library SET {','.join(fields)} WHERE id=?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM keyword_library WHERE id=?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def delete(self, entry_id: int) -> bool:
        with self._conn() as conn:
            result = conn.execute("DELETE FROM keyword_library WHERE id=?", (entry_id,))
            conn.commit()
        return result.rowcount > 0

    def bulk_toggle(self, ids: List[int], enabled: bool) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            result = conn.execute(
                f"UPDATE keyword_library SET enabled=? WHERE id IN ({placeholders})",
                [int(enabled)] + ids
            )
            conn.commit()
        return result.rowcount

    def derive_keywords(self) -> List[str]:
        """从启用的关键词库条目派生关键词列表（主词+同义词）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT keyword,synonyms FROM keyword_library WHERE enabled=1"
            ).fetchall()
        result = []
        seen = set()
        for row in rows:
            for term in [row["keyword"]] + [s.strip() for s in row["synonyms"].split(",") if s.strip()]:
                if term and term not in seen:
                    seen.add(term)
                    result.append(term)
        return result

    def export_csv(self) -> str:
        import io, csv
        rows = self.list_all()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["id","enabled","business_direction","sub_category","keyword","synonyms","match_scope","note"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k,"") for k in writer.fieldnames})
        return buf.getvalue()

    def import_csv(self, csv_text: str) -> Dict[str, Any]:
        import io, csv
        reader = csv.DictReader(io.StringIO(csv_text.lstrip(chr(0xfeff))))
        added = 0
        skipped = 0
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if not kw:
                skipped += 1
                continue
            self.create({
                "enabled": str(row.get("enabled","1")).strip() not in ("0","false","False",""),
                "business_direction": row.get("business_direction",""),
                "sub_category": row.get("sub_category",""),
                "keyword": kw,
                "synonyms": row.get("synonyms",""),
                "match_scope": row.get("match_scope","title_content"),
                "note": row.get("note",""),
            })
            added += 1
        return {"added": added, "skipped": skipped}


keyword_library_storage = KeywordLibraryStorage(KEYWORD_LIBRARY_DB_FILE)


def is_legacy_url_list_key(key: Any) -> bool:
    return str(key).startswith('url_list_')

def is_stale_builtin_path(path: Any, filename: str) -> bool:
    """识别迁移后遗留的项目内置数据文件绝对路径。"""
    if not path:
        return False
    normalized = os.path.normpath(str(path)).replace('\\', '/')
    current_builtin = os.path.normpath(os.path.join(BASE_DIR, 'server', filename)).replace('\\', '/')
    if normalized == current_builtin:
        return False
    if os.path.basename(normalized) != filename:
        return False
    parts = normalized.split('/')
    return 'BidMonitor-AI' in parts and 'server' in parts

def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """补齐旧配置缺少的新字段，不覆盖用户已有值。"""
    if isinstance(config.get('enabled_sites'), list):
        config['enabled_sites'] = [
            key for key in config['enabled_sites']
            if not is_legacy_url_list_key(key)
        ]
    if not isinstance(config.get('site_metadata'), dict):
        config['site_metadata'] = {}
    else:
        config['site_metadata'] = {
            key: value for key, value in config['site_metadata'].items()
            if not is_legacy_url_list_key(key)
        }
    if not isinstance(config.get('non_follow_reason_tags'), list):
        config['non_follow_reason_tags'] = DEFAULT_NON_FOLLOW_REASON_TAGS.copy()
    ai_config = config.setdefault('ai_config', {})
    if not ai_config.get('endpoint_type'):
        base_url = (ai_config.get('base_url') or '').rstrip('/').lower()
        ai_config['endpoint_type'] = 'chat_completions' if base_url.endswith('/chat/completions') else 'responses'
    if is_stale_builtin_path(config.get('site_topologies_path'), 'site_topologies.json'):
        config['site_topologies_path'] = DEFAULT_SITE_TOPOLOGIES_PATH
    for source in config.get('csv_url_sources', []):
        source_path = source.get('file_path')
        if source_path == DEFAULT_URL_LIST_PATH or is_stale_builtin_path(source_path, 'url_sources.json'):
            source['name'] = '招标URL源'
            source['file_path'] = DEFAULT_URL_SOURCES_PATH
            source['source_type'] = 'json'
        if is_stale_builtin_path(source.get('site_topologies_path'), 'site_topologies.json'):
            source['site_topologies_path'] = DEFAULT_SITE_TOPOLOGIES_PATH
        source.setdefault('domain_delay', 2)
        source.setdefault('concurrency', 4)
        source.setdefault('auth_cookies', [])
        if str(source.get('file_path', '')).endswith('.json'):
            source.setdefault('source_type', 'json')
    config.setdefault('qianlima_vip_search_enabled', True)
    config.setdefault('qianlima_backfill_enabled', False)
    config.setdefault('qianlima_num_per_page', 20)
    config.setdefault('qianlima_max_pages_per_keyword', 30)
    config.setdefault('qianlima_backfill_max_pages_per_keyword', 100)
    config.setdefault('qianlima_stop_after_duplicate_pages', 3)
    config.setdefault('qianlima_max_results_per_run', 1000)
    config.setdefault('qianlima_time_type', 8)
    config.setdefault('qianlima_sort_type', 6)
    config.pop('custom_sites', None)
    return config

def load_config() -> Dict[str, Any]:
    """加载配置"""
    default_config = {
        'keywords': '弱电,智能化,安防,监控,门禁,广播,会议系统,大屏,楼宇智能化,信息化,综合布线,运维,维保,采购意向,招标公告,竞争性磋商,公开招标',
        'exclude': '大疆',
        'must_contain': '',
        'interval': 10,
        'enabled_sites': [],
        'email_enabled': True,
        'sms_enabled': True,
        'voice_enabled': False,
        'wechat_enabled': False,
        'ai_enabled': False,
        'email_configs': [],  # 开源版本默认空
        'sms_config': {
            'provider': 'aliyun',
            'sign_name': '',
            'template_code': '',
            'access_key_id': '',
            'access_key_secret': ''
        },
        'voice_config': {
            'provider': 'aliyun',
            'access_key_id': '',
            'access_key_secret': '',
            'called_show_number': '',
            'tts_code': ''
        },
        'wechat_config': {
            'provider': 'pushplus',
            'token': ''
        },
        'ai_config': {
            'enable': False,
            'base_url': 'https://api.sakrylle.com/v1',
            'api_key': '',  # 请填入您的API Key
            'model': 'grok-4.20-fast',
            'endpoint_type': 'responses',
        },
        'contacts': [],  # 开源版本默认空
        'use_selenium': False,  # Selenium浏览器模式开关
        'browser_backend': {
            'mode': 'http',
            'cloakbrowser_enabled': False,
            'note': '仅支持授权 Cookie、人工验证码处理、限频和普通浏览器渲染；不内置隐身绕过能力。'
        },
        'site_topologies_path': DEFAULT_SITE_TOPOLOGIES_PATH,
        'non_follow_reason_tags': DEFAULT_NON_FOLLOW_REASON_TAGS.copy(),
        'site_metadata': {},
        'csv_url_sources': [
            {
                'name': '招标URL源',
                'source_type': 'json',
                'file_path': DEFAULT_URL_SOURCES_PATH,
                'enabled': True,
                'domain_delay': 2,
                'concurrency': 4,
                'auth_cookies': []
            }
        ]
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    return normalize_config(default_config)

def save_config(config: Dict[str, Any]):
    """保存配置"""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """返回可暴露给前端的用户字段。"""
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "is_active": user["is_active"],
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }

def ensure_bootstrap_admin() -> None:
    """确保首次启动有一个管理员账号。"""
    username = os.environ.get("BIDMONITOR_ADMIN_USER", "Admin")
    password = os.environ.get("BIDMONITOR_ADMIN_PASSWORD", "123654")
    try:
        user = auth_storage.ensure_admin_user(username, password)
        logger.info("认证系统已就绪，管理员账号: %s", user["username"])
    except Exception as e:
        logger.error("初始化管理员账号失败: %s", e)

def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")

def get_current_user(request: Request) -> Dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = auth_storage.get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或会话已失效")
    return user

def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

# Pydantic 模型
class ConfigModel(BaseModel):
    keywords: Optional[str] = None
    exclude: Optional[str] = None
    must_contain: Optional[str] = None
    interval: Optional[int] = None
    enabled_sites: Optional[List[str]] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    voice_enabled: Optional[bool] = None
    wechat_enabled: Optional[bool] = None
    ai_enabled: Optional[bool] = None
    use_selenium: Optional[bool] = None  # Selenium浏览器模式开关
    browser_backend: Optional[Dict[str, Any]] = None
    site_topologies_path: Optional[str] = None
    qianlima_vip_search_enabled: Optional[bool] = None
    qianlima_backfill_enabled: Optional[bool] = None
    qianlima_num_per_page: Optional[int] = None
    qianlima_max_pages_per_keyword: Optional[int] = None
    qianlima_backfill_max_pages_per_keyword: Optional[int] = None
    qianlima_stop_after_duplicate_pages: Optional[int] = None
    qianlima_max_results_per_run: Optional[int] = None
    qianlima_time_type: Optional[int] = None
    qianlima_sort_type: Optional[int] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class StatusResponse(BaseModel):
    is_running: bool
    last_run_time: Optional[str]
    next_run_time: Optional[str]
    total_bids: int
    today_new: int
    interval: int

SITE_METADATA_FIELDS = {
    'display_name',
    'access_status',
    'requires_login',
    'has_antibot',
    'note',
    'last_checked_at',
    'last_diagnostic',
}

SITE_ACCESS_STATUSES = {
    'public_no_antibot',
    'login_no_antibot',
    'login_with_antibot',
    'js_limited',
    'commercial_limited',
    'unavailable',
    'unknown',
}

def sanitize_site_metadata(metadata: Any) -> Dict[str, Any]:
    """只保留管理员可维护的内置站点元数据字段。"""
    if not isinstance(metadata, dict):
        return {}
    sanitized = {
        key: value
        for key, value in metadata.items()
        if key in SITE_METADATA_FIELDS
    }
    if sanitized.get('access_status') not in SITE_ACCESS_STATUSES:
        sanitized.pop('access_status', None)
    return sanitized

def infer_site_access_defaults(name: str, url: str) -> Dict[str, Any]:
    """根据 URL/名称给内置站点提供保守的默认访问分类。"""
    text = f"{name} {url}".lower()
    login_markers = ('login', 'signin', 'sso', 'oauth', 'cas', 'passport', 'auth', '登录', '统一认证')
    antibot_markers = ('captcha', '验证码', '滑块', '人机验证')
    js_markers = ('javascript', 'js required', 'enablejs')
    commercial_markers = ('会员', 'vip', '付费', 'commercial')
    unavailable_markers = ('停用', '不可用', 'offline', 'unavailable')

    if any(marker in text for marker in unavailable_markers):
        return {'access_status': 'unavailable', 'requires_login': False, 'has_antibot': False}
    if any(marker in text for marker in commercial_markers):
        return {'access_status': 'commercial_limited', 'requires_login': True, 'has_antibot': False}
    if any(marker in text for marker in js_markers):
        return {'access_status': 'js_limited', 'requires_login': False, 'has_antibot': False}
    if any(marker in text for marker in login_markers):
        has_antibot = any(marker in text for marker in antibot_markers)
        return {
            'access_status': 'login_with_antibot' if has_antibot else 'login_no_antibot',
            'requires_login': True,
            'has_antibot': has_antibot,
        }
    return {'access_status': 'unknown', 'requires_login': False, 'has_antibot': False}

def build_site_response(key: str, info: Dict[str, Any], enabled_sites: List[str], metadata: Dict[str, Any]) -> Dict[str, Any]:
    default_name = info.get('name', key)
    url = info.get('url', '')
    site_metadata = sanitize_site_metadata(metadata.get(key, {}))
    display_name = site_metadata.get('display_name') or default_name
    access_defaults = infer_site_access_defaults(display_name, url)

    return {
        'key': key,
        'name': default_name,
        'display_name': display_name,
        'url': url,
        'enabled': key in enabled_sites,
        'access_status': site_metadata.get('access_status', access_defaults['access_status']),
        'requires_login': site_metadata.get('requires_login', access_defaults['requires_login']),
        'has_antibot': site_metadata.get('has_antibot', access_defaults['has_antibot']),
        'note': site_metadata.get('note'),
        'last_checked_at': site_metadata.get('last_checked_at'),
        'last_diagnostic': site_metadata.get('last_diagnostic'),
    }

def parse_sites_update_payload(payload: Any) -> Dict[str, Any]:
    """兼容旧 List[str]、新 {'sites': [...]} 和直接 List[Dict]。"""
    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        return {'enabled_sites': [item for item in payload if not is_legacy_url_list_key(item)], 'site_metadata': None}

    site_items = payload.get('sites') if isinstance(payload, dict) else payload
    if not isinstance(site_items, list):
        raise HTTPException(status_code=400, detail="网站配置格式无效")

    enabled_sites: List[str] = []
    site_metadata: Dict[str, Dict[str, Any]] = {}
    for item in site_items:
        if not isinstance(item, dict) or not item.get('key'):
            continue
        key = str(item['key'])
        if is_legacy_url_list_key(key):
            continue
        if item.get('enabled'):
            enabled_sites.append(key)
        sanitized = sanitize_site_metadata(item)
        if sanitized:
            site_metadata[key] = sanitized
    return {'enabled_sites': enabled_sites, 'site_metadata': site_metadata}

def qianlima_auth_cookies_from_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for source in config.get('csv_url_sources', []):
        for item in source.get('auth_cookies', []) or []:
            if isinstance(item, dict):
                cookies.append(item)
    return cookies

def build_qianlima_membership_crawler(config: Dict[str, Any]) -> UrlListCrawler:
    source_config = {
        "name": "千里马会员状态",
        "file_path": "",
        "auth_cookies": qianlima_auth_cookies_from_config(config),
        "domain_delay": config.get("domain_delay", 0),
    }
    crawler = UrlListCrawler(config, source_config)

    if not hasattr(crawler, "get_json"):
        def get_json(url: str):
            try:
                html, status_code, status_text = crawler._request_http("GET", url)
            except Exception as exc:
                return {}, 599, f"{exc.__class__.__name__}: request failed"
            try:
                return json.loads(html or "{}"), status_code, status_text
            except (TypeError, ValueError):
                return {}, status_code, status_text

        crawler.get_json = get_json
    return crawler

def build_crawler_overrides_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    overrides = {
        'enabled_sites': config.get('enabled_sites', []),
        'use_selenium': config.get('use_selenium', False),
        'browser_backend': config.get('browser_backend', {}),
        'site_topologies_path': config.get('site_topologies_path', DEFAULT_SITE_TOPOLOGIES_PATH),
        'csv_url_sources': config.get('csv_url_sources', []),
        'site_metadata': config.get('site_metadata', {}),
    }
    for key in QIANLIMA_CRAWLER_CONFIG_KEYS:
        if key in config:
            overrides[key] = config[key]
    return overrides

# 定时任务：执行监控
async def run_monitor_task():
    """执行一次监控任务"""
    # 检查是否应该运行
    if not app_state.is_running:
        return
    
    # 检查是否被中断
    if app_state.stop_event.is_set():
        app_state.add_log("检索任务被中断")
        return
    
    # 标记任务正在运行
    app_state.current_task_running = True
    
    app_state.add_log("=" * 40)
    app_state.add_log("开始执行检索任务...")
    app_state.last_run_time = datetime.now()
    
    try:
        config = app_state.config
        # 优先从关键词库派生；库为空时回落 config['keywords']
        _lib_keywords = keyword_library_storage.derive_keywords()
        if _lib_keywords:
            keywords = _lib_keywords
        else:
            keywords = [k.strip() for k in config.get('keywords', '').split(',') if k.strip()]
        exclude = [k.strip() for k in config.get('exclude', '').split(',') if k.strip()]
        must_contain = [k.strip() for k in config.get('must_contain', '').split(',') if k.strip()]
        
        # AI 配置
        ai_config = None
        if config.get('ai_enabled') and config.get('ai_config'):
            ai_config = copy.deepcopy(config['ai_config'])
            ai_config['enable'] = True
            ai_config['filter_keywords'] = keywords
            ai_config['exclude_keywords'] = exclude
            ai_config['must_contain_keywords'] = must_contain
        
        # 创建监控核心
        monitor = MonitorCore(
            keywords=keywords,
            exclude_keywords=exclude,
            must_contain_keywords=must_contain,
            log_callback=app_state.add_log,
            ai_config=ai_config,
            crawler_overrides=build_crawler_overrides_from_config(config),
        )
        
        if config.get('use_selenium'):
            app_state.add_log("浏览器渲染模式已启用")
        else:
            app_state.add_log("使用普通HTTP模式")
        
        # 设置爬虫总数
        app_state.progress_total = len(monitor.crawlers)
        app_state.progress_current = 0
        app_state.progress_site = ""
        
        # 进度回调函数
        def progress_callback(current, total, site_name):
            app_state.progress_current = current
            app_state.progress_total = total
            app_state.progress_site = site_name
        
        # 在线程池中执行同步的爬虫任务，防止阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: monitor.run_once(progress_callback=progress_callback, stop_event=app_state.stop_event)
        )
        
        # 检查是否被中断
        if app_state.stop_event.is_set():
            app_state.add_log("检索任务被中断")
            app_state.current_task_running = False
            return
        
        new_count = result.get('saved_count', result.get('new_count', 0))
        matched_count = result.get('matched_count', 0)
        app_state.add_log(f"检索完成，新增入库 {new_count} 条，推荐通知 {matched_count} 条")
        
        # 发送通知（如果有新结果且未被中断）
        if matched_count > 0 and not app_state.stop_event.is_set():
            await send_notifications(config, matched_count)
        
    except Exception as e:
        app_state.add_log(f"检索任务异常: {e}")
        logger.exception("Monitor task error")
    finally:
        app_state.current_task_running = False
        # 清除进度信息
        app_state.progress_current = 0
        app_state.progress_total = 0
        app_state.progress_site = ""
    
    # 增加今日监控轮数（如果日期变化则重置）
    today = datetime.now().strftime('%Y-%m-%d')
    if today != app_state.today_date:
        app_state.today_date = today
        app_state.today_rounds = 0
    app_state.today_rounds += 1
    app_state.add_log(f"📊 今日已完成第 {app_state.today_rounds} 轮监控")
    
    # 任务完成后，调度下一次执行（仅在仍在运行时）
    if app_state.is_running and not app_state.stop_event.is_set():
        interval = app_state.config.get('interval', 20)
        from datetime import timedelta
        from apscheduler.triggers.date import DateTrigger
        
        next_run = datetime.now() + timedelta(minutes=interval)
        app_state.next_run_time = next_run
        
        # 调度下一次任务
        if app_state.scheduler and app_state.scheduler.running:
            # 移除旧任务（如果存在）
            try:
                app_state.scheduler.remove_job('monitor_job')
            except:
                pass
            # 添加新的一次性任务
            app_state.scheduler.add_job(
                run_monitor_task,
                trigger=DateTrigger(run_date=next_run),
                id='monitor_job',
                replace_existing=True
            )
            app_state.add_log(f"⏰ 下次检索时间: {next_run.strftime('%H:%M:%S')}")

async def send_notifications(config: Dict, new_count: int):
    """发送通知"""
    # 使用最新的配置（支持运行期间修改配置立即生效）
    config = app_state.config
    
    # 复用原有的通知模块
    try:
        contacts = config.get('contacts', [])
        
        # 获取新增的招标信息用于通知
        unnotified_bids = app_state.storage.get_unnotified() if hasattr(app_state.storage, 'get_unnotified') else []
        
        for contact in contacts:
            if not contact.get('enabled', True):
                continue
            
            name = contact.get('name', '未知')
            
            # 邮件通知
            if config.get('email_enabled') and contact.get('email') and contact.get('email_password'):
                try:
                    email_type = contact.get('email_type', 'QQ邮箱')
                    smtp_configs = {
                        'QQ邮箱': {'smtp_server': 'smtp.qq.com', 'smtp_port': 465, 'use_ssl': True},
                        '163邮箱': {'smtp_server': 'smtp.163.com', 'smtp_port': 465, 'use_ssl': True},
                        'Gmail': {'smtp_server': 'smtp.gmail.com', 'smtp_port': 587, 'use_ssl': False},
                        'Outlook': {'smtp_server': 'smtp.office365.com', 'smtp_port': 587, 'use_ssl': False},
                        '企业邮箱': {'smtp_server': 'smtp.exmail.qq.com', 'smtp_port': 465, 'use_ssl': True},
                    }
                    smtp_config = smtp_configs.get(email_type, smtp_configs['QQ邮箱'])
                    
                    email_config_full = {
                        'smtp_server': smtp_config['smtp_server'],
                        'smtp_port': smtp_config['smtp_port'],
                        'use_ssl': smtp_config['use_ssl'],
                        'sender': contact['email'],
                        'password': contact['email_password'],
                        'receiver': contact['email'],
                    }
                    from notifier.email import EmailNotifier
                    notifier = EmailNotifier(email_config_full)
                    if notifier.send(unnotified_bids[:10]):  # 最多发送10条
                        app_state.add_log(f"📧 邮件通知成功: {name}")
                    else:
                        app_state.add_log(f"❌ 邮件通知失败: {name}")
                except Exception as e:
                    app_state.add_log(f"❌ 邮件通知异常 {name}: {e}")
            
            # 短信通知
            if config.get('sms_enabled') and contact.get('phone'):
                try:
                    sms_config = config.get('sms_config', {})
                    if sms_config.get('access_key_id') and sms_config.get('template_code'):
                        from notifier.sms import SMSNotifier
                        notifier = SMSNotifier(sms_config)
                        summary = {'count': new_count, 'source': '招标网站'}
                        if notifier.send(contact['phone'], summary=summary):
                            app_state.add_log(f"📱 短信通知成功: {name}")
                        else:
                            app_state.add_log(f"❌ 短信通知失败: {name}")
                except Exception as e:
                    app_state.add_log(f"❌ 短信通知异常 {name}: {e}")
            
            # 语音通知
            if config.get('voice_enabled') and contact.get('phone'):
                try:
                    from notifier.voice import VoiceNotifier
                    import time
                    time.sleep(3)  # 延迟3秒让网络恢复
                    voice_config = config.get('voice_config', {})
                    if voice_config.get('tts_code'):
                        notifier = VoiceNotifier(voice_config)
                        if notifier.call(contact['phone'], count=new_count, source="招标网站"):
                            app_state.add_log(f"📞 语音呼叫成功: {name}")
                        else:
                            app_state.add_log(f"❌ 语音呼叫失败: {name}")
                except Exception as e:
                    app_state.add_log(f"❌ 语音通知异常 {name}: {e}")
            
            # 微信通知
            if config.get('wechat_enabled') and contact.get('wechat_token'):
                try:
                    from notifier.wechat import WeChatNotifier
                    notifier = WeChatNotifier({
                        'provider': 'pushplus',
                        'token': contact['wechat_token']
                    })
                    if notifier.send(unnotified_bids[:10]):  # 最多发送10条
                        app_state.add_log(f"💬 微信通知成功: {name}")
                    else:
                        app_state.add_log(f"❌ 微信通知失败: {name}")
                except Exception as e:
                    app_state.add_log(f"❌ 微信通知异常 {name}: {e}")
                        
    except Exception as e:
        app_state.add_log(f"发送通知异常: {e}")

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    app_state.config = load_config()
    ensure_bootstrap_admin()
    app_state.add_log("BidMonitor 服务器已启动")
    
    yield
    
    # 关闭时
    if app_state.scheduler and app_state.scheduler.running:
        app_state.scheduler.shutdown()
    app_state.add_log("BidMonitor 服务器已关闭")

# 创建 FastAPI 应用
app = FastAPI(
    title="BidMonitor API",
    description="招标监控系统服务端 API",
    version="1.6",
    lifespan=lifespan
)

# 添加CORS中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)

# 静态文件
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# API 路由
@app.get("/", response_class=HTMLResponse)
async def root():
    """返回主页"""
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>BidMonitor 服务正在运行</h1><p>请访问 /static/index.html</p>")

@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    """站内登录，返回 HttpOnly session cookie。"""
    user = auth_storage.verify_password(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth_storage.create_session(user["id"])
    set_session_cookie(response, token)
    return {"success": True, "user": public_user(user)}

@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """退出登录并删除当前 session。"""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    auth_storage.delete_session(token)
    clear_session_cookie(response)
    return {"success": True, "message": "已退出登录"}

@app.get("/api/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)):
    """获取当前登录用户。"""
    return {"user": public_user(user)}

@app.get("/api/users")
async def list_users(user: Dict[str, Any] = Depends(require_admin)):
    """管理员查看用户列表。"""
    return {"users": [public_user(item) for item in auth_storage.list_users()]}

@app.post("/api/users")
async def create_user(req: CreateUserRequest, user: Dict[str, Any] = Depends(require_admin)):
    """管理员创建团队用户。"""
    try:
        created = auth_storage.create_user(req.username, req.password, req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "user": public_user(created)}

@app.patch("/api/users/{user_id}")
async def update_user(user_id: int, req: UpdateUserRequest, user: Dict[str, Any] = Depends(require_admin)):
    """管理员更新用户角色、状态或密码。"""
    try:
        updated = auth_storage.update_user(
            user_id,
            role=req.role,
            is_active=req.is_active,
            password=req.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "user": public_user(updated)}

@app.get("/api/status")
async def get_status(user: Dict[str, Any] = Depends(get_current_user)):
    """获取监控状态"""
    # 统计今日新增
    today_str = datetime.now().strftime('%Y-%m-%d')
    all_bids = app_state.storage.get_all() if hasattr(app_state.storage, 'get_all') else []
    
    # publish_date 是字符串格式如 "2025-12-18"
    today_new = 0
    for b in all_bids:
        if b.publish_date and b.publish_date.startswith(today_str):
            today_new += 1
    
    return {
        "is_running": app_state.is_running,
        "last_run_time": app_state.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if app_state.last_run_time else None,
        "next_run_time": app_state.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if app_state.next_run_time else None,
        "total_bids": len(all_bids),
        "today_new": today_new,
        "today_rounds": app_state.today_rounds,
        "interval": app_state.config.get('interval', 20),
        # 进度信息
        "progress_current": app_state.progress_current,
        "progress_total": app_state.progress_total,
        "progress_site": app_state.progress_site,
        "is_crawling": app_state.current_task_running
    }

@app.post("/api/start")
async def start_monitor(background_tasks: BackgroundTasks, user: Dict[str, Any] = Depends(get_current_user)):
    """开始监控"""
    if app_state.is_running:
        return {"success": False, "message": "监控已在运行中"}
    
    # 清除停止事件
    app_state.stop_event.clear()
    app_state.is_running = True
    interval = app_state.config.get('interval', 20)
    
    # 创建调度器（不立即添加定时任务，任务完成后再调度下一次）
    app_state.scheduler = AsyncIOScheduler()
    app_state.scheduler.start()
    
    # 立即执行一次（next_run_time会在任务完成后设置）
    app_state.next_run_time = None
    background_tasks.add_task(run_monitor_task)
    
    app_state.add_log(f"✅ 监控已启动，间隔 {interval} 分钟")
    
    return {"success": True, "message": "监控已启动"}

@app.post("/api/stop")
async def stop_monitor(user: Dict[str, Any] = Depends(get_current_user)):
    """停止监控"""
    if not app_state.is_running:
        return {"success": False, "message": "监控未在运行"}
    
    # 设置停止事件，通知正在运行的任务中断
    app_state.stop_event.set()
    app_state.is_running = False
    
    # 关闭调度器
    if app_state.scheduler and app_state.scheduler.running:
        app_state.scheduler.shutdown(wait=False)
        app_state.scheduler = None
    
    app_state.next_run_time = None
    app_state.add_log("⏹️ 监控已停止")
    
    # 如果有任务正在运行，提示用户
    if app_state.current_task_running:
        app_state.add_log("⚠️ 正在等待当前检索任务完成中断...")
    
    return {"success": True, "message": "监控已停止"}

@app.post("/api/run-once")
async def run_once(background_tasks: BackgroundTasks, user: Dict[str, Any] = Depends(get_current_user)):
    """立即执行一次检索（不需要启动监控也可使用）"""
    # 记录原始状态
    was_running = app_state.is_running
    app_state.stop_event.clear()  # 确保stop_event未设置
    
    async def manual_run_task():
        """手动运行任务的包装函数"""
        # 临时设置is_running为True以允许任务执行
        app_state.is_running = True
        try:
            await run_monitor_task()
        finally:
            # 如果原来不在运行，则恢复为停止状态
            if not was_running:
                app_state.is_running = False
                app_state.next_run_time = None
    
    background_tasks.add_task(manual_run_task)
    app_state.add_log("🔍 手动触发检索...")
    return {"success": True, "message": "已开始检索"}

@app.get("/api/config")
async def get_config(user: Dict[str, Any] = Depends(get_current_user)):
    """获取配置"""
    config = copy.deepcopy(app_state.config)
    return _mask_config_secrets(config)

@app.post("/api/config")
async def update_config(config: ConfigModel, user: Dict[str, Any] = Depends(get_current_user)):
    """更新配置"""
    update_data = config.dict(exclude_unset=True)
    app_state.config.update(update_data)
    save_config(app_state.config)
    
    # 如果正在运行且间隔时间改变，重新调度
    if app_state.is_running and 'interval' in update_data:
        new_interval = update_data['interval']
        if app_state.scheduler:
            app_state.scheduler.reschedule_job(
                'monitor_job',
                trigger=IntervalTrigger(minutes=new_interval)
            )
            app_state.add_log(f"⏱️ 检索间隔已调整为 {new_interval} 分钟")
    
    return {"success": True, "message": "配置已更新"}

@app.get("/api/sites")
async def get_sites(user: Dict[str, Any] = Depends(get_current_user)):
    """获取可用网站列表"""
    sites = get_default_sites()
    enabled = app_state.config.get('enabled_sites', [])
    metadata = app_state.config.get('site_metadata', {})
    
    result = []
    for key, info in sites.items():
        result.append(build_site_response(key, info, enabled, metadata))
    
    return result

@app.get("/api/sites/qianlima/membership")
async def get_qianlima_membership(user: Dict[str, Any] = Depends(get_current_user)):
    """获取千里马会员状态，不返回账号个人信息或 Cookie。"""
    config = app_state.config
    cookies = qianlima_auth_cookies_from_config(config)
    if not has_qianlima_cookie(cookies):
        return {"status": "missing_cookie", "reason": "未配置 qianlima.com 授权 Cookie"}

    crawler = build_qianlima_membership_crawler(config)
    try:
        payload, status_code, status_text = crawler.get_json(
            config.get("qianlima_member_info_endpoint") or QIANLIMA_MEMBER_INFO_ENDPOINT
        )
    except Exception as exc:
        return {"status": "failed", "reason": f"{exc.__class__.__name__}: request failed", "status_code": 599}
    if status_code in (401, 403):
        return {"status": "failed", "reason": "qianlima_cookie_invalid_or_expired", "status_code": status_code}
    if status_code >= 400:
        return {"status": "failed", "reason": f"HTTP {status_code}: {status_text}", "status_code": status_code}
    return parse_membership_payload(payload)

@app.post("/api/sites")
async def update_sites(payload: Any = Body(...), user: Dict[str, Any] = Depends(require_admin)):
    """更新启用的网站"""
    parsed = parse_sites_update_payload(payload)
    app_state.config['enabled_sites'] = parsed['enabled_sites']
    if parsed['site_metadata'] is not None:
        app_state.config['site_metadata'] = parsed['site_metadata']
    save_config(app_state.config)
    return {"success": True, "message": "网站配置已更新"}

def result_summary(bid: BidInfo) -> Dict[str, Any]:
    resolved = resolve_result_data(bid)
    return {
        "id": bid.id,
        "title": bid.title,
        "url": bid.url,
        "source": bid.source,
        "pub_date": bid.publish_date or None,
        "fit_status": bid.fit_status,
        "follow_decision": bid.follow_decision,
        "urgency": bid.urgency,
        "project_stage": bid.project_stage,
        "organization": resolved.get("organization"),
        "amount": resolved.get("amount"),
        "amount_unit": resolved.get("amount_unit"),
        "region": resolved.get("region"),
        "category": resolved.get("category"),
        "registration_deadline": resolved.get("registration_deadline"),
        "submission_deadline": resolved.get("submission_deadline"),
        "bid_opening_time": resolved.get("bid_opening_time"),
        "ai_extract_status": bid.ai_extract_status,
        "detail_fetch_status": bid.detail_fetch_status,
        "non_follow_reasons": bid.non_follow_reasons,
        "review_notes": bid.review_notes,
    }


def result_detail_payload(bid: BidInfo) -> Dict[str, Any]:
    return {
        **result_summary(bid),
        "content": bid.content,
        "purchaser": bid.purchaser,
        "project_type": bid.project_type,
        "nature": bid.nature,
        "deadline_source": bid.deadline_source,
        "urgency_source": bid.urgency_source,
        "urgency_reference_time": bid.urgency_reference_time,
        "urgency_reference_type": bid.urgency_reference_type,
        "detail_fetched_at": bid.detail_fetched_at,
        "detail_text": bid.detail_text,
        "ai_extracted_data": bid.ai_extracted_data or {},
        "manual_overrides": bid.manual_overrides or {},
        "resolved": resolve_result_data(bid),
        "ai_recommendation": bid.ai_recommendation,
        "ai_extract_error": bid.ai_extract_error,
        "detail_fetch_error": bid.detail_fetch_error,
        "updated_at": bid.updated_at,
        "created_at": bid.created_at,
    }


def _result_not_found(result_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"result {result_id} not found")


def _review_reason_tags() -> List[str]:
    tags = app_state.config.get("non_follow_reason_tags")
    if isinstance(tags, list) and tags:
        return tags
    return DEFAULT_NON_FOLLOW_REASON_TAGS.copy()


CONFIG_SECRET_MARKERS = ("password", "token", "secret", "api_key")
CONFIG_PUBLIC_SECRET_NAME_EXCEPTIONS = {"access_key_id"}

RESULT_OVERRIDE_FIELDS = {
    "organization",
    "amount",
    "amount_unit",
    "region",
    "category",
    "project_type",
    "nature",
    "registration_deadline",
    "submission_deadline",
    "bid_opening_time",
    "deadlines",
}


def _is_config_secret_key(key: Any) -> bool:
    key_text = str(key).lower()
    return key_text not in CONFIG_PUBLIC_SECRET_NAME_EXCEPTIONS and any(
        marker in key_text for marker in CONFIG_SECRET_MARKERS
    )


def _is_masked_or_empty_secret(value: Any) -> bool:
    return value in ("", None, "***")


def _mask_config_secrets(config: Any) -> Any:
    if isinstance(config, dict):
        for key, value in config.items():
            if _is_config_secret_key(key):
                if value:
                    config[key] = "***"
            else:
                _mask_config_secrets(value)
    elif isinstance(config, list):
        for item in config:
            _mask_config_secrets(item)
    return config


def _preserve_config_secrets(new_value: Any, old_value: Any) -> Any:
    if isinstance(new_value, dict) and isinstance(old_value, dict):
        for key, value in new_value.items():
            if _is_config_secret_key(key):
                if _is_masked_or_empty_secret(value):
                    new_value[key] = old_value.get(key, "")
            else:
                new_value[key] = _preserve_config_secrets(value, old_value.get(key))
    elif isinstance(new_value, list) and isinstance(old_value, list):
        for index, item in enumerate(new_value):
            old_item = old_value[index] if index < len(old_value) else None
            new_value[index] = _preserve_config_secrets(item, old_item)
    return new_value


def _normalize_search_text(value: Any) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_search_text(item) for item in value if item not in (None, "", []))
    if isinstance(value, dict):
        return " ".join(_normalize_search_text(item) for item in value.values() if item not in (None, "", []))
    return str(value)


def _matches_result_query(bid: BidInfo, query: str) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    resolved = resolve_result_data(bid)
    haystack = " ".join(
        _normalize_search_text(value)
        for value in [
            bid.title,
            bid.source,
            bid.publish_date,
            bid.purchaser,
            bid.content,
            bid.detail_text,
            resolved,
            bid.ai_extracted_data,
            bid.manual_overrides,
            bid.non_follow_reasons,
            bid.review_notes,
        ]
    ).lower()
    return needle in haystack


def _validate_manual_override_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="fields required")
    unknown = sorted(set(payload) - RESULT_OVERRIDE_FIELDS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"unsupported manual override fields: {', '.join(unknown)}")
    return payload


@app.get("/api/results")
async def get_results(
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    fit_status: Optional[str] = None,
    follow_decision: Optional[str] = None,
    urgency: Optional[str] = None,
    project_stage: Optional[str] = None,
    ai_extract_status: Optional[str] = None,
    source: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取招标结果"""
    search_query = q
    filters = {}
    for key, value in {
        "fit_status": fit_status,
        "follow_decision": follow_decision,
        "urgency": urgency,
        "project_stage": project_stage,
        "ai_extract_status": ai_extract_status,
        "source": source,
        "region": region,
        "category": category,
    }.items():
        if value not in (None, ""):
            filters[key] = value

    if search_query not in (None, ""):
        try:
            _bids, candidate_total = app_state.storage.query_results(filters, 0, 0)
            candidates, _total = app_state.storage.query_results(filters, candidate_total, 0) if candidate_total else ([], 0)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        matched = [bid for bid in candidates if _matches_result_query(bid, search_query)]
        total = len(matched)
        bids = matched[offset: offset + limit]
    else:
        try:
            bids, total = app_state.storage.query_results(filters, limit, offset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [result_summary(bid) for bid in bids],
    }


@app.get("/api/results/{result_id}")
async def get_result_detail(result_id: int, user: Dict[str, Any] = Depends(get_current_user)):
    bid = app_state.storage.get_by_id(result_id)
    if not bid:
        raise _result_not_found(result_id)
    return result_detail_payload(bid)


@app.patch("/api/results/{result_id}/review")
async def update_result_review(result_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    bid = app_state.storage.get_by_id(result_id)
    if not bid:
        raise _result_not_found(result_id)
    try:
        update = validate_review_update(payload, _review_reason_tags())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    app_state.storage.update_review([result_id], update)
    return {"success": True}


@app.patch("/api/results/bulk-review")
async def bulk_update_result_review(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    result_ids = payload.get("ids") or []
    update_payload = payload.get("update") or {}
    if not isinstance(result_ids, list) or not result_ids:
        raise HTTPException(status_code=400, detail="ids required")
    try:
        update = validate_review_update(update_payload, _review_reason_tags())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    missing_ids = [result_id for result_id in result_ids if not app_state.storage.get_by_id(result_id)]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"results not found: {', '.join(str(result_id) for result_id in missing_ids)}")
    app_state.storage.update_review(result_ids, update)
    return {"success": True, "updated": len(result_ids)}


@app.patch("/api/results/{result_id}/fields")
async def update_result_fields(result_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    bid = app_state.storage.get_by_id(result_id)
    if not bid:
        raise _result_not_found(result_id)
    updates = _validate_manual_override_payload(payload)
    merged = dict(bid.manual_overrides or {})
    merged.update(updates)
    app_state.storage.update_manual_overrides(result_id, merged)
    return {"success": True}


@app.get("/api/result-settings")
async def get_result_settings(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "fit_statuses": sorted(FIT_STATUSES),
        "follow_decisions": sorted(FOLLOW_DECISIONS),
        "urgencies": sorted(URGENCIES),
        "project_stages": sorted(PROJECT_STAGES),
        "non_follow_reason_tags": _review_reason_tags(),
    }


@app.post("/api/result-settings/reasons")
async def update_non_follow_reasons(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    tags = payload.get("tags")
    if not isinstance(tags, list) or not tags:
        raise HTTPException(status_code=400, detail="tags required")
    normalized_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    if not normalized_tags:
        raise HTTPException(status_code=400, detail="tags required")
    app_state.config["non_follow_reason_tags"] = normalized_tags
    save_config(app_state.config)
    return {"success": True}


# ── 关键词库 API ──────────────────────────────────────────────────────────────

@app.get("/api/keyword-library")
async def get_keyword_library(user: Dict[str, Any] = Depends(get_current_user)):
    """获取全部关键词库条目"""
    return keyword_library_storage.list_all()


@app.post("/api/keyword-library")
async def create_keyword_entry(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(require_admin)):
    """新增关键词库条目"""
    if not (payload.get("keyword") or "").strip():
        raise HTTPException(status_code=400, detail="keyword 不能为空")
    return keyword_library_storage.create(payload)


@app.put("/api/keyword-library/{entry_id}")
async def update_keyword_entry(entry_id: int, payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(require_admin)):
    """更新关键词库条目"""
    result = keyword_library_storage.update(entry_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    return result


@app.delete("/api/keyword-library/{entry_id}")
async def delete_keyword_entry(entry_id: int, user: Dict[str, Any] = Depends(require_admin)):
    """删除关键词库条目"""
    if not keyword_library_storage.delete(entry_id):
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"success": True}


@app.post("/api/keyword-library/bulk-toggle")
async def bulk_toggle_keywords(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(require_admin)):
    """批量启停关键词库条目"""
    ids = payload.get("ids", [])
    enabled = bool(payload.get("enabled", True))
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    count = keyword_library_storage.bulk_toggle([int(i) for i in ids], enabled)
    return {"success": True, "updated": count}


@app.get("/api/keyword-library/export.csv")
async def export_keyword_library(user: Dict[str, Any] = Depends(get_current_user)):
    """导出关键词库为 CSV"""
    from fastapi.responses import Response as FastAPIResponse
    csv_text = keyword_library_storage.export_csv()
    return FastAPIResponse(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=keyword_library.csv"},
    )


@app.post("/api/keyword-library/import")
async def import_keyword_library(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(require_admin)):
    """导入关键词库（JSON body: {csv: '...'}）"""
    csv_text = payload.get("csv", "")
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="csv 内容为空")
    result = keyword_library_storage.import_csv(csv_text)
    return {"success": True, **result}


@app.get("/api/logs")
async def get_logs(limit: int = 100, user: Dict[str, Any] = Depends(get_current_user)):
    """获取最近的日志"""
    limit = max(1, min(int(limit), LOG_API_LIMIT))
    return {
        "logs": app_state.logs[-limit:]
    }

@app.delete("/api/logs")
async def clear_logs(user: Dict[str, Any] = Depends(get_current_user)):
    """清空日志"""
    app_state.logs = []
    return {"success": True, "message": "日志已清空"}

@app.delete("/api/history")
async def clear_history(user: Dict[str, Any] = Depends(require_admin)):
    """清空历史数据"""
    app_state.storage.clear_all()
    app_state.add_log("🗑️ 历史数据已清空")
    return {"success": True, "message": "历史数据已清空"}

@app.get("/api/contacts")
async def get_contacts(user: Dict[str, Any] = Depends(get_current_user)):
    """获取联系人列表"""
    contacts = copy.deepcopy(app_state.config.get('contacts', []))
    return _mask_config_secrets(contacts)

@app.post("/api/contacts")
async def update_contacts(contacts: List[Dict[str, Any]], user: Dict[str, Any] = Depends(get_current_user)):
    """更新联系人列表"""
    # 保留原有联系人的敏感字段
    old_contacts = app_state.config.get('contacts', [])
    old_contacts_by_name = {c.get('name'): c for c in old_contacts}
    
    for contact in contacts:
        name = contact.get('name', '')
        old_contact = old_contacts_by_name.get(name, {})
        
        # 保留email_password如果前端没有传入新值
        if not contact.get('email_password') and old_contact.get('email_password'):
            contact['email_password'] = old_contact['email_password']
        
        # 保留wechat_token如果前端传入空值但原来有值
        # (注意：wechat_token用户可能想清空，这里不强制保留)
    
    app_state.config['contacts'] = contacts
    save_config(app_state.config)
    app_state.add_log(f"📋 联系人配置已更新，共 {len(contacts)} 人")
    return {"success": True, "message": "联系人已更新"}

@app.post("/api/config/full")
async def update_full_config(config: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """更新完整配置（包括通知配置）"""
    # 保留前端回传的掩码/空值对应的既有敏感字段。
    config = _preserve_config_secrets(config, app_state.config)
    config = normalize_config(config)
    app_state.config.update(config)
    save_config(app_state.config)
    return {"success": True, "message": "配置已更新"}

# 测试通知请求模型
class TestNotifyRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    token: Optional[str] = None

@app.post("/api/test/voice")
async def test_voice(req: TestNotifyRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """测试语音呼叫"""
    if not req.phone:
        raise HTTPException(status_code=400, detail="请输入测试手机号")
    
    voice_config = app_state.config.get('voice_config', {})
    if not voice_config.get('access_key_id') or not voice_config.get('tts_code'):
        raise HTTPException(status_code=400, detail="请先配置语音API参数")
    
    try:
        from notifier.voice import VoiceNotifier
        notifier = VoiceNotifier(voice_config)
        success = notifier.call(req.phone, count=1, source="测试")
        if success:
            app_state.add_log(f"✅ 测试语音呼叫成功: {req.phone}")
            return {"success": True, "message": f"语音呼叫已发送到 {req.phone}"}
        else:
            app_state.add_log(f"❌ 测试语音呼叫失败: {req.phone}")
            return {"success": False, "message": "语音呼叫失败，请检查配置"}
    except Exception as e:
        app_state.add_log(f"❌ 测试语音呼叫异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/sms")
async def test_sms(req: TestNotifyRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """测试短信发送"""
    if not req.phone:
        raise HTTPException(status_code=400, detail="请输入测试手机号")
    
    sms_config = app_state.config.get('sms_config', {})
    if not sms_config.get('access_key_id') or not sms_config.get('template_code'):
        raise HTTPException(status_code=400, detail="请先配置短信API参数")
    
    try:
        from notifier.sms import SMSNotifier
        notifier = SMSNotifier(sms_config)
        success = notifier.send_test(req.phone)
        if success:
            app_state.add_log(f"✅ 测试短信发送成功: {req.phone}")
            return {"success": True, "message": f"测试短信已发送到 {req.phone}"}
        else:
            app_state.add_log(f"❌ 测试短信发送失败: {req.phone}")
            return {"success": False, "message": "短信发送失败，请检查配置"}
    except Exception as e:
        app_state.add_log(f"❌ 测试短信发送异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/email")
async def test_email(req: TestNotifyRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """测试邮件发送"""
    if not req.email:
        raise HTTPException(status_code=400, detail="请输入测试邮箱地址")
    
    # 从联系人或配置中获取邮箱配置
    contacts = app_state.config.get('contacts', [])
    contact_config = None
    for contact in contacts:
        if contact.get('email') == req.email and contact.get('email_password'):
            contact_config = contact
            break
    
    if not contact_config:
        raise HTTPException(status_code=400, detail="未找到该邮箱的配置，请先在联系人中配置邮箱和授权码")
    
    # 根据邮箱类型配置SMTP服务器
    email_type = contact_config.get('email_type', 'QQ邮箱')
    smtp_configs = {
        'QQ邮箱': {'smtp_server': 'smtp.qq.com', 'smtp_port': 465, 'use_ssl': True},
        '163邮箱': {'smtp_server': 'smtp.163.com', 'smtp_port': 465, 'use_ssl': True},
        'Gmail': {'smtp_server': 'smtp.gmail.com', 'smtp_port': 587, 'use_ssl': False},
        'Outlook': {'smtp_server': 'smtp.office365.com', 'smtp_port': 587, 'use_ssl': False},
        '企业邮箱': {'smtp_server': 'smtp.exmail.qq.com', 'smtp_port': 465, 'use_ssl': True},
    }
    smtp_config = smtp_configs.get(email_type, smtp_configs['QQ邮箱'])
    
    email_config = {
        'smtp_server': smtp_config['smtp_server'],
        'smtp_port': smtp_config['smtp_port'],
        'use_ssl': smtp_config['use_ssl'],
        'sender': contact_config['email'],
        'password': contact_config['email_password'],
        'receiver': contact_config['email'],  # 发送给自己作为测试
    }
    
    try:
        from notifier.email import EmailNotifier
        notifier = EmailNotifier(email_config)
        success = notifier.send_test()
        if success:
            app_state.add_log(f"✅ 测试邮件发送成功: {req.email}")
            return {"success": True, "message": f"测试邮件已发送到 {req.email}"}
        else:
            app_state.add_log(f"❌ 测试邮件发送失败: {req.email}")
            return {"success": False, "message": "邮件发送失败，请检查授权码是否正确"}
    except Exception as e:
        app_state.add_log(f"❌ 测试邮件发送异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/wechat")
async def test_wechat(req: TestNotifyRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """测试微信推送"""
    if not req.token:
        raise HTTPException(status_code=400, detail="请输入PushPlus Token")
    
    try:
        from notifier.wechat import WeChatNotifier
        notifier = WeChatNotifier({'provider': 'pushplus', 'token': req.token})
        success = notifier.send_test()
        if success:
            app_state.add_log(f"✅ 测试微信推送成功")
            return {"success": True, "message": "微信推送已发送，请检查微信"}
        else:
            app_state.add_log(f"❌ 测试微信推送失败")
            return {"success": False, "message": "微信推送失败，请检查Token是否正确"}
    except Exception as e:
        app_state.add_log(f"❌ 测试微信推送异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/ai")
async def test_ai(user: Dict[str, Any] = Depends(get_current_user)):
    """测试AI配置"""
    ai_config = app_state.config.get('ai_config', {})
    if not ai_config.get('api_key'):
        raise HTTPException(status_code=400, detail="请先配置AI API Key")
    
    try:
        try:
            from results.ai_extractor import AIExtractor
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=f"AI extractor unavailable: {exc}")

        extractor = AIExtractor(
            {
                "enable": True,
                "base_url": ai_config.get("base_url", "https://api.sakrylle.com/v1"),
                "api_key": ai_config["api_key"],
                "model": ai_config.get("model", "grok-4.20-fast"),
                "endpoint_type": ai_config.get("endpoint_type") or (
                    "chat_completions"
                    if (ai_config.get("base_url") or "").rstrip("/").lower().endswith("/chat/completions")
                    else "responses"
                ),
            }
        )
        test_result = extractor.test_connection("Reply with exactly: ok")
        app_state.add_log("✅ AI测试成功")
        return {"success": True, "message": str(test_result)}
    except HTTPException:
        raise
    except Exception as e:
        app_state.add_log(f"❌ AI测试异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 主入口
if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("BIDMONITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("BIDMONITOR_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
