# -*- coding: utf-8 -*-
"""T5 回归：MES 直连适配层（2026-11-06）

验证：
  1. 未配置 MES_DB_* → 适配层休眠（返回 None），get_mes_lot_info 行为与旧版一致
  2. 直连通道（用本地 Oracle lots 表模拟 MES 库）→ 查询成功、字段标准化
  3. 直连配置了但连不上 → 返回 None（自动落到 MCP 兜底路径，不外抛）
  4. 列名映射：MES_LOT_COLUMN_MAP env 优先于内置别名表

运行：python tests/ai/test_mes_adapter.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


def main():
    from modules.ai_assistant.services import mes_adapter
    from modules.ai_assistant.services.tools import get_mes_lot_info
    from modules.ai_assistant.services.config_store import _get_db

    # ── 1. 未配置：休眠 ─────────────────────────────────────
    print("== 1. 未配置 MES_DB_* 时休眠 ==")
    for k in ("MES_DB_USER", "MES_DB_PASSWORD", "MES_DB_DSN", "MES_LOT_SQL", "MES_LOT_COLUMN_MAP"):
        os.environ.pop(k, None)
    check("mes_direct_configured()=False", mes_adapter.mes_direct_configured() is False)
    check("query_lot_direct 返回 None", mes_adapter.query_lot_direct("LOT100131") is None)

    db = _get_db()
    try:
        r = get_mes_lot_info(db, "LOT100131")
    finally:
        db.close()
    check("get_mes_lot_info 走 MCP 判定路径（行为不变）",
          "MCP" in (r.get("answer") or "") or "MES" in (r.get("answer") or ""),
          f"ans={(r.get('answer') or '')[:30]!r}")

    # ── 2. 直连通道（本地 lots 表模拟 MES 库）────────────────
    print("== 2. 直连通道命中 ==")
    # 本地库连接参数：从 backend/database.py 同源环境取（复用现有 DSN 探测结果）
    os.environ["MES_DB_USER"] = os.getenv("ORACLE_USER", "fabtwin")
    os.environ["MES_DB_PASSWORD"] = os.getenv("ORACLE_PASSWORD", "fabtwin")
    os.environ["MES_DB_DSN"] = os.getenv("ORACLE_DSN", "localhost:1521/xepdb1")
    # 用本地 lots 表模拟 MES LOT 表：别名对齐标准字段
    os.environ["MES_LOT_SQL"] = (
        "SELECT id AS LOT_ID, product AS PRODUCT, status AS LOTJOBSTATUS, "
        "wafer_count AS CURRENTQUANTITY, recipe_id AS ROUTE "
        "FROM lots WHERE UPPER(id) = UPPER(:lot) FETCH FIRST 1 ROWS ONLY"
    )
    check("mes_direct_configured()=True", mes_adapter.mes_direct_configured() is True)
    direct = mes_adapter.query_lot_direct("LOT100131")
    check("直连返回结果", direct is not None and direct.get("row") is not None,
          f"row_keys={list((direct or {}).get('row', {}).keys())[:6]}")
    row = (direct or {}).get("row") or {}
    check("标准化字段 product 存在", "product" in row, f"product={row.get('product')}")
    check("标准化字段 lotjobstatus 存在", "lotjobstatus" in row, f"status={row.get('lotjobstatus')}")
    check("标准化字段 currentquantity 存在", "currentquantity" in row, f"qty={row.get('currentquantity')}")

    db = _get_db()
    try:
        r2 = get_mes_lot_info(db, "LOT100131")
    finally:
        db.close()
    ans2 = r2.get("answer") or ""
    check("get_mes_lot_info 走直连并输出结构化答案",
          "MES 直连" in (r2.get("sql") or "") and "产品型号" in ans2,
          f"sql={(r2.get('sql') or '')[:30]!r}")

    # ── 3. 直连失败 → 落 MCP 兜底（不外抛）──────────────────
    print("== 3. 直连失败自动兜底 ==")
    os.environ["MES_DB_DSN"] = "127.0.0.1:1/NOSUCH"
    direct_fail = mes_adapter.query_lot_direct("LOT100131")
    check("连不上返回 None", direct_fail is None)

    # ── 4. 列名映射 env 优先 ────────────────────────────────
    print("== 4. MES_LOT_COLUMN_MAP 优先 ==")
    os.environ["MES_DB_DSN"] = "localhost:1521/xepdb1"
    os.environ["MES_LOT_SQL"] = (
        "SELECT id AS LOT, product AS PNAME, status AS ST, wafer_count AS EXTRA_QTY "
        "FROM lots WHERE UPPER(id) = UPPER(:lot) FETCH FIRST 1 ROWS ONLY"
    )
    os.environ["MES_LOT_COLUMN_MAP"] = json.dumps({
        "lot": "LOT", "product": "PNAME", "lotjobstatus": "ST",
    })
    direct2 = mes_adapter.query_lot_direct("LOT100131")
    row2 = (direct2 or {}).get("row") or {}
    check("env 映射生效（product←PNAME）", row2.get("product") not in (None, "N/A"),
          f"product={row2.get('product')}")
    check("未映射列原样透传（extra_qty）", "extra_qty" in row2, f"keys={list(row2.keys())}")

    # 清理 env（避免污染同进程其他测试）
    for k in ("MES_DB_USER", "MES_DB_PASSWORD", "MES_DB_DSN", "MES_LOT_SQL", "MES_LOT_COLUMN_MAP"):
        os.environ.pop(k, None)

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（MES 直连适配层符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
