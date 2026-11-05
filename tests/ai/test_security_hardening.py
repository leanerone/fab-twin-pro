# -*- coding: utf-8 -*-
"""T6 回归：安全加固四项（2026-11-06）

  1. 读接口鉴权补齐：/api/machines /api/models /api/floors 匿名 401
  2. /ws/realtime 无 token 拒绝握手（403），带有效 token 101 升级
  3. debug 注入端点 admin-only：普通用户 403
  4. 登录防爆破：同 用户名+IP 连续失败 5 次 → 429
  5. SSO 信任头：非回环内网 IP 不再默认信任

运行（前提：后端已带改动启动）：python tests/ai/test_security_hardening.py --backend http://127.0.0.1:8003
"""
import os
import sys
import json
import base64
import socket
import time
import urllib.request
import urllib.error
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


def http(method, path, data=None, token=None, timeout=30):
    req = urllib.request.Request(BACKEND + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def ws_handshake_status(path):
    """裸 socket 发 WS 升级请求，返回 HTTP 状态码"""
    host = BACKEND.split("//")[1].split(":")[0]
    port = int(BACKEND.split(":")[-1])
    s = socket.create_connection((host, port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    data = s.recv(200).decode(errors="ignore")
    s.close()
    try:
        return int(data.split(" ")[1])
    except Exception:
        return 0


def main():
    global BACKEND
    BACKEND = "http://127.0.0.1:8003"
    for i, a in enumerate(sys.argv):
        if a == "--backend" and i + 1 < len(sys.argv):
            BACKEND = sys.argv[i + 1]

    st, body = http("POST", "/api/auth/login-password", {"username": "admin", "password": "admin123"})
    token = body.get("token", "") if isinstance(body, dict) else ""
    check("admin 正常登录", st == 200 and token, f"HTTP {st}")

    # ── 1. 读接口鉴权 ──────────────────────────────────────
    print("== 1. 读接口匿名 401 ==")
    for p in ("/api/machines", "/api/models", "/api/floors"):
        st, _ = http("GET", p)
        check(f"匿名 GET {p} → 401", st == 401, f"HTTP {st}")
    st, _ = http("GET", "/api/machines", token=token)
    check("带 token GET /api/machines → 200", st == 200, f"HTTP {st}")

    # ── 2. WS 鉴权 ────────────────────────────────────────
    print("== 2. WS 握手鉴权 ==")
    st_no = ws_handshake_status("/ws/realtime")
    check("无 token 握手被拒（403）", st_no == 403, f"HTTP {st_no}")
    st_ok = ws_handshake_status(f"/ws/realtime?token={token}")
    check("带有效 token 升级成功（101）", st_ok == 101, f"HTTP {st_ok}")

    # ── 3. debug 注入 admin-only ───────────────────────────
    print("== 3. debug 注入 admin-only ==")
    from database import SessionLocal
    from models import User
    from core.services.security import issue_token, hash_password
    db = SessionLocal()
    try:
        tmp = db.query(User).filter(User.username == "t6_tmp_user").first()
        if not tmp:
            tmp = User(id=f"u_t6_{int(time.time())}",
                       username="t6_tmp_user", display_name="T6临时用户",
                       role="user", password_hash=hash_password("T6tmp#123"),
                       created_at=datetime_now_iso())
            db.add(tmp)
            db.commit()
            db.refresh(tmp)
        user_token = issue_token(str(tmp.id))
    finally:
        db.close()

    st, _ = http("GET", "/api/machines", token=token)
    st, machines = http("GET", "/api/machines", token=user_token)
    mid = ""
    if st == 200 and isinstance(machines, list) and machines:
        mid = (machines[0] or {}).get("id", "")
    st, _ = http("POST", "/api/debug/event",
                 {"tool_id": mid or "X", "event_name": "Start"}, token=user_token)
    check("普通用户注入 → 403", st == 403, f"HTTP {st} (mid={mid!r})")

    # 清理临时用户
    db = SessionLocal()
    try:
        db.query(User).filter(User.username == "t6_tmp_user").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    # ── 4. 登录防爆破 ──────────────────────────────────────
    print("== 4. 登录防爆破（用一次性用户名，不污染 admin） ==")
    lock_user = f"t6_lock_{int(time.time())}"
    last = 0
    for i in range(6):
        st, body = http("POST", "/api/auth/login-password",
                        {"username": lock_user, "password": "wrong"})
        last = st
    check("连续6次失败第6次 → 429", last == 429, f"HTTP {last}")
    st, _ = http("POST", "/api/auth/login-password",
                 {"username": "admin", "password": "admin123"})
    check("其他用户名不受影响（admin 仍可登录）", st == 200, f"HTTP {st}")

    # ── 5. SSO 信任头 ──────────────────────────────────────
    print("== 5. SSO 信任头默认仅回环 ==")
    from modules.system_admin.routes.auth import _sso_header_trusted
    loopback = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    intranet = SimpleNamespace(client=SimpleNamespace(host="192.168.1.50"))
    check("回环 127.0.0.1 信任", _sso_header_trusted(loopback) is True)
    old_nets = os.environ.pop("FABTWIN_TRUST_SSO_NETS", None)
    check("内网 192.168.1.50 不再默认信任", _sso_header_trusted(intranet) is False)
    os.environ["FABTWIN_TRUST_SSO_NETS"] = "192.168.1.0/24"
    check("显式声明网段后信任", _sso_header_trusted(intranet) is True)
    os.environ.pop("FABTWIN_TRUST_SSO_NETS", None)
    if old_nets is not None:
        os.environ["FABTWIN_TRUST_SSO_NETS"] = old_nets

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（安全加固四项符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


def datetime_now_iso():
    from datetime import datetime
    return datetime.now().isoformat()


if __name__ == "__main__":
    sys.exit(main())
