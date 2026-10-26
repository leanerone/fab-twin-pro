"""端到端：外部系统直写 DT_EVENT_RAW（WinForm/EAP 生产路径）→ db_poller 每秒轮询
→ WebSocket /ws/realtime 推送到前端。

这是实时链路的核心闭环：写入侧不经过任何 API，只写库。
raw_id 用 TIDZ. 前缀保证在 poller「raw_id desc 最新 100 行」窗口的顶部可见。
"""
import time
import uuid

import pytest
from sqlalchemy import text

from conftest import TEST_RAW_PREFIX, WsReader, make_rv_payload


def test_external_db_write_reaches_websocket(client, db):
    tool = "TEST-RW-WS-" + uuid.uuid4().hex[:6]
    raw_id = f"{TEST_RAW_PREFIX}{int(time.time() * 1000)}"

    db.execute(
        text(
            "INSERT INTO DT_EVENT_RAW (raw_id, tool_id, source_system, source_message_id,"
            " received_ts_utc, event_ts_utc, payload_json, parse_status)"
            " VALUES (:r, :t, 'WINFORM', 'SM-WS', :ts, :ts, :p, 'PARSED')"
        ),
        {"r": raw_id, "t": tool, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "p": make_rv_payload(tool)},
    )
    db.commit()

    with client.websocket_connect("/ws/realtime") as ws:
        reader = WsReader(ws)
        # 首帧是 connected 握手；随后等 poller 下一轮（1s 间隔）把新事件广播出来
        deadline = time.time() + 25
        seen = []
        while time.time() < deadline:
            msg = reader.next(timeout=2.0)
            if msg is None:
                continue
            if msg.get("__closed__"):
                break
            seen.append(msg)
            data = msg.get("data") or {}
            if msg.get("type") == "raw_event" and (
                data.get("tool_id") == tool or tool in str(data)
            ):
                assert data.get("event_name") or data.get("payload"), "推送必须带事件内容"
                return
        pytest.fail(
            f"25s 内未在 /ws/realtime 收到 tool={tool} 的推送；共收到 {len(seen)} 帧: "
            + str(seen[:3])[:300]
        )
