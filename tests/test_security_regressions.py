"""认证、权限、慢 SQL 与实时 WebSocket 的纯单元安全回归。"""
import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

os.environ.setdefault("ORACLE_SERVICE", "XEPDB1")
os.environ.setdefault("FABTWIN_TOKEN_SECRET", "security-regression-test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core import deps as core_deps
from core.deps import get_current_user
from core.services import perf
from core.services.realtime import connect_authenticated
from core.services.security import (
    WS_SUBPROTOCOL,
    decode_ws_token,
    encode_ws_token,
    hash_password,
    issue_token,
    verify_password,
)
from database import get_db
from models import User
from modules.system_admin.routes import auth, users


PROXY_IP = "10.20.30.40"
SSO_KEY = "test-sso-shared-key"


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, result=None):
        self.result = result
        self.added = []
        self.commits = 0
        self.queries = 0

    def query(self, model):
        self.queries += 1
        return FakeQuery(self.result)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def refresh(self, value):
        return None

    def close(self):
        return None


def make_user(user_id="u1", username="alice", role="admin", password_hash=None):
    return User(
        id=user_id,
        username=username,
        display_name=username,
        email="",
        department="",
        role=role,
        password_hash=password_hash,
        windows_sid="",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        last_login_at="",
    )


def make_client(router, db, prefix="", source=PROXY_IP, current_user=None):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_db] = lambda: db
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app, client=(source, 12345))


def configure_sso(monkeypatch, proxies=PROXY_IP, key=SSO_KEY):
    monkeypatch.setenv("FABTWIN_SSO_TRUSTED_PROXIES", proxies)
    monkeypatch.setenv("FABTWIN_SSO_SHARED_KEY", key)


def sso_headers(username=r"DOMAIN\alice", key=SSO_KEY):
    return {"X-Forwarded-User": username, "X-FabTwin-SSO-Key": key}


def test_login_windows_uses_verified_header_and_ignores_body(monkeypatch):
    configure_sso(monkeypatch)
    db = FakeDB(make_user(username="alice"))
    client = make_client(auth.router, db)

    response = client.post(
        "/api/auth/login-windows",
        json={"username": "attacker"},
        headers=sso_headers(),
    )
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"
    assert response.json()["user"]["username"] != "attacker"

    no_body = client.post("/api/auth/login-windows", headers=sso_headers())
    assert no_body.status_code == 200


@pytest.mark.parametrize("source", ["127.0.0.1", "::1", "192.168.1.8", "203.0.113.8"])
def test_login_windows_rejects_unlisted_sources_even_with_legacy_flag(monkeypatch, source):
    configure_sso(monkeypatch)
    monkeypatch.setenv("FABTWIN_TRUST_SSO_HEADER", "1")
    client = make_client(auth.router, FakeDB(make_user()), source=source)

    response = client.post("/api/auth/login-windows", headers=sso_headers())
    assert response.status_code == 403


def test_login_windows_rejects_bad_or_missing_key(monkeypatch):
    configure_sso(monkeypatch)
    client = make_client(auth.router, FakeDB(make_user()))

    wrong = client.post("/api/auth/login-windows", headers=sso_headers(key="wrong"))
    missing = client.post(
        "/api/auth/login-windows", headers={"X-Forwarded-User": r"DOMAIN\alice"}
    )
    assert wrong.status_code == 401
    assert missing.status_code == 401


def test_login_windows_rejects_unconfigured_sso(monkeypatch):
    monkeypatch.delenv("FABTWIN_SSO_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("FABTWIN_SSO_SHARED_KEY", raising=False)
    monkeypatch.setenv("FABTWIN_TRUST_SSO_HEADER", "1")
    client = make_client(auth.router, FakeDB(make_user()))

    response = client.post("/api/auth/login-windows", headers=sso_headers())
    assert response.status_code == 403


def test_login_password_fallback_contract_and_spoofed_header(monkeypatch):
    monkeypatch.delenv("FABTWIN_SSO_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("FABTWIN_SSO_SHARED_KEY", raising=False)
    client = make_client(auth.router, FakeDB(), source="203.0.113.8")

    fallback = client.post("/api/auth/login")
    spoofed = client.post(
        "/api/auth/login", headers={"X-Forwarded-User": r"DOMAIN\admin"}
    )
    assert fallback.status_code == 200
    assert fallback.json()["need_password_login"] is True
    assert spoofed.status_code == 403


@pytest.mark.parametrize("empty_hash", [None, ""])
def test_local_login_never_falls_back_to_username_123(empty_hash):
    user = make_user(username="legacy", password_hash=empty_hash)
    db = FakeDB(user)
    client = make_client(auth.router, db)

    response = client.post(
        "/api/auth/login-password",
        json={"username": "legacy", "password": "legacy123"},
    )
    assert response.status_code == 401
    assert user.password_hash == empty_hash
    assert db.commits == 0


def test_create_user_requires_password_and_hashes_explicit_password():
    db = FakeDB()
    client = make_client(
        users.router, db, current_user=make_user(role="admin")
    )
    payload = {"username": "local", "display_name": "Local User"}

    missing = client.post("/api/users", json=payload)
    empty = client.post("/api/users", json={**payload, "password": ""})
    mismatch = client.post(
        "/api/users",
        json={**payload, "password": "secret", "confirm_password": "different"},
    )
    assert missing.status_code == 422
    assert empty.status_code == 422
    assert mismatch.status_code == 422
    assert db.added == []

    created = client.post(
        "/api/users",
        json={**payload, "password": "secret", "confirm_password": "secret"},
    )
    assert created.status_code == 200
    password_hash = db.added[0].password_hash
    assert password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("secret", password_hash)
    assert not verify_password("local123", password_hash)


def test_create_sso_only_user_keeps_empty_hash():
    db = FakeDB()
    client = make_client(
        users.router, db, current_user=make_user(role="admin")
    )

    response = client.post(
        "/api/users",
        json={"username": "sso-user", "display_name": "SSO User", "sso_only": True},
    )
    assert response.status_code == 200
    assert db.added[0].password_hash is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"new_password": ""},
        {"new_password": "new-secret", "confirm_password": "different"},
        {"new_password": "new-secret", "password_confirm": "different"},
    ],
)
def test_reset_password_rejects_empty_missing_or_mismatch(payload):
    user = make_user(password_hash=hash_password("old-secret"))
    db = FakeDB(user)
    client = make_client(
        users.router, db, current_user=make_user(role="admin")
    )

    response = client.put("/api/users/u1/password", json=payload)
    assert response.status_code == 422
    assert verify_password("old-secret", user.password_hash)
    assert db.commits == 0


def test_reset_password_requires_and_stores_explicit_new_password():
    user = make_user(password_hash=hash_password("old-secret"))
    db = FakeDB(user)
    client = make_client(
        users.router, db, current_user=make_user(role="admin")
    )

    response = client.put(
        "/api/users/u1/password",
        json={"new_password": "new-secret", "confirm_password": "new-secret"},
    )
    assert response.status_code == 200
    assert verify_password("new-secret", user.password_hash)
    assert not verify_password("old-secret", user.password_hash)
    assert not verify_password("alice123", user.password_hash)
    assert db.commits == 1


def test_require_admin_rejects_non_admin():
    assert core_deps.require_admin(make_user(role="admin")).role == "admin"
    with pytest.raises(HTTPException) as exc:
        core_deps.require_admin(make_user(role="user"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/perf/slow"),
        ("post", "/api/perf/clear"),
        ("post", "/api/metrics/perf/reset"),
    ],
)
def test_perf_mutation_and_slow_routes_require_admin(method, path):
    client = make_client(
        perf.router, FakeDB(), current_user=make_user(role="engineer")
    )
    response = getattr(client, method)(path)
    assert response.status_code == 403


def test_slow_sql_contains_only_operation_duration_and_sha256(monkeypatch, caplog):
    statement = "SELECT 'raw-secret' AS value, ? AS bound"
    bound_value = "bound-secret"
    monkeypatch.setattr(perf, "SLOW_SQL_MS", 0)
    caplog.set_level(logging.WARNING, logger="fabtwin.perf")
    perf.reset()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    perf.install_sql_timing(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql(statement, (bound_value,)).fetchall()

    snapshot = perf.snapshot()
    assert len(snapshot["slow_sql"]) == 1
    entry = snapshot["slow_sql"][0]
    assert set(entry) == {"operation", "ms", "statement_sha256"}
    assert entry["operation"] == "SELECT"
    assert entry["statement_sha256"] == hashlib.sha256(statement.encode()).hexdigest()
    exposed = repr(snapshot) + caplog.text
    assert statement not in exposed
    assert "raw-secret" not in exposed
    assert bound_value not in exposed

    client = make_client(
        perf.router, FakeDB(), current_user=make_user(role="admin")
    )
    response = client.get("/api/perf/slow")
    assert response.status_code == 200
    assert response.json()["slow_sql"] == [entry]
    assert "raw-secret" not in response.text
    assert bound_value not in response.text
    assert client.post("/api/perf/clear").status_code == 200
    assert perf.snapshot()["slow_sql"] == []
    engine.dispose()


def test_ws_token_subprotocol_roundtrip_and_invalid_encoding():
    token = issue_token("user-1")
    wrapped = encode_ws_token(token)
    assert wrapped.startswith("fabtwin-token.")
    assert "=" not in wrapped
    assert decode_ws_token([WS_SUBPROTOCOL, wrapped]) == token
    assert decode_ws_token([wrapped]) is None
    assert decode_ws_token([WS_SUBPROTOCOL, wrapped, wrapped]) is None
    assert decode_ws_token([WS_SUBPROTOCOL, "fabtwin-token.!!!"]) is None
    assert decode_ws_token([WS_SUBPROTOCOL, wrapped + "="]) is None


class FakeWebSocket:
    def __init__(self, protocols):
        self.scope = {"subprotocols": protocols}
        self.accepted = []
        self.close_code = None
        self.events = []

    async def accept(self, subprotocol=None):
        self.accepted.append(subprotocol)
        self.events.append(("accept", subprotocol))

    async def close(self, code):
        self.close_code = code
        self.events.append(("close", code))


class RecordingManager:
    def __init__(self):
        self.connected = []

    async def connect(self, websocket, subprotocol=None):
        self.connected.append(websocket)
        await websocket.accept(subprotocol=subprotocol)


@pytest.mark.parametrize("protocols", [[], [WS_SUBPROTOCOL], [WS_SUBPROTOCOL, "fabtwin-token.bad"]])
def test_ws_invalid_or_unknown_token_closes_1008_without_registration(protocols):
    websocket = FakeWebSocket(protocols)
    manager = RecordingManager()
    db = FakeDB(make_user())

    connected = asyncio.run(connect_authenticated(websocket, db, manager))
    assert connected is False
    assert websocket.close_code == 1008
    # 必须先 accept（只携带固定应用子协议）再 close 1008：
    # 握手前 close 会被转为 HTTP 403，浏览器只能拿到 1006，
    # 客户端基于 1008 的认证清理与停连逻辑永远不会触发
    assert websocket.accepted == [WS_SUBPROTOCOL]
    assert websocket.events.index(("accept", WS_SUBPROTOCOL)) < websocket.events.index(("close", 1008))
    assert manager.connected == []


def test_ws_unknown_user_closes_1008_without_registration():
    token = issue_token("deleted-user")
    websocket = FakeWebSocket([WS_SUBPROTOCOL, encode_ws_token(token)])
    manager = RecordingManager()

    connected = asyncio.run(connect_authenticated(websocket, FakeDB(None), manager))
    assert connected is False
    assert websocket.close_code == 1008
    assert manager.connected == []


def test_ws_existing_user_connects_with_only_fixed_subprotocol():
    token = issue_token("u1")
    wrapped = encode_ws_token(token)
    websocket = FakeWebSocket([WS_SUBPROTOCOL, wrapped])
    manager = RecordingManager()

    connected = asyncio.run(connect_authenticated(websocket, FakeDB(make_user()), manager))
    assert connected is True
    assert manager.connected == [websocket]
    assert websocket.accepted == [WS_SUBPROTOCOL]
    assert wrapped not in websocket.accepted
    assert websocket.close_code is None
