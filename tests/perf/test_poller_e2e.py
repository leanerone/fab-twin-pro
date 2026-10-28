"""端到端验证：外部直接写库 → db_poller 轮询 → WebSocket 推送

这是本次最关键的回归测试。修复前 db_poller 从未启动（同步 on_startup 在线程池里
create_task 抛 RuntimeError），导致"WinForm/EAP 直接写 DT_EVENT_RAW"这条生产路径
完全不通；而走 rvmessages API 注入的事件会绕过轮询直接广播，所以端到端测试一直全绿，
问题长期未被发现。

本测试绕开所有 API，直接向 DT_EVENT_RAW 插一行，然后等 WebSocket 收到 raw_event。
收到 → 轮询链路真的工作。

用法：
    python tests/perf/test_poller_e2e.py
    python tests/perf/test_poller_e2e.py --tool PODOPENER-1 --wait 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta

import oracledb
import websockets

DSN = os.getenv("ORACLE_DSN", "localhost:1521/XEPDB1")
USER = os.getenv("ORACLE_USER", "fabtwin")
PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
WS_URL = os.getenv("FABTWIN_WS", "ws://localhost:8002/ws/realtime")


def insert_event(tool_id: str, raw_id: str) -> str:
    """直接向 DT_EVENT_RAW 插一行（模拟 EAP/WinForm 写入）"""
    now = datetime.now()
    # 与 rvmessages.py 保持一致：ISO T 分隔、本地时间
    ts = now.isoformat()
    conn = oracledb.connect(user=USER, password=PASSWORD, dsn=DSN)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dt_event_raw "
            "(raw_id, tool_id, source_system, source_message_id, "
            " received_ts_utc, event_ts_utc, payload_json, parse_status) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8)",
            [
                raw_id, tool_id, "E2E-TEST", f"MSG-{raw_id}",
                ts, ts,
                json.dumps({"event_name": "POD_PLACED", "lot_id": "E2E_LOT",
                            "_e2e_marker": raw_id}, ensure_ascii=False),
                "PARSED",
            ],
        )
        conn.commit()
        return ts
    finally:
        conn.close()


async def wait_for_event(raw_id: str, timeout: float) -> bool:
    async with websockets.connect(WS_URL, open_timeout=15) as ws:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "raw_event":
                continue
            payload = data.get("data", {}) or {}
            if raw_id in json.dumps(payload, ensure_ascii=False):
                print(f"  [WS] 收到目标事件: tool={payload.get('tool_id')} "
                      f"event={payload.get('event_name')} ts={payload.get('timestamp')}")
                return True
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", default="PODOPENER-1")
    ap.add_argument("--wait", type=float, default=25.0)
    args = ap.parse_args()

    # raw_id 必须用与真实 EAP 一致的单调前缀：本地库 received_ts_utc 是 VARCHAR2，
    # 轮询的回退路径按 raw_id 倒序取窗口，字典序不单调的 id 会被窗口排除。
    raw_id = f"TID.Z{int(time.time() * 1_000_000)}"
    print("=== db_poller 端到端验证 ===")
    print(f"  目标机台 : {args.tool}")
    print(f"  事件 raw_id: {raw_id}")
    print(f"  等待上限 : {args.wait}s")
    print()
    print("  步骤 1/3：连接 WebSocket ...")
    print("  步骤 2/3：直接向 DT_EVENT_RAW 插入一行（绕开所有 API）...")

    ts = insert_event(args.tool, raw_id)
    print(f"  已插入，received_ts_utc={ts}")

    print("  步骤 3/3：等待 WebSocket 推送 ...")
    ok = asyncio.run(wait_for_event(raw_id, args.wait))

    print()
    if ok:
        print("结果: 通过 —— 外部写库的事件被轮询发现并推送到了前端")
        print("      （修复前这条路径是不通的）")
        return 0
    print("结果: 失败 —— 超时未收到推送。检查：")
    print("      1) 后端 DB_POLLER_ENABLED 是否为 True")
    print("      2) curl http://localhost:8002/health 里 db_poller 是否 status=ok")
    print("      3) 后端日志是否有 [DB Poller] 启动DB事件轮询服务")
    return 1


if __name__ == "__main__":
    sys.exit(main())
