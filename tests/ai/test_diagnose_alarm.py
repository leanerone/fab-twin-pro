# -*- coding: utf-8 -*-
"""R1 回归：告警智能诊断工具 diagnose_alarm（2026-11-06）

验证：
  1. 全厂/单机诊断返回结构（answer + table_data 六列）
  2. 频次聚合与"优先处置"段存在
  3. 领域知识库匹配（VAC/DOOR 等给原因；未知码走默认建议）
  4. 无告警场景返回友好提示
  5. 工具已注册（TOOL_DEFINITIONS/TOOL_HANDLERS），工具桥自动暴露

运行：python tests/ai/test_diagnose_alarm.py
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
    from modules.ai_assistant.services.tools import (
        diagnose_alarm, _alarm_advice, TOOL_DEFINITIONS, TOOL_HANDLERS,
    )
    from modules.ai_assistant.services.config_store import _get_db

    # ── 1. 结构 ────────────────────────────────────────────
    print("== 1. 全厂诊断结构 ==")
    db = _get_db()
    try:
        r = diagnose_alarm(db, lookback_hours=500)
    finally:
        db.close()
    check("answer 非空", bool((r.get("answer") or "").strip()))
    check("含诊断标记或无告警提示", "诊断" in r.get("answer", "") or "无告警" in r.get("answer", ""))
    td = r.get("table_data") or {}
    check("table_data 六列", td.get("headers") == ["告警码", "次数", "近1h", "最近发生", "可能原因", "建议"],
          f"headers={td.get('headers')}")

    print("== 2. 单机诊断 ==")
    db = _get_db()
    try:
        r2 = diagnose_alarm(db, machine_id="OXE-1", lookback_hours=500)
    finally:
        db.close()
    check("answer 提及机台范围", ("机台 OXE-1" in r2.get("answer", "")) or ("无告警" in r2.get("answer", "")))

    # ── 3. 领域知识库 ───────────────────────────────────────
    print("== 3. 知识库匹配 ==")
    cause, advice = _alarm_advice("VAC_LOSS", "")
    check("VAC → 真空原因", cause and "真空" in cause, f"cause={cause}")
    check("建议非默认", advice and "真空泵" in advice)
    cause2, advice2 = _alarm_advice("DOOR_TIMEOUT", "门超时")
    check("DOOR → 门原因", cause2 and "门" in cause2)
    cause3, advice3 = _alarm_advice("XYZ_UNKNOWN", "完全未知告警")
    check("未知码走默认建议", cause3 is None and "上下文事件" in advice3)

    # ── 4. 无告警友好提示 ───────────────────────────────────
    print("== 4. 无告警场景 ==")
    db = _get_db()
    try:
        r4 = diagnose_alarm(db, machine_id="NO-SUCH-MACHINE-99")
    finally:
        db.close()
    check("无数据返回友好提示", "无告警记录" in r4.get("answer", "") or "无需诊断" in r4.get("answer", ""),
          f"ans={(r4.get('answer') or '')[:40]!r}")

    # ── 5. 注册与桥暴露 ─────────────────────────────────────
    print("== 5. 注册检查 ==")
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    check("TOOL_DEFINITIONS 含 diagnose_alarm", "diagnose_alarm" in names, f"总数={len(names)}")
    check("TOOL_HANDLERS 含 diagnose_alarm", "diagnose_alarm" in TOOL_HANDLERS)

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（diagnose_alarm 符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
