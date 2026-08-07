import json
import mimetypes
import os
import queue
import threading
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import fetch_history_events_for_tool, fetch_latest_event_for_tool, get_oracle_pool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
TEMPLATES_DIR = os.path.join(BASE_DIR, "docs", "templates")
REGISTRY_DIR = os.path.join(BASE_DIR, "registry")

HTTP_PORT = int(os.environ.get("DT_HTTP_PORT", "7501"))
DASHBOARD_FILE = os.environ.get("TWIN_DASHBOARD_FILE", "index.html")
DASHBOARD_URL = f"http://127.0.0.1:{HTTP_PORT}/{DASHBOARD_FILE}"
STATIC_ROOTS = [MODELS_DIR]

clients = []
clients_lock = threading.Lock()
tool_subscribers = defaultdict(set)
tool_subscribers_lock = threading.Lock()
session_bindings_lock = threading.Lock()
session_bindings = {}


def _load_json_file(file_path, default_value):
    if not os.path.isfile(file_path):
        return default_value
    try:
        with open(file_path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return default_value


def _save_json_file(file_path, payload):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def load_model_registry():
    return _load_json_file(
        os.path.join(
            REGISTRY_DIR,
            "model_registry.json"),
        [])


def load_machine_registry():
    return _load_json_file(
        os.path.join(
            REGISTRY_DIR,
            "machine_registry.json"),
        [])


def load_session_bindings():
    return _load_json_file(
        os.path.join(
            REGISTRY_DIR,
            "session_binding.json"),
        [])


def _session_binding_file_path():
    return os.path.join(REGISTRY_DIR, "session_binding.json")


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _normalize_query_value(values, default=""):
    if not values:
        return default
    value = values[0]
    return value.strip() if isinstance(value, str) else default


def resolve_model_key(tool_id):
    for item in load_machine_registry():
        if str(item.get("tool_id", "")).strip() == str(tool_id).strip():
            return item.get("model_key")
    return None


def _refresh_session_bindings_cache():
    with session_bindings_lock:
        records = load_session_bindings()
        session_bindings.clear()
        for record in records:
            session_id = str(record.get("session_id", "")).strip()
            if session_id:
                session_bindings[session_id] = record


def _persist_session_bindings_locked():
    records = sorted(
        session_bindings.values(),
        key=lambda item: str(
            item.get(
                "bind_ts_utc",
                "")))
    _save_json_file(_session_binding_file_path(), records)


def get_session_binding(session_id):
    if not session_id:
        return None
    with session_bindings_lock:
        return session_bindings.get(session_id)


def upsert_session_binding(
        session_id,
        tool_id,
        client_id="",
        bind_mode="viewer"):
    session_id = str(session_id or "").strip()
    tool_id = str(tool_id or "").strip()
    if not session_id or not tool_id:
        return None
    model_key = resolve_model_key(tool_id)
    record = {
        "session_id": session_id,
        "tool_id": tool_id,
        "model_key": model_key,
        "client_id": str(client_id or "").strip(),
        "bind_mode": str(bind_mode or "viewer").strip() or "viewer",
        "bind_ts_utc": _utc_now_iso(),
        "unbind_ts_utc": None,
        "status": "active",
    }
    with session_bindings_lock:
        session_bindings[session_id] = record
        _persist_session_bindings_locked()
    return record


def close_session_binding(session_id):
    session_id = str(session_id or "").strip()
    if not session_id:
        return None
    with session_bindings_lock:
        record = session_bindings.get(session_id)
        if not record:
            return None
        record = {
            **record,
            "unbind_ts_utc": _utc_now_iso(),
            "status": "closed"}
        session_bindings[session_id] = record
        _persist_session_bindings_locked()
    return record


def register_tool_subscriber(tool_id, client_queue):
    tool_id = str(tool_id or "").strip()
    if not tool_id:
        return False
    with tool_subscribers_lock:
        tool_subscribers[tool_id].add(client_queue)
    return True


def unregister_tool_subscriber(tool_id, client_queue):
    tool_id = str(tool_id or "").strip()
    if not tool_id:
        return
    with tool_subscribers_lock:
        subscribers = tool_subscribers.get(tool_id)
        if not subscribers:
            return
        subscribers.discard(client_queue)
        if not subscribers:
            tool_subscribers.pop(tool_id, None)


def send_json_payload(handler, status_code, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        handler.send_response(status_code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
        return False
    return True


def broadcast_to_tool(tool_id, event_data):
    resolved_tool_id = str(tool_id or event_data.get("tool_id") or "").strip()
    if not resolved_tool_id:
        return
    msg = f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
    with tool_subscribers_lock:
        subscribers = list(tool_subscribers.get(resolved_tool_id, set()))
    for client_q in subscribers:
        client_q.put(msg)


def broadcast_to_frontend(event_data):
    broadcast_to_tool(event_data.get("tool_id"), event_data)


class TwinRequestHandler(BaseHTTPRequestHandler):
    def resolve_static_file(self, requested_path):
        normalized_path = os.path.normpath(requested_path).lstrip("\\/")
        if not normalized_path or normalized_path.startswith(".."):
            return None
        if normalized_path.startswith("models/"):
            normalized_path = normalized_path[len("models/"):]
        for root_dir in STATIC_ROOTS:
            root_abs = os.path.abspath(root_dir)
            candidate_path = os.path.abspath(
                os.path.join(root_abs, normalized_path))
            if os.path.commonpath([candidate_path, root_abs]) != root_abs:
                continue
            if os.path.isfile(candidate_path):
                return candidate_path
        return None

    def send_file(self, file_path):
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            return
        content_type, _ = mimetypes.guess_type(file_path)
        self.send_response(200)
        self.send_header(
            "Content-Type",
            content_type or "application/octet-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open(file_path, "rb") as stream:
                self.wfile.write(stream.read())
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            return

    def do_GET(self):
        parsed_url = urlparse(self.path)
        request_path = parsed_url.path or "/"
        params = parse_qs(parsed_url.query)

        if request_path == "/":
            self.send_response(302)
            self.send_header("Location", f"/{DASHBOARD_FILE}")
            self.end_headers()
            return

        if request_path == "/bind":
            session_id = _normalize_query_value(params.get("session_id"))
            tool_id = _normalize_query_value(params.get("tool_id"))
            client_id = _normalize_query_value(params.get("client_id"))
            bind_mode = _normalize_query_value(
                params.get("bind_mode"), "viewer")
            if not session_id or not tool_id:
                send_json_payload(
                    self, 400, {
                        "error": "session_id and tool_id are required"})
                return
            record = upsert_session_binding(
                session_id, tool_id, client_id=client_id, bind_mode=bind_mode)
            if record is None:
                send_json_payload(self, 400, {
                    "error": "unable to bind session",
                    "session_id": session_id,
                    "tool_id": tool_id,
                })
                return
            send_json_payload(self, 200, {"ok": True, "binding": record})
            return

        if request_path == "/unbind":
            session_id = _normalize_query_value(params.get("session_id"))
            if not session_id:
                send_json_payload(
                    self, 400, {
                        "error": "session_id is required"})
                return
            record = close_session_binding(session_id)
            if record is None:
                send_json_payload(
                    self, 404, {
                        "error": "binding not found", "session_id": session_id})
                return
            send_json_payload(self, 200, {"ok": True, "binding": record})
            return

        if request_path == "/events":
            session_id = _normalize_query_value(params.get("session_id"))
            tool_id = _normalize_query_value(params.get("tool_id"))
            if not session_id or not tool_id:
                send_json_payload(
                    self, 400, {
                        "error": "session_id and tool_id are required"})
                return
            binding = get_session_binding(session_id)
            if not binding or binding.get("status") != "active" or str(
                    binding.get("tool_id", "")).strip() != tool_id:
                send_json_payload(self, 409, {
                    "error": "session not bound to requested tool",
                    "session_id": session_id,
                    "tool_id": tool_id,
                    "binding": binding,
                })
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            client_q = queue.Queue()
            register_tool_subscriber(tool_id, client_q)
            try:
                hello_msg = (
                    f"data: {json.dumps({'event_type': 'CONNECTED', 'msg': 'RV 网桥已链接并在此守候！', 'session_id': session_id, 'tool_id': tool_id, 'model_key': binding.get('model_key')})}\n\n"
                )
                try:
                    self.wfile.write(hello_msg.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
                    return
                while True:
                    msg = client_q.get()
                    try:
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
                        return
            except BaseException:
                pass
            finally:
                unregister_tool_subscriber(tool_id, client_q)
            return

        if request_path == "/latest-event":
            tool_id = _normalize_query_value(params.get("tool_id"))
            if not tool_id:
                send_json_payload(self, 400, {"error": "tool_id is required"})
                return
            latest_event = fetch_latest_event_for_tool(tool_id)
            if latest_event is None:
                status_code = 503 if get_oracle_pool() is None else 404
                error_message = "database unavailable" if status_code == 503 else "event not found"
                send_json_payload(
                    self, status_code, {
                        "error": error_message, "tool_id": tool_id})
                return
            send_json_payload(self, 200, latest_event)
            return

        if request_path == "/history-events":
            tool_id = _normalize_query_value(params.get("tool_id"))
            limit_raw = _normalize_query_value(params.get("limit"), "2000")
            if not tool_id:
                send_json_payload(self, 400, {"error": "tool_id is required"})
                return
            try:
                limit = int(limit_raw)
            except ValueError:
                limit = 2000
            limit = max(1, min(limit, 5000))
            events = fetch_history_events_for_tool(tool_id, limit=limit)
            send_json_payload(self, 200, {
                "tool_id": tool_id,
                "source": "realtime_lot_snapshot",
                "count": len(events),
                "events": events,
            })
            return

        requested_name = request_path.lstrip("/")
        file_path = self.resolve_static_file(requested_name)
        if file_path is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_file(file_path)


def run_http_server():
    _refresh_session_bindings_cache()
    server_address = ("", HTTP_PORT)
    httpd = ThreadingHTTPServer(server_address, TwinRequestHandler)
    # 已禁用自动打开浏览器（Linux 部署）
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n停止 Web 服务...")
        httpd.server_close()
