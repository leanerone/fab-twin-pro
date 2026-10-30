# -*- coding: utf-8 -*-
"""LAM2300 全链验证：注入一炉完整流程事件（复用 OXE 26 步词表）

走真实链路：/api/debug/event → DT_EVENT_RAW → db_poller → WS raw_event →
模型编辑器「动画调试」MotionPreview（lam2300 deriver）→ 动画。
用法：python scripts/inject_lam2300_cycle.py [backend_url]
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002"
TOOL = "LAM2300-1"


def post(path, body, token=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    tok = post("/api/auth/login-password", {"username": "admin", "password": "admin123"})["token"]

    # 一炉完整流程：POD 上port → 取片 → 寻边 → 进腔 PM1 加工 → 出腔回 port → 移走
    seq = [
        ("POD_PLACED",           {"PORT": "1", "LOT_ID": "LOT230001"}),
        ("COMPLETED_PORT_LOCK",  {"PORT": "1"}),
        ("BATCH_INFO_FROM_ECUI", {"PORT": "1", "LOT_ID": "LOT230001", "SLOT": "1"}),
        ("MVIN",                 {"PORT": "1", "SLOT": "1"}),
        ("DOOR_OPEN",            {"PORT": "1"}),
        ("LOAD_CYCLE_STARTED",   {"PORT": "1", "SLOT": "1"}),
        ("LOAD_CYCLE_COMPLETED", {"PORT": "1", "SLOT": "1"}),
        ("STARTMAPPING",         {"PORT": "1"}),
        ("WAFER_MAPPING",        {"PORT": "1", "SLOT": "1"}),
        ("ENDMAPPING",           {"PORT": "1"}),
        ("WAFERLOADED",          {"CHAMBER": "A", "SLOT": "1"}),
        ("START",                {"CHAMBER": "A"}),
        ("PS",                   {"CHAMBER": "A"}),
        ("PE",                   {"CHAMBER": "A"}),
        ("WAFERUNLOADED",        {"CHAMBER": "A", "SLOT": "1"}),
        ("MVOU",                 {"CHAMBER": "A"}),
        ("READYTOUNLOAD",        {"CHAMBER": "A"}),
        ("TRANSFER",             {}),
        ("UNLOAD_CYCLE_COMPLETED", {"PORT": "1"}),
        ("ALARM_REPORT",         {"CHAMBER": "B", "alarm_text": "PM2 PRESSURE HIGH"}),
        ("DOOR_CLOSE",           {"PORT": "1"}),
        ("POD_REMOVED",          {"PORT": "1"}),
    ]
    for i, (name, params) in enumerate(seq, 1):
        body = {"tool_id": TOOL, "event_name": name, "event_type": "VFEI", "params": params}
        try:
            post("/api/debug/event", body, tok)
            print(f"[{i:02d}/{len(seq)}] {name} {params}")
        except Exception as e:  # noqa: BLE001
            print(f"[{i:02d}] {name} 失败: {e}")
            return 1
        time.sleep(1.2)  # 略大于 poller 1s 轮询间隔，逐条实时推送
    print("[DONE] 全部事件已注入，等待 db_poller → WS → 前端")
    return 0


if __name__ == "__main__":
    sys.exit(main())
