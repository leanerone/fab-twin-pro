"""慢测试（-m "not slow" 可跳过）：/api/lots/{lot_id} 走 payload CLOB LIKE '%lot%' 全表扫，
是交接文档「雷区 1」的直接实测 —— 在千万行上量出真实耗时，为物化列方案提供基线数据。
"""
import time

import pytest
from sqlalchemy import text

from conftest import record

pytestmark = pytest.mark.slow


@pytest.fixture()
def seeded_lot(client, db):
    """先经写入端点造一条带 lot_id 的事件，保证 LIKE 一定能命中。"""
    tool = "TEST-RW-LOT"
    resp = client.post(
        "/api/rv/message",
        json={
            "tool_id": tool,
            "source_message_id": "SM-LOT-1",
            "payload_json": _payload(tool),
        },
    )
    assert resp.status_code == 200, resp.text[:300]
    return "TESTLOT-K9"


def _payload(tool):
    import json

    return json.dumps(
        {
            "tool_id": tool,
            "lot_id": "TESTLOT-K9",
            "event_name": "BATCH_INFO_FROM_ECUI",
            "machine_mode": "PACKING",
            "alarm_code": "",
        }
    )


def test_lot_found_clob_like_baseline(client, db, seeded_lot):
    """命中路径：千万行 CLOB LIKE 全表扫 —— 物化列优化前的基线耗时。"""
    t0 = time.perf_counter()
    r = client.get(f"/api/lots/{seeded_lot}")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert seeded_lot in str(body) or body.get("machine_id") or body.get("events") is not None
    record("/api/lots/{id} 命中（CLOB LIKE 全表扫，10M 行基线）", elapsed, "雷区1实测")


def test_lot_not_found_cost(client, db):
    """未命中路径：同样付全表扫成本才能返回 404。"""
    t0 = time.perf_counter()
    r = client.get("/api/lots/__NO_SUCH_LOT__")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 404, f"不存在的 lot 应 404，实际 {r.status_code}"
    record("/api/lots/{id} 未命中 404（同样全表扫）", elapsed)


def test_lot_events_endpoint(client, db, seeded_lot):
    """/{lot}/events：5000 行上限的 CLOB 拉取路径。"""
    t0 = time.perf_counter()
    r = client.get(f"/api/lots/{seeded_lot}/events")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text[:300]
    evs = r.json()
    assert isinstance(evs, list) and len(evs) >= 1
    assert any(e.get("lot_id") == seeded_lot or seeded_lot in str(e) for e in evs)
    record("/api/lots/{id}/events（LIKE + limit 5000）", elapsed)
