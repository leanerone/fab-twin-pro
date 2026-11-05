# -*- coding: utf-8 -*-
"""AI 工具桥服务层（T4 2026-11-06）：把 LLM Function Calling 的同一套工具
以 REST 形式暴露给 Dify 自定义工具（OpenAPI 导入）与外部编排器。

设计：
  - 与 providers/openai.py 的内联分发保持同一语义（machine_id 兜底、sql 诚实化标注）
  - openai.py 的内联分发暂不重构（夜班最小改动），后续白班可让两边共用 execute_tool
  - 全部工具只读；query_fab_data 走 sql guard 白名单（tests/ai/test_sql_guard.py 覆盖）
"""
import logging
from typing import Any, Dict, Optional

from modules.ai_assistant.services.config_store import _get_db
from modules.ai_assistant.services.tools import TOOL_DEFINITIONS, TOOL_HANDLERS

logger = logging.getLogger("fabtwin.ai_tools")

# 与 openai.py 同规则：只有 query_fab_data 的 sql 字段是真实执行的语句
_REAL_SQL_TOOLS = {"query_fab_data"}


def list_tool_metas() -> list:
    """工具元信息列表（给 GET /tools 与 openapi.json 共用）"""
    metas = []
    for t in TOOL_DEFINITIONS:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        if not fn.get("name"):
            continue
        metas.append({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return metas


def get_tool_meta(name: str) -> Optional[Dict[str, Any]]:
    for meta in list_tool_metas():
        if meta["name"] == name:
            return meta
    return None


def execute_tool(name: str, args: Optional[Dict[str, Any]] = None,
                 machine_id: Optional[str] = None) -> Dict[str, Any]:
    """统一分发：与 openai.py Function Calling 同一语义执行单个工具

    Args:
        name: 工具名（TOOL_DEFINITIONS 中的 function.name）
        args: 工具参数（JSON body）
        machine_id: 上下文机台（参数缺省且工具需要时兜底）
    Raises:
        KeyError: 工具不存在
        ValueError: 参数不合法
    """
    args = dict(args or {})
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise KeyError(f"未知工具: {name}")

    # machine_id 兜底（与 openai.py 同规则：工具参数未传时用上下文机台）
    if "machine_id" in args and not args.get("machine_id") and machine_id:
        args["machine_id"] = machine_id

    db = _get_db()
    try:
        result = handler(db, **args)
    finally:
        db.close()

    # sql 诚实化（与 openai.py 同规则）
    if isinstance(result, dict) and result.get("sql") and name not in _REAL_SQL_TOOLS:
        result["sql"] = (
            "-- 参考查询（本次由 ORM 取数，并未执行此语句）\n"
            + str(result["sql"])
        )
    return result if isinstance(result, dict) else {"answer": str(result)}
