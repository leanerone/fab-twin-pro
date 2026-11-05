# -*- coding: utf-8 -*-
"""T3 回归：AI 聊天会话持久化 + 内存上限（2026-11-06）

验证：
  1. 每轮对话落库 ai_chat_sessions
  2. 模拟重启（清空内存）后同 session 继续对话 → 上下文从 DB 恢复，不归零
  3. 内存会话 LRU 上限（默认 200），最旧被淘汰
  4. _dify_conv_map 运行时上限 500
  5. clear_session 同时清内存与 DB

运行：python tests/ai/test_session_persist.py
前置：Oracle 可用；ai_chat_sessions 表已建（sql/v2.21_add_ai_chat_sessions.sql）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


def main():
    from modules.ai_assistant.services.middleware import AIMiddleware
    from modules.ai_assistant.services.config_store import _get_db
    from models import AIChatSession

    m = AIMiddleware()

    # ── 1. 两轮对话落库 ────────────────────────────────────
    print("== 1. 每轮对话落库 ==")
    sid = "sess_t3_persist_a"
    m.chat("今天有多少报警", session_id=sid, force_provider="local")
    m.chat("再看看产量", session_id=sid, force_provider="local")
    db = _get_db()
    try:
        row = db.query(AIChatSession).filter(AIChatSession.session_id == sid).first()
    finally:
        db.close()
    check("DB 中存在会话记录", row is not None)
    check("消息条数 >= 4（2问2答）", row is not None and (row.message_count or 0) >= 4,
          f"count={row.message_count if row else None}")
    check("messages 为合法 JSON 数组", row is not None and isinstance(__import__('json').loads(row.messages), list))

    # ── 2. 模拟重启恢复 ────────────────────────────────────
    print("== 2. 重启后从 DB 恢复 ==")
    m.sessions.clear()  # 模拟进程重启（内存全丢）
    m.chat("状态如何", session_id=sid, force_provider="local")
    db = _get_db()
    try:
        row2 = db.query(AIChatSession).filter(AIChatSession.session_id == sid).first()
    finally:
        db.close()
    cnt2 = row2.message_count if row2 else 0
    check("重启后消息续写不归零（>=6）", cnt2 >= 6, f"count={cnt2}")
    msgs = __import__('json').loads(row2.messages) if row2 and row2.messages else []
    first_user = next((x for x in msgs if x.get("role") == "user"), {})
    check("最早一条用户消息仍在（上下文完整）",
          first_user.get("content") == "今天有多少报警",
          f"first={first_user.get('content', '')[:20]!r}")

    # ── 3. 内存 LRU 上限 ───────────────────────────────────
    print("== 3. 内存会话 LRU 上限 ==")
    m.sessions.clear()
    for i in range(250):
        m._get_or_create_session(f"sess_lru_{i:04d}")
    check("内存会话数不超过 200", len(m.sessions) <= 200, f"len={len(m.sessions)}")
    check("最旧的被淘汰", "sess_lru_0000" not in m.sessions)
    check("最新的保留", "sess_lru_0249" in m.sessions)

    # ── 4. dify conv map 上限 ──────────────────────────────
    print("== 4. _dify_conv_map 上限 ==")
    m._dify_conv_map.clear()
    for i in range(520):
        m._conv_put(f"sess_cm_{i:04d}", f"cid-{i}")
    check("映射数不超过 500", len(m._dify_conv_map) <= 500, f"len={len(m._dify_conv_map)}")
    check("最新映射可取回", m._conv_get("sess_cm_0519") == "cid-519")

    # ── 5. clear_session 双清 ──────────────────────────────
    print("== 5. clear_session 内存+DB 双清 ==")
    ok = m.clear_session(sid)
    db = _get_db()
    try:
        row3 = db.query(AIChatSession).filter(AIChatSession.session_id == sid).first()
    finally:
        db.close()
    check("返回 True", ok is True)
    check("DB 记录已删", row3 is None)

    # 清理 LRU/CM 测试残留（避免污染开发库）
    db = _get_db()
    try:
        n1 = db.query(AIChatSession).filter(AIChatSession.session_id.like("sess_lru_%")).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（会话持久化 + 内存上限符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
