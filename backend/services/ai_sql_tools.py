# -*- coding: utf-8 -*-
"""真实取数工具：把受控 SQL 通道包装成 AI 可调用的 function calling 工具。

这两个工具是「AI 智能化数据真实」的落点——此前 AI 只有 9 个硬编码查询，遇到
「上月按天分组产量」这类任意意图就只能瞎答；这里的 query_fab_data 让 AI 自己写 SQL、
由 ai_sql 安全层校验后**真实执行**，返回的 sql 字段是真正跑过的那条语句。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("fabtwin.ai_sql_tools")


def query_fab_data(db, sql: str = "", row_limit: int = 200) -> Dict[str, Any]:
    """按用户问题执行一条只读 SQL，返回真实结果行。

    安全约束由 services/ai_sql.py 保证：只能 SELECT、只能查白名单表、
    自动注入行数围栏、禁止多语句与注释藏毒。被拒时会把原因回给模型以便改写重试。
    """
    from .ai_sql import execute_readonly, format_result_for_llm

    if not sql or not str(sql).strip():
        return {"answer": "缺少 SQL。请用可用的表写一条只读 SELECT。", "sql": "", "table_data": []}

    cap = int(row_limit or 200)
    res = execute_readonly(db, sql, row_cap=cap)
    text = format_result_for_llm(res)

    out: Dict[str, Any] = {
        "answer": text,
        "sql": res.get("sql") or "",          # 真实执行过的那条语句
        "rows": res.get("rows", []),
        "row_count": res.get("row_count", 0),
        "truncated": res.get("truncated", False),
        "executed": bool(res.get("ok")),
        "table_data": [
            {"columns": res.get("columns", []), "rows": res.get("rows", [])},
        ] if res.get("ok") and res.get("rows") else [],
    }
    if not res.get("ok"):
        out["error"] = res.get("error")
    return out


def describe_fab_table(db, table_name: str = "") -> Dict[str, Any]:
    """查询某张表的全部字段定义，用于写 SQL 前确认列名、类型与业务含义。"""
    from .ai_schema import schema_catalog

    if not table_name:
        names = schema_catalog.table_names()
        return {
            "answer": "可用表清单：\n" + "\n".join(f"- {n}" for n in names),
            "sql": "",
            "tables": names,
        }
    detail = schema_catalog.to_table_ddl_text(table_name)
    return {"answer": detail, "sql": "", "table": table_name}


# ==================== Function Calling 声明 ====================
TOOL_DEFINITIONS_SQL = [
    {
        "type": "function",
        "function": {
            "name": "describe_fab_table",
            "description": (
                "查询某张表有哪些字段、各字段类型和业务含义。写 SQL 之前先用它确认列名，"
                "不要凭印象猜字段名。不传 table_name 则返回全部可用表清单。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名，如 dt_event_raw / machines / lots。留空则返回可用表清单。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_fab_data",
            "description": (
                "执行一条只读 SQL 查询真实数据，用于回答硬编码工具覆盖不到的任意问题"
                "（按天/按周分组统计、TOP N 排行、跨表关联、区间聚合等）。"
                "只能写单条 SELECT；时间字段是 ISO 字符串，用字符串区间比较；"
                "分页写 FETCH FIRST n ROWS ONLY；machines 的主键 id 与事件表的 tool_id 不同，"
                "跨表请经 machine_tool_mappings 转换。不确定字段时先调 describe_fab_table。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的只读 SELECT 语句（Oracle 方言）"
                    },
                    "row_limit": {
                        "type": "integer",
                        "description": "返回行数上限，默认 200，最大 1000",
                        "default": 200
                    }
                },
                "required": ["sql"]
            }
        }
    },
]

TOOL_HANDLERS_SQL = {
    "describe_fab_table": describe_fab_table,
    "query_fab_data": query_fab_data,
}

__all__ = ["TOOL_DEFINITIONS_SQL", "TOOL_HANDLERS_SQL", "query_fab_data", "describe_fab_table"]
