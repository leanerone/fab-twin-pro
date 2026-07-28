"""MCP 工具注册表：定义 AI 可调用的 MCP 工具元信息

每个注册项包含：
  - name: AI 工具名（给 LLM Function Calling 用）
  - description: 工具描述（决定 LLM 是否调用）
  - mcp_tool_name: N8N MCP Server 上的实际工具名
  - parameters: OpenAI Function Calling 参数 schema
  - keywords: 关键词兜底路由

新增 N8N 工具时，只需在此处追加一条注册项即可。
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MCPToolConfig:
    """单个 MCP 工具的注册信息"""
    name: str  # AI 工具名（给 GPT-4o 看）
    description: str  # 自然语言描述（决定 GPT-4o 是否调用）
    mcp_tool_name: str  # N8N MCP Server 上的实际工具名
    parameters: Dict  # OpenAI Function Calling 参数 schema
    keywords: List[str] = field(default_factory=list)  # 关键词兜底


# ==================== 工具注册表 ====================

MCP_REGISTRY: Dict[str, MCPToolConfig] = {
    "get_mes_lot_info": MCPToolConfig(
        name="get_mes_lot_info",
        description=(
            "查询 MES 系统中的 Lot 详细信息。"
            "返回字段包括：product（产品型号）、process（工艺）、route（路线）、"
            "step（当前步骤）、lotjobstatus（状态：RUN/HOLD/COMPLETE）、"
            "currentquantity（晶圆数量）、cassette（花篮号）、wafertype（晶圆类型）。"
            "适用场景：用户提到具体 Lot ID（如 PC00H.29、NT938、VC001）"
            "并询问产品、状态、步骤、数量、工艺信息时，必须调用此工具。"
        ),
        mcp_tool_name="MES_LotInfo_Query",
        parameters={
            "type": "object",
            "properties": {
                "lot": {
                    "type": "string",
                    "description": "Lot ID，如 PC00H.29、NT938、NT938.15、VC001"
                }
            },
            "required": ["lot"]
        },
        keywords=["lot", "批次", "产品", "工艺", "状态", "晶圆", "花篮", "控片", "追溯"],
    ),
    # 后续新增工具只需在此追加，例如：
    # "get_mes_alarm_info": MCPToolConfig(
    #     name="get_mes_alarm_info",
    #     description="查询 MES 系统中的报警记录",
    #     mcp_tool_name="MES_AlarmQuery",
    #     parameters={...},
    #     keywords=["报警", "告警", "alarm"],
    # ),
}


def get_mcp_tool_definitions() -> List[Dict]:
    """生成 OpenAI Function Calling 的 tools 定义列表

    Returns:
        tools 数组，可直接注入 LLM 请求的 payload["tools"]
    """
    definitions = []
    for cfg in MCP_REGISTRY.values():
        definitions.append({
            "type": "function",
            "function": {
                "name": cfg.name,
                "description": cfg.description,
                "parameters": cfg.parameters,
            }
        })
    return definitions


def find_mcp_tool_by_name(name: str) -> MCPToolConfig:
    """按 AI 工具名查找注册项"""
    return MCP_REGISTRY.get(name)


def find_mcp_tool_by_keyword(question: str) -> MCPToolConfig:
    """按关键词匹配查找工具（兜底路由）

    Args:
        question: 用户问题（已转小写）

    Returns:
        匹配度最高的工具，或 None
    """
    q = (question or "").lower()
    best_match = None
    best_score = 0

    for cfg in MCP_REGISTRY.values():
        score = sum(1 for kw in cfg.keywords if kw.lower() in q)
        if score > best_score:
            best_score = score
            best_match = cfg

    return best_match if best_score > 0 else None


def list_registered_mcp_tools() -> List[Dict]:
    """列出所有已注册的 MCP 工具（供 UI 展示）"""
    return [{
        "name": cfg.name,
        "description": cfg.description,
        "mcp_tool_name": cfg.mcp_tool_name,
        "parameters": cfg.parameters,
        "keywords": cfg.keywords,
    } for cfg in MCP_REGISTRY.values()]
