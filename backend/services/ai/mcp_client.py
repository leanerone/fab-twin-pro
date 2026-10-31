"""MCP (Model Context Protocol) 轻量 HTTP 客户端

用于调用 N8N MCP Server 暴露的工具（如 MES_LotInfo_Query）。

协议：JSON-RPC 2.0 over HTTP
传输：单向 HTTP POST（每次请求一个 JSON-RPC 消息）

核心方法：
  - list_tools(): 发现 MCP Server 上的工具
  - call_tool(name, arguments): 调用指定工具

配置来源：ai_configs 表的 mcp_n8n_* 键
"""
import json
import time
import logging
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fabtwin.mcp")


class MCPError(Exception):
    """MCP 调用异常基类"""


class MCPClient:
    """轻量 MCP HTTP/SSE 客户端

    不依赖官方 mcp SDK，仅用 requests 实现 JSON-RPC 2.0 调用。
    支持 SSE 响应格式（N8N MCP Server 使用）和纯 JSON 响应格式。
    """

    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = (base_url or "").rstrip('/')
        self.token = token or ""
        self.timeout = timeout or 30
        self._initialized = False
        self._server_info = None
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    def _ensure_initialized(self):
        """确保已完成 MCP initialize 握手

        N8N MCP Server 可能不支持 initialize 方法，
        失败后标记为已初始化，不阻止后续 tools/list 和 tools/call。
        """
        if not self._initialized:
            self._initialize()
            # 无论 initialize 成功还是失败，都标记为已初始化
            # 避免后续每次调用都重复尝试 initialize
            self._initialized = True

    def _initialize(self):
        """执行 MCP initialize 握手（可选）"""
        try:
            result = self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "clientInfo": {
                    "name": "fabtwin-mcp-client",
                    "version": "1.0.0",
                },
            })
            self._server_info = result
            logger.info("[MCP] initialize 成功: %s", result.get("serverInfo", {}))
        except Exception as e:
            logger.warning("[MCP] initialize 跳过（N8N MCP 可能不支持）: %s", e)

    def _request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 JSON-RPC 2.0 请求

        Args:
            method: MCP 方法名（tools/list, tools/call）
            params: 方法参数

        Returns:
            JSON-RPC result 字段

        Raises:
            MCPError: 调用失败
        """
        if not self.base_url:
            raise MCPError("MCP Server URL 未配置")

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1000000000,
            "method": method,
        }
        if params:
            payload["params"] = params

        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                headers=self._headers,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            raise MCPError(f"MCP 请求超时（{self.timeout}s）: {self.base_url}")
        except requests.exceptions.ConnectionError as e:
            raise MCPError(f"MCP 连接失败: {e}")
        except requests.exceptions.RequestException as e:
            raise MCPError(f"MCP 请求异常: {e}")

        if resp.status_code != 200:
            raise MCPError(f"MCP HTTP {resp.status_code}: {resp.text[:300]}")

        text = self._parse_sse_or_json(resp.text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise MCPError(f"MCP 响应非 JSON: {text[:300]}")

        if "error" in data and data["error"]:
            err = data["error"]
            raise MCPError(f"MCP 错误 [{err.get('code')}]: {err.get('message', '')}")

        return data.get("result", {})

    def _parse_sse_or_json(self, raw_text: str) -> str:
        """解析 MCP 响应，支持纯 JSON 和 SSE 两种格式

        N8N MCP Server 返回 SSE 格式（event: message + data: {...}），
        而部分 MCP Server 返回纯 JSON。本方法统一解析为 JSON 字符串。

        SSE 格式示例：
            event: message
            data: {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

        Args:
            raw_text: 原始响应文本

        Returns:
            JSON 字符串
        """
        text = raw_text.strip()
        if not text:
            return "{}"

        lines = text.splitlines()

        data_lines = []
        in_data = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                in_data = False
                continue
            if stripped.startswith("data:"):
                data_lines.append(stripped[5:].strip())
                in_data = True
            elif stripped.startswith("event:"):
                in_data = False
                continue
            elif stripped.startswith("id:"):
                in_data = False
                continue
            elif in_data:
                data_lines.append(stripped)

        if data_lines:
            return "".join(data_lines)

        return text

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出 MCP Server 注册的所有工具

        Returns:
            工具列表，每项含 name/description/inputSchema
        """
        self._ensure_initialized()
        result = self._request("tools/list")
        tools = result.get("tools", []) if isinstance(result, dict) else []
        logger.info("[MCP] 发现 %d 个工具: %s", len(tools), [t.get("name") for t in tools])
        return tools

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """调用 MCP 工具

        Args:
            name: MCP 工具名（如 MES_LotInfo_Query）
            arguments: 工具参数

        Returns:
            工具返回值（已自动解析 content[0].text 为 JSON）
        """
        self._ensure_initialized()
        params: Dict[str, Any] = {"name": name}
        # 即使 arguments 是空字典 {}，也要传给 MCP Server
        # 因为部分工具（如 search_workflows）要求 arguments 字段必须存在
        if arguments is not None:
            params["arguments"] = arguments
        else:
            params["arguments"] = {}

        result = self._request("tools/call", params)

        # 检测 MCP 错误响应（isError 标志）
        if isinstance(result, dict) and result.get("isError"):
            content = result.get("content", [])
            err_text = ""
            if content and isinstance(content, list) and isinstance(content[0], dict):
                err_text = content[0].get("text", "")
            raise MCPError(f"MCP 工具调用错误: {err_text or result}")

        # MCP 标准响应：content 数组，每项 {type, text}
        content = result.get("content", []) if isinstance(result, dict) else []
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text", "")
                # 检测文本中的 MCP error
                if text.startswith("MCP error"):
                    raise MCPError(text[:500])
                # 尝试解析为 JSON
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
            return first

        # 部分实现直接返回结果
        return result

    def ping(self) -> bool:
        """快速连通性测试

        Returns:
            True 表示可连接
        """
        try:
            self.list_tools()
            return True
        except Exception as e:
            logger.warning("[MCP] ping 失败: %s", e)
            return False


# ==================== 配置加载工具 ====================

def _get_db():
    """获取数据库 Session"""
    from database import SessionLocal
    return SessionLocal()


def get_mcp_config() -> Dict[str, Any]:
    """从 ai_configs 表读取 MCP 配置

    Returns:
        {
            "enabled": bool,
            "url": str,
            "token": str,
            "timeout": int,
        }
    """
    defaults = {
        "mcp_n8n_enabled": "false",
        "mcp_n8n_url": "",
        "mcp_n8n_token": "",
        "mcp_n8n_timeout": "30",
    }
    try:
        db = _get_db()
        try:
            from models import AIConfig
            rows = db.query(AIConfig).filter(
                AIConfig.config_key.in_(list(defaults.keys()))
            ).all()
            for r in rows:
                defaults[r.config_key] = r.config_value or defaults[r.config_key]
        finally:
            db.close()
    except Exception as e:
        logger.warning("[MCP] 读取配置失败，使用默认值: %s", e)

    return {
        "enabled": str(defaults["mcp_n8n_enabled"]).lower() == "true",
        "url": defaults["mcp_n8n_url"],
        "token": defaults["mcp_n8n_token"],
        "timeout": int(defaults["mcp_n8n_timeout"] or 30),
    }


def get_mcp_client() -> Optional[MCPClient]:
    """获取已配置的 MCP 客户端实例

    Returns:
        MCPClient 或 None（未配置/未启用时）
    """
    cfg = get_mcp_config()
    if not cfg["enabled"]:
        return None
    if not cfg["url"]:
        return None
    return MCPClient(cfg["url"], cfg["token"], cfg["timeout"])
