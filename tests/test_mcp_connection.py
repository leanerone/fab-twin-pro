"""MCP 连接测试脚本

直接运行此脚本验证 N8N MCP Server 连接是否正常。
使用方法：
    python test_mcp_connection.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.mcp_client import MCPClient, MCPError


def test_connection(url: str, token: str):
    """测试 MCP 连接"""
    print("=" * 60)
    print("FabTwin MCP 连接测试")
    print("=" * 60)
    print(f"URL:    {url}")
    print(f"Token:  {token[:10]}...{token[-4:] if len(token) > 14 else token}" if token else "Token:  (空)")
    print()

    client = MCPClient(url, token, timeout=30)

    # 测试 1: list_tools
    print("[测试 1/3] tools/list - 发现工具...")
    try:
        tools = client.list_tools()
        print(f"  ✓ 成功，发现 {len(tools)} 个工具：")
        for t in tools:
            name = t.get("name", "?")
            desc = t.get("description", "")[:60]
            print(f"    - {name}: {desc}")
        print()
    except MCPError as e:
        print(f"  ✗ 失败: {e}")
        print()
        return False
    except Exception as e:
        print(f"  ✗ 异常: {type(e).__name__}: {e}")
        print()
        return False

    # 测试 2: 找 MES_LotInfo_Query 工具
    print("[测试 2/3] 检查 MES_LotInfo_Query 工具是否存在...")
    mes_tools = [t for t in tools if "lot" in t.get("name", "").lower() or "mes" in t.get("name", "").lower()]
    if mes_tools:
        print(f"  ✓ 找到 {len(mes_tools)} 个 MES 相关工具：")
        for t in mes_tools:
            print(f"    - {t.get('name')}")
            schema = t.get("inputSchema", {})
            props = schema.get("properties", {}) if isinstance(schema, dict) else {}
            print(f"      参数: {list(props.keys())}")
    else:
        print(f"  ⚠ 未找到 MES_LotInfo_Query。可用工具: {[t.get('name') for t in tools]}")
    print()

    # 测试 3: 调用 MES_LotInfo_Query（如果存在）
    if mes_tools:
        tool_name = mes_tools[0].get("name")
        print(f"[测试 3/3] 调用 {tool_name} (lot=PC00H.29)...")
        try:
            result = client.call_tool(tool_name, {"lot": "PC00H.29"})
            print(f"  ✓ 调用成功")
            if isinstance(result, dict):
                success = result.get("success", "?")
                message = result.get("message", "")
                print(f"    success: {success}")
                print(f"    message: {message[:100] if message else '(空)'}")
                if "data" in result:
                    data = result["data"]
                    if isinstance(data, dict):
                        rows = data.get("rows", [])
                        print(f"    rows: {len(rows) if isinstance(rows, list) else '?'}")
                        if rows and isinstance(rows, list):
                            row = rows[0]
                            print(f"    首行关键字段:")
                            for k in ["lot", "product", "step", "lotjobstatus", "currentquantity", "cassette"]:
                                if k in row:
                                    print(f"      {k}: {row[k]}")
            elif isinstance(result, list):
                print(f"    返回数组，长度 {len(result)}")
                if result:
                    print(f"    首项: {str(result[0])[:200]}")
            else:
                print(f"    返回: {str(result)[:200]}")
        except MCPError as e:
            print(f"  ✗ 失败: {e}")
        except Exception as e:
            print(f"  ✗ 异常: {type(e).__name__}: {e}")
    else:
        print("[测试 3/3] 跳过（无 MES 工具）")

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    return True


if __name__ == "__main__":
    url = os.environ.get("MCP_URL", "http://10.30.116.137/mcp-server/http")
    token = os.environ.get("MCP_TOKEN", "")

    if not token:
        print("⚠  未设置 MCP_TOKEN 环境变量")
        print("   请设置后再运行：")
        print("   PowerShell: $env:MCP_TOKEN = 'your_token'")
        print("   CMD: set MCP_TOKEN=your_token")
        print()
        confirm = input("继续用空 Token 测试吗？(y/n): ").strip().lower()
        if confirm != "y":
            sys.exit(0)

    test_connection(url, token)
