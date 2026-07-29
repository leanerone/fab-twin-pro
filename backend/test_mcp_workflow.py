"""N8N 工作流探测脚本

N8N MCP Server 暴露的是管理 API（search_workflows / execute_workflow），
不是把每个工作流直接暴露为工具。本脚本探测两步调用流程：
  1. search_workflows 搜索 MES_LotInfo_Query
  2. execute_workflow 执行该工作流

使用方法：
    $env:MCP_TOKEN = "your_token"
    python test_mcp_workflow.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.mcp_client import MCPClient, MCPError


def main():
    url = os.environ.get("MCP_URL", "http://10.30.116.137/mcp-server/http")
    token = os.environ.get("MCP_TOKEN", "")

    if not token:
        print("✗ 请先设置 MCP_TOKEN 环境变量")
        sys.exit(1)

    client = MCPClient(url, token, timeout=30)

    print("=" * 60)
    print("N8N 工作流探测")
    print("=" * 60)

    # ── 第1步: 搜索工作流 ──
    print("\n[第1步] search_workflows - 搜索所有工作流...")
    try:
        result = client.call_tool("search_workflows", {})
        print(f"  返回类型: {type(result).__name__}")

        # 打印完整返回结构（截断）
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        if len(result_str) > 3000:
            print(f"  完整返回（截断）:\n{result_str[:3000]}...")
        else:
            print(f"  完整返回:\n{result_str}")

    except MCPError as e:
        print(f"  ✗ 失败: {e}")
        # 尝试带参数搜索
        print("\n  尝试带 query 参数搜索...")
        try:
            result = client.call_tool("search_workflows", {"query": "MES"})
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"  返回:\n{result_str[:3000]}")
        except MCPError as e2:
            print(f"  ✗ 再次失败: {e2}")
        return

    # ── 解析工作流列表 ──
    print("\n[第2步] 解析工作流列表...")
    workflows = []
    if isinstance(result, list):
        workflows = result
    elif isinstance(result, dict):
        # 可能在 data / workflows / items 等字段里
        for key in ["data", "workflows", "items", "results"]:
            if key in result and isinstance(result[key], list):
                workflows = result[key]
                break
        if not workflows:
            # 可能直接就是单个工作流
            if "id" in result and "name" in result:
                workflows = [result]

    if not workflows:
        print("  ⚠ 未能从返回中解析出工作流列表")
        print("  请把上面的完整返回贴给我，我来调整解析逻辑")
        return

    print(f"  找到 {len(workflows)} 个工作流：")
    for wf in workflows:
        wf_id = wf.get("id", "?")
        wf_name = wf.get("name", "?")
        wf_active = wf.get("active", "?")
        print(f"    - id={wf_id}, name={wf_name}, active={wf_active}")

    # ── 第3步: 找 MES_LotInfo_Query ──
    print("\n[第3步] 查找 MES_LotInfo_Query...")
    mes_wf = None
    for wf in workflows:
        name = wf.get("name", "").lower()
        if "lot" in name or "mes" in name:
            mes_wf = wf
            break

    if not mes_wf:
        print("  ⚠ 未找到名称含 lot/mes 的工作流")
        print("  请检查工作流是否已在 N8N 中发布(activate)")
        return

    wf_id = mes_wf.get("id")
    wf_name = mes_wf.get("name")
    print(f"  ✓ 找到: id={wf_id}, name={wf_name}")

    # ── 第4步: 执行工作流 ──
    print(f"\n[第4步] execute_workflow - 执行 {wf_name} (lot=PC00H.29)...")
    try:
        # execute_workflow 可能需要的参数格式：
        # 方式A: {"workflowId": "xxx", "input": {"lot": "PC00H.29"}}
        # 方式B: {"workflowId": "xxx", "data": {"lot": "PC00H.29"}}
        # 先尝试方式A
        exec_result = client.call_tool("execute_workflow", {
            "workflowId": str(wf_id),
            "input": {"lot": "PC00H.29"}
        })
        print(f"  ✓ 执行成功")
        exec_str = json.dumps(exec_result, ensure_ascii=False, indent=2)
        if len(exec_str) > 3000:
            print(f"  返回（截断）:\n{exec_str[:3000]}...")
        else:
            print(f"  返回:\n{exec_str}")

    except MCPError as e:
        print(f"  ✗ 方式A失败: {e}")
        print("  尝试方式B...")
        try:
            exec_result = client.call_tool("execute_workflow", {
                "workflowId": str(wf_id),
                "data": {"lot": "PC00H.29"}
            })
            print(f"  ✓ 执行成功(方式B)")
            exec_str = json.dumps(exec_result, ensure_ascii=False, indent=2)
            print(f"  返回:\n{exec_str[:3000]}")
        except MCPError as e2:
            print(f"  ✗ 方式B也失败: {e2}")
            print("  尝试方式C（直接传参数）...")
            try:
                exec_result = client.call_tool("execute_workflow", {
                    "workflowId": str(wf_id),
                    "lot": "PC00H.29"
                })
                print(f"  ✓ 执行成功(方式C)")
                exec_str = json.dumps(exec_result, ensure_ascii=False, indent=2)
                print(f"  返回:\n{exec_str[:3000]}")
            except MCPError as e3:
                print(f"  ✗ 方式C也失败: {e3}")
                print("  请把错误信息贴给我")

    print("\n" + "=" * 60)
    print("探测完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
