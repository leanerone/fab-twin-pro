# -*- coding: utf-8 -*-
"""T2 回归：force_provider 强制引擎路由（2026-11-06）

验证：
  1. chat(force_provider="local")   → 走本地规则引擎，provider=="local"
  2. chat(force_provider="llm")     → 走 OpenAI 兼容配置（打在替身上），provider 回传
  3. chat(force_provider="dify")    → 跳过机台专属配置走全局 Dify
  4. chat_stream(force_provider=…)  → final 帧的 provider 字段如实
  5. 不传 force_provider 时行为与旧版完全一致（回归保护）

运行前置：普通模式替身已起（python tests/ai/mock_providers.py --port 8902）
运行：python tests/ai/test_force_provider.py --mock http://127.0.0.1:8902
"""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


async def collect_stream(m, **kw):
    """收集 chat_stream 的全部 SSE 帧（解析为对象列表）"""
    frames = []
    async for line in m.chat_stream(**kw):
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            frames.append(json.loads(payload))
        except Exception:
            pass
    return frames


def main():
    mock = "http://127.0.0.1:8902"
    for i, a in enumerate(sys.argv):
        if a == "--mock" and i + 1 < len(sys.argv):
            mock = sys.argv[i + 1]

    from modules.ai_assistant.services.middleware import AIMiddleware
    m = AIMiddleware()

    # ── 准备：把实例指向替身（不动 DB 配置）────────────────
    m.provider, m.base_url, m.api_key, m.model = "custom", f"{mock}/v1", "mock-key", "mock-model"
    m.dify_enabled, m.dify_base_url, m.dify_api_key = True, mock, "mock-key"

    # ── 1. force=local ────────────────────────────────────
    print("== chat force_provider=local ==")
    r = m.chat("OXE-51 状态怎么样", session_id="sess_fp_local_1", force_provider="local")
    check("provider=local", r.get("provider") == "local", f"got={r.get('provider')}")
    check("answer 非空", bool((r.get("answer") or "").strip()))

    # ── 2. force=llm（打替身）───────────────────────────────
    print("== chat force_provider=llm ==")
    r2 = m.chat("今天产量多少", session_id="sess_fp_llm_1", force_provider="llm")
    check("provider=custom", r2.get("provider") == "custom", f"got={r2.get('provider')}")
    check("命中替身 fixture（1,248）", "1,248" in (r2.get("answer") or ""), f"ans={r2.get('answer','')[:40]!r}")

    # ── 3. force=dify（打替身的 Dify 面）────────────────────
    print("== chat force_provider=dify ==")
    r3 = m.chat("今天产量多少", session_id="sess_fp_dify_1", force_provider="dify")
    check("provider=dify", r3.get("provider") == "dify", f"got={r3.get('provider')}")
    check("answer 非空（替身 Dify 应答）", bool((r3.get("answer") or "").strip()),
          f"ans={(r3.get('answer') or '')[:40]!r}")

    # ── 4. 流式 force ──────────────────────────────────────
    print("== chat_stream force_provider ==")
    frames_l = asyncio.run(collect_stream(
        m, question="OXE-51 状态", session_id="sess_fp_s1",
        machine_id=None, user_role="user", force_provider="local"))
    final_l = next((f for f in frames_l if f.get("event") == "final"), {})
    check("流式 local final.provider=local", final_l.get("provider") == "local",
          f"got={final_l.get('provider')}")

    frames_d = asyncio.run(collect_stream(
        m, question="今天产量", session_id="sess_fp_s2",
        machine_id=None, user_role="user", force_provider="dify"))
    final_d = next((f for f in frames_d if f.get("event") == "final"), {})
    check("流式 dify final.provider=dify", final_d.get("provider") == "dify",
          f"got={final_d.get('provider')}")
    check("流式 dify 有正文", bool((final_d.get("answer") or "").strip()))

    # ── 5. 回归保护：不传 force 行为不变 ─────────────────────
    print("== 默认路由不受影响 ==")
    r5 = m.chat("今天产量多少", session_id="sess_fp_none_1")
    check("默认路由照常出答案", bool((r5.get("answer") or "").strip()))
    r6 = m.chat("批量看下告警", session_id="sess_fp_weak_1", force_provider="llm",
                user_role="admin")
    check("admin 弱关键词 + force=llm 不进 n8n", r6.get("provider") == "custom",
          f"got={r6.get('provider')}")

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（force_provider 路由覆盖符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
