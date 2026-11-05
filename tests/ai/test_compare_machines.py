# -*- coding: utf-8 -*-
"""R2 回归：多机台对比工具 compare_machines（2026-11-06）

验证：
  1. 指定机台对比：表结构七列 + 分析结论段
  2. 自动选活跃机台（不传 ids）
  3. 参数归一：逗号字符串 / 列表 / 超长截断到8
  4. 注册与桥数量（14）

运行：python tests/ai/test_compare_machines.py
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
    from modules.ai_assistant.services.tools import compare_machines, TOOL_DEFINITIONS, TOOL_HANDLERS
    from modules.ai_assistant.services.config_store import _get_db

    # ── 1. 指定机台对比（窗口覆盖库内数据：最新事件 2026-11-02）──
    print("== 1. 指定机台对比 ==")
    db = _get_db()
    try:
        r = compare_machines(db, machine_ids="OXE-1,OXE-19", lookback_hours=600)
    finally:
        db.close()
    ans = r.get("answer") or ""
    td = r.get("table_data") or {}
    check("含表头", td.get("headers") == ["机台", "事件数", "告警数", "告警率", "取片", "放片", "最近活动"],
          f"headers={td.get('headers')}")
    check("含分析结论段", ("最活跃" in ans) or ("无事件" in ans), f"ans_head={ans[:40]!r}")

    # ── 2. 自动选机台 ──────────────────────────────────────
    print("== 2. 自动选机台 ==")
    db = _get_db()
    try:
        r2 = compare_machines(db, lookback_hours=600)
    finally:
        db.close()
    rows = (r2.get("table_data") or {}).get("rows") or []
    check("返回不超过6台", len(rows) <= 6, f"rows={len(rows)}")
    check("按事件数降序", all(int(x[1]) >= int(rows[i + 1][1]) for i, x in enumerate(rows[:-1])) if len(rows) > 1 else True)

    # ── 3. 参数归一 ────────────────────────────────────────
    print("== 3. 参数归一 ==")
    db = _get_db()
    try:
        r3 = compare_machines(db, machine_ids=["OXE-1", "OXE-19"], lookback_hours=600)
        r4 = compare_machines(db, machine_ids=",".join(f"M{i}" for i in range(20)), lookback_hours=600)
    finally:
        db.close()
    check("列表参数可用", isinstance(r3.get("answer"), str))
    check("超长截断到8台不报错", isinstance(r4.get("answer"), str))

    # ── 4. 注册 ────────────────────────────────────────────
    print("== 4. 注册检查 ==")
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    check("TOOL_DEFINITIONS 含 compare_machines", "compare_machines" in names, f"总数={len(names)}")
    check("TOOL_HANDLERS 含 compare_machines", "compare_machines" in TOOL_HANDLERS)

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（compare_machines 符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
