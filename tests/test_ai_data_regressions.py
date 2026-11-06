# -*- coding: utf-8 -*-
"""AI 会话/生产数据整改的纯单元回归测试（不需要数据库）。

覆盖：
- RV/debug raw_id 生成器：TID.Z 前缀、固定宽度微秒、UUID hex、长度与排序兼容
- 历史 keyset 翻页游标语义：本页最小 raw_id 直接作为游标，下一页严格 <
  （零填充连续 ID 不丢宽度、多页无漏无重、非数字 ID 不崩）
- FABTWIN_AI_SQL_TIMEOUT 默认值与合法边界
- AIConversation 模型：session_id 主键、user_id String(255)
- 会话属主键控：user/session 复合键与 machine_id 首次绑定不可换绑
- describe_fab_table：非法/未知/受限输入拒绝（复用 .schema.schema_catalog）
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


# ---------------------------------------------------------------- raw_id 生成器

def test_generate_raw_id_format():
    from modules.production_monitor.routes.rvmessages import generate_raw_id

    rid = generate_raw_id()
    assert rid.startswith("TID.Z")
    assert re.fullmatch(r"TID\.Z\d{20}[0-9a-f]{16}", rid), rid
    assert len(rid) <= 255  # DT_EVENT_RAW.RAW_ID 列宽


def test_generate_raw_id_monotonic_unique():
    from modules.production_monitor.routes.rvmessages import generate_raw_id

    ids = [generate_raw_id() for _ in range(2000)]
    assert len(set(ids)) == 2000, "同微秒并发也不得撞主键"
    # 固定宽度微秒前缀（5..25 位）单调不减；同微秒内 UUID 段无序属预期
    ts_prefix = [rid[5:25] for rid in ids]
    assert ts_prefix == sorted(ts_prefix), "微秒时间戳段必须按生成顺序单调不减"


def test_debug_reuses_same_generator():
    from modules.production_monitor.routes import debug, rvmessages

    assert debug.generate_raw_id is rvmessages.generate_raw_id


def test_debug_env_gate_default_closed(monkeypatch):
    from modules.production_monitor.routes import debug

    monkeypatch.delenv("FABTWIN_DEBUG_WRITE_ENABLED", raising=False)
    assert debug._debug_write_enabled() is False
    monkeypatch.setenv("FABTWIN_DEBUG_WRITE_ENABLED", "1")
    assert debug._debug_write_enabled() is True
    monkeypatch.setenv("FABTWIN_DEBUG_WRITE_ENABLED", "TRUE")
    assert debug._debug_write_enabled() is True
    monkeypatch.setenv("FABTWIN_DEBUG_WRITE_ENABLED", "0")
    assert debug._debug_write_enabled() is False


# ------------------------------------------------------- 历史 keyset 游标语义

def _page(rows_desc, cursor, limit):
    """模拟 history.py 的服务端语义：raw_id < 游标，按 raw_id 倒序取 limit 条。"""
    rows = [r for r in rows_desc if cursor is None or r < cursor]
    rows.sort(reverse=True)
    return rows[:limit]


def test_keyset_cursor_zero_padded_no_gap_no_overlap():
    ids = [f"SEED{n:010d}" for n in range(100, 89, -1)]  # SEED0000000100 .. SEED0000000090
    page1 = _page(ids, None, 4)
    assert len(page1) == 4
    cursor = min(page1)  # 本页最小 raw_id 直接作为游标
    assert cursor == "SEED0000000097"
    page2 = _page(ids, cursor, 4)
    assert not set(page1) & set(page2), "两页不得重叠"
    assert max(page2) < min(page1), "第二页整体小于第一页"
    expected_next = "SEED0000000096"  # 紧邻行不得被跳过
    assert page2[0] == expected_next, "减一游标会漏掉紧邻行"


def test_keyset_cursor_multi_page_exhaustive():
    ids = [f"SEED{n:010d}" for n in range(50, 0, -1)]
    seen, cursor, pages = set(), None, 0
    while True:
        page = _page(ids, cursor, 7)
        if not page:
            break
        assert not set(page) & seen, "任何两页不得重叠"
        seen |= set(page)
        pages += 1
        cursor = min(page)
    assert seen == set(ids), "翻页必须无漏行"
    assert pages == (len(ids) + 6) // 7


def test_keyset_cursor_non_numeric_id():
    ids = [
        "TID.Z00000000170000000001aabbccddeeff0011",
        "TID.Z00000000170000000000ffeeddccbbaa9900",
    ]
    page1 = _page(ids, None, 1)
    cursor = min(page1)
    assert cursor == ids[0], "非数字 ID 游标原样返回，不得做减一运算"
    assert _page(ids, cursor, 1) == [ids[1]]


# ------------------------------------------------------- SQL 超时环境变量边界

def test_statement_timeout_default_and_bounds(monkeypatch):
    from modules.ai_assistant.services import sql as ai_sql

    monkeypatch.delenv("FABTWIN_AI_SQL_TIMEOUT", raising=False)
    assert ai_sql.get_statement_timeout_sec() == 20.0
    monkeypatch.setenv("FABTWIN_AI_SQL_TIMEOUT", "0.01")
    assert ai_sql.get_statement_timeout_sec() == 1.0
    monkeypatch.setenv("FABTWIN_AI_SQL_TIMEOUT", "9999")
    assert ai_sql.get_statement_timeout_sec() == 120.0
    monkeypatch.setenv("FABTWIN_AI_SQL_TIMEOUT", "not-a-number")
    assert ai_sql.get_statement_timeout_sec() == 20.0


# ------------------------------------------------------------- 模型与会话属主

def test_ai_conversation_model_shape():
    from sqlalchemy import String

    from models import AIConversation

    pk_cols = [c.name for c in AIConversation.__table__.primary_key.columns]
    assert pk_cols == ["session_id"]
    user_id_col = AIConversation.__table__.c.user_id
    assert isinstance(user_id_col.type, String)
    assert user_id_col.type.length == 255
    index_names = {ix.name for ix in AIConversation.__table__.indexes}
    assert {"ix_ai_conv_user_session", "ix_ai_conv_user_updated"} <= index_names


def test_conversation_owner_keys():
    from modules.ai_assistant.services.conversations import (
        _machine_conflict,
        _session_key,
        _user_key,
    )

    assert _user_key(42) == "42"
    assert _user_key("u-1") == "u-1"
    assert _user_key(None) == ""
    assert _session_key(7, "sess_x") == ("7", "sess_x")
    assert _machine_conflict("OXE01", "OXE02") is True
    assert _machine_conflict("OXE01", "OXE01") is False
    assert _machine_conflict(None, "OXE02") is False, "首次绑定允许从空到有机台"
    assert _machine_conflict("OXE01", None) is False


def test_chat_signature_carries_owner_and_snapshot():
    import inspect

    from modules.ai_assistant.services.middleware import AIMiddleware

    for name in ("chat", "chat_stream"):
        params = inspect.signature(getattr(AIMiddleware, name)).parameters
        assert "user_id" in params, f"{name} 必须接收 user_id 做属主隔离"
        assert "_chat_config" in params, f"{name} 必须接收请求级配置快照"
    prepare_params = inspect.signature(AIMiddleware.prepare_chat).parameters
    assert {"session_id", "user_id", "machine_id", "config_id"} <= set(prepare_params)


# ------------------------------------------------------------ describe_fab_table

def test_describe_fab_table_rejects_bad_input():
    from modules.ai_assistant.services.schema import schema_catalog
    from modules.ai_assistant.services.sql_tools import describe_fab_table

    bad = describe_fab_table(None, "1;DROP TABLE users")
    assert bad.get("error") == "invalid_table_name"

    forbidden = sorted(schema_catalog.forbidden_table_names())
    assert forbidden, "schema_catalog 必须提供受限表清单"
    res = describe_fab_table(None, forbidden[0])
    assert res.get("error") == "forbidden_table"

    unknown = describe_fab_table(None, "DEFINITELY_NOT_A_TABLE_12345")
    assert unknown.get("error") == "unknown_table"

    listing = describe_fab_table(None, "")
    assert listing.get("tables") and not listing.get("error")

    valid = schema_catalog.table_names()[0]
    ok = describe_fab_table(None, valid)
    assert not ok.get("error")
    assert valid.upper() in ok["answer"].upper()
