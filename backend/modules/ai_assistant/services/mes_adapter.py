# -*- coding: utf-8 -*-
"""MES 直连适配层（T5 2026-11-06 夜班）

背景：MES Lot 查询此前只走 n8n MCP Server（tools.get_mes_lot_info → MCP → n8n → MES），
n8n 是不稳定依赖。本适配层让直连通道优先：MES_DB_* 环境变量配置齐全时直连 MES Oracle
（oracledb thin 模式，无需 Instant Client），未配置或失败自动落到原有 MCP 通道——
**未配置时零行为变化**。

环境变量契约（全部缺省 = 适配层休眠）：
  MES_DB_USER        MES 库账号
  MES_DB_PASSWORD    MES 库密码
  MES_DB_DSN         Oracle DSN，如 "mes-host:1521/MESDB"
  MES_LOT_SQL        可选。Lot 查询 SQL，命名绑定 :lot；
                     缺省 "SELECT * FROM MES_LOT WHERE LOT_ID = :lot FETCH FIRST 1 ROWS ONLY"
  MES_LOT_COLUMN_MAP 可选。JSON，标准字段→实际列名，如 {"product": "PRODUCT_CODE"}；
                     缺省用内置别名表（PRODUCT/PRODUCT_ID/... → product）

输出：与 n8n 通道同一行结构（lowercase 标准字段名），调用方无感知。
"""
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("fabtwin.mes")

DEFAULT_LOT_SQL = "SELECT * FROM MES_LOT WHERE LOT_ID = :lot FETCH FIRST 1 ROWS ONLY"

# 标准字段 → 候选列名（大写）。首个命中的列生效；MES_LOT_COLUMN_MAP 优先于本表。
_COLUMN_ALIASES: Dict[str, tuple] = {
    "lot": ("LOT_ID", "LOT", "ID"),
    "product": ("PRODUCT", "PRODUCT_ID", "PRODUCT_NAME", "PRODUCTCODE", "PRODUCT_CODE"),
    "process": ("PROCESS", "PROCESS_OP", "OPERATION", "PROCESSFLOW", "PROCESS_FLOW"),
    "processversion": ("PROCESSVERSION", "PROCESS_VERSION", "PROCESS_VER"),
    "route": ("ROUTE", "ROUTE_ID", "ROUTENAME", "ROUTE_NAME"),
    "step": ("STEP", "STEP_ID", "CURR_STEP", "CURRENTSTEP", "STEPNAME", "STEP_NAME"),
    "lotjobstatus": ("LOTJOBSTATUS", "STATUS", "LOT_STATUS", "LOTSTATE", "LOT_STATE"),
    "currentquantity": ("CURRENTQUANTITY", "QTY", "QUANTITY", "WAFERQTY", "WAFER_QTY", "WAFERCOUNT"),
    "cassette": ("CASSETTE", "CASSETTE_ID", "CARRIER", "LOTCARRIER"),
    "lottype": ("LOTTYPE", "LOT_TYPE"),
    "wafertype": ("WAFERTYPE", "WAFER_TYPE"),
    "isrework": ("ISREWORK", "REWORK"),
}


def mes_direct_configured() -> bool:
    """直连通道是否已配置（三项必需环境变量齐全）"""
    return bool(
        os.getenv("MES_DB_USER") and os.getenv("MES_DB_PASSWORD") and os.getenv("MES_DB_DSN")
    )


def _column_map() -> Dict[str, str]:
    """生效的字段→列名映射（env JSON 优先，缺省用内置别名表）"""
    raw = os.getenv("MES_LOT_COLUMN_MAP", "")
    if raw:
        try:
            user_map = json.loads(raw)
            if isinstance(user_map, dict) and user_map:
                return {str(k).lower(): str(v) for k, v in user_map.items()}
        except Exception as e:
            logger.warning("MES_LOT_COLUMN_MAP 不是合法 JSON，使用内置别名表: %s", e)
    return {field: cols[0] for field, cols in _COLUMN_ALIASES.items()}


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """DB 行（列名大写）→ n8n 通道同构的标准字段行（lowercase）"""
    upper = {str(k).upper(): v for k, v in row.items()}
    cmap = _column_map()
    out: Dict[str, Any] = {}
    # 1) 按映射表取标准字段
    for field, col in cmap.items():
        if col in upper:
            out[field] = upper[col]
    # 2) 未映射到的列原样保留（小写），LLM 仍可看到
    mapped_cols = {str(c).upper() for c in cmap.values()}
    for k, v in upper.items():
        if k not in mapped_cols:
            out.setdefault(str(k).lower(), v)
    return out


def query_lot_direct(lot_id: str) -> Optional[Dict[str, Any]]:
    """直连 MES 查询 Lot。

    Returns:
        {"row": 标准字段行, "sql": 实际SQL, "source": "direct"}；未配置/失败一律 None
        （调用方落到 MCP 兜底），异常只记日志不外抛。
    """
    if not lot_id or not mes_direct_configured():
        return None

    sql = os.getenv("MES_LOT_SQL", DEFAULT_LOT_SQL)
    try:
        import oracledb  # thin 模式，无需 Instant Client

        with oracledb.connect(
            user=os.getenv("MES_DB_USER"),
            password=os.getenv("MES_DB_PASSWORD"),
            dsn=os.getenv("MES_DB_DSN"),
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, lot=str(lot_id))
                cols = [d[0] for d in cur.description] if cur.description else []
                raw = cur.fetchone()
        if not raw:
            logger.info("MES 直连未查到 Lot %s（可能不在 MES 库）", lot_id)
            return None
        row = _normalize_row(dict(zip(cols, raw)))
        logger.info("MES 直连命中 Lot %s（字段 %d 个）", lot_id, len(row))
        return {"row": row, "sql": sql, "source": "direct"}
    except Exception as e:
        logger.warning("MES 直连失败，将落到 MCP 兜底: %s", str(e)[:200])
        return None
