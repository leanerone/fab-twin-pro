"""写路径：POST /api/rv/message（RV 实时消息 → DT_EVENT_RAW + DT_EVENT_RAW_CUR）。

覆盖：正常落库回读、CUR 表 upsert、非法 payload 的行为、
以及 raw_id 秒级精度导致的主键碰撞（已知缺陷的回归记录）。
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from conftest import make_rv_payload


def _tool():
    return "TEST-RW-" + uuid.uuid4().hex[:8]


def test_rv_message_write_and_readback(client, db):
    """写入 → 双表落库 → 三个读端点全部可回读。"""
    tool = _tool()
    r = client.post(
        "/api/rv/message",
        json={
            "tool_id": tool,
            "source_message_id": "SM-1",
            "payload_json": make_rv_payload(tool),
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["status"] == "ok"
    raw_id = body["raw_id"]
    assert raw_id.startswith("TID.")

    # DT_EVENT_RAW 落库
    row = db.execute(
        text("SELECT tool_id, payload_json, parse_status FROM DT_EVENT_RAW WHERE raw_id = :r"),
        {"r": raw_id},
    ).fetchone()
    assert row is not None, "DT_EVENT_RAW 必须落库"
    assert row[0] == tool
    assert "TESTLOT-K9" in str(row[1])

    # DT_EVENT_RAW_CUR upsert（同 tool 单行）
    cur = db.execute(
        text("SELECT raw_id, tool_id FROM DT_EVENT_RAW_CUR WHERE tool_id = :t"), {"t": tool}
    ).fetchone()
    assert cur is not None, "DT_EVENT_RAW_CUR 必须落库"
    assert cur[0] == raw_id

    # /api/rv/current 回读
    rc = client.get(f"/api/rv/current/{tool}")
    assert rc.status_code == 200, rc.text[:300]

    # /api/history 实时模式回读
    rh = client.get(f"/api/history/{tool}", params={"limit": 10})
    assert rh.status_code == 200
    evs = rh.json()["events"]
    assert any(e["raw_id"] == raw_id for e in evs), "实时模式必须能看到刚写入的事件"


def test_rv_message_cur_upsert_not_append(client, db):
    """同一机台第二次写入：CUR 表应更新（merge）而不是追加。"""
    tool = _tool()
    import time as _t

    for i, sm in enumerate(("SM-A", "SM-B")):
        r = client.post(
            "/api/rv/message",
            json={"tool_id": tool, "source_message_id": sm, "payload_json": make_rv_payload(tool)},
        )
        assert r.status_code == 200, r.text[:300]
        if i == 0:
            _t.sleep(1.1)  # 避开 raw_id 秒级碰撞（该缺陷另行单测记录）

    n = db.execute(
        text("SELECT COUNT(*) FROM DT_EVENT_RAW_CUR WHERE tool_id = :t"), {"t": tool}
    ).scalar()
    assert n == 1, f"CUR 表应只有 1 行（merge 语义），实际 {n}"
    n_raw = db.execute(
        text("SELECT COUNT(*) FROM DT_EVENT_RAW WHERE tool_id = :t"), {"t": tool}
    ).scalar()
    assert n_raw == 2, "RAW 表应保留 2 条历史"


def test_rv_message_invalid_json_current_behavior(client, db):
    """已知不一致（回归记录）：payload_json 非法时行已 commit，但 json.loads 在
    commit 之后抛错 → 客户端拿到 500，数据却已写入。
    修复后（校验前置或宽容解析）请把断言改为 200/400 + 明确的落库语义。"""
    tool = _tool()
    r = client.post(
        "/api/rv/message",
        json={"tool_id": tool, "source_message_id": "SM-BAD", "payload_json": "{not-valid-json"},
    )
    assert r.status_code == 500, f"当前行为应为 500，实际 {r.status_code}"
    n = db.execute(
        text("SELECT COUNT(*) FROM DT_EVENT_RAW WHERE tool_id = :t"), {"t": tool}
    ).scalar()
    assert n == 1, "行已提交（500 之外的副作用）—— 这就是要记录的不一致"


def test_rv_message_same_second_rawid_collision(client, db):
    """已知缺陷（回归记录）：raw_id = f"TID.{int(ts)}" 秒级精度，
    同一秒内第二条消息主键冲突 → 500，事件丢失。
    修复后（对齐 debug.py 的毫秒+随机数写法）改为断言两次都 200 且 raw_id 不同。"""
    tool = _tool()
    r1 = client.post(
        "/api/rv/message",
        json={"tool_id": tool, "source_message_id": "SM-C1", "payload_json": make_rv_payload(tool)},
    )
    r2 = client.post(
        "/api/rv/message",
        json={"tool_id": tool, "source_message_id": "SM-C2", "payload_json": make_rv_payload(tool)},
    )
    assert r1.status_code == 200
    if r2.status_code == 200:
        # 极少数情况下跨过了秒边界：两条都成功则 raw_id 必然不同
        assert r1.json()["raw_id"] != r2.json()["raw_id"]
    else:
        assert r2.status_code == 500, f"碰撞应表现为 500，实际 {r2.status_code}"
        n = db.execute(
            text("SELECT COUNT(*) FROM DT_EVENT_RAW WHERE tool_id = :t"), {"t": tool}
        ).scalar()
        assert n == 1, "碰撞时第二条不得部分写入"


def test_raw_id_pk_is_global():
    """直接证明：raw_id 主键是全表唯一（跨机台也冲突）——碰撞影响的不是单机台。"""
    from database import SessionLocal
    from models import DT_EVENT_RAW

    s = SessionLocal()
    try:
        dup = "TIDZ.TEST." + uuid.uuid4().hex[:8]
        for i in range(2):
            s.add(
                DT_EVENT_RAW(
                    raw_id=dup,
                    tool_id=f"TEST-RW-PK{i}",
                    source_system="TEST",
                    source_message_id="SM-PK",
                    received_ts_utc="2026-10-26T00:00:00",
                    event_ts_utc="2026-10-26T00:00:00",
                    payload_json="{}",
                    parse_status="PARSED",
                )
            )
            if i == 0:
                s.commit()
        with pytest.raises(IntegrityError):
            s.commit()
    finally:
        s.rollback()
        s.close()
