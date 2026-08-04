"""MES_ExecuteQuery_Tool 执行测试

直接用已知的 workflowId 测试三种 inputs 格式，
找到正确的调用方式后，后续 get_mes_lot_info 就按这个格式调用。

使用方法：
    $env:MCP_TOKEN = "your_token"
    python test_mcp_execute.py
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

    client = MCPClient(url, token, timeout=60)

    # MES_LotInfo_Query 的 workflowId
    workflow_id = "ymOYQpVMhHr7cWJH"
    lot_id = "PC00H.29"

    print("=" * 60)
    print(f"MES_LotInfo_Query 执行测试")
    print(f"workflowId: {workflow_id}")
    print(f"lot: {lot_id}")
    print("=" * 60)

    # ── 方式1: webhook 类型，body 传 lot ──
    print("\n[方式1] webhook + body...")
    try:
        result = client.call_tool("execute_workflow", {
            "workflowId": workflow_id,
            "inputs": {
                "type": "webhook",
                "webhookData": {
                    "method": "POST",
                    "body": {"lot": lot_id}
                }
            }
        })
        print(f"  ✓ 成功")
        print_result(result)
        return  # 成功就不再尝试其他方式
    except MCPError as e:
        print(f"  ✗ 失败: {e}")

    # ── 方式2: form 类型，formData 传 lot ──
    print("\n[方式2] form + formData...")
    try:
        result = client.call_tool("execute_workflow", {
            "workflowId": workflow_id,
            "inputs": {
                "type": "form",
                "formData": {"lot": lot_id}
            }
        })
        print(f"  ✓ 成功")
        print_result(result)
        return
    except MCPError as e:
        print(f"  ✗ 失败: {e}")

    # ── 方式3: chat 类型，chatInput 传 JSON 字符串 ──
    print("\n[方式3] chat + chatInput...")
    try:
        result = client.call_tool("execute_workflow", {
            "workflowId": workflow_id,
            "inputs": {
                "type": "chat",
                "chatInput": json.dumps({"lot": lot_id})
            }
        })
        print(f"  ✓ 成功")
        print_result(result)
        return
    except MCPError as e:
        print(f"  ✗ 失败: {e}")

    # ── 方式4: 不传 inputs，看看工作流是否有默认触发 ──
    print("\n[方式4] 不传 inputs...")
    try:
        result = client.call_tool("execute_workflow", {
            "workflowId": workflow_id
        })
        print(f"  ✓ 成功")
        print_result(result)
        return
    except MCPError as e:
        print(f"  ✗ 失败: {e}")

    # ── 方式5: webhook + query ──
    print("\n[方式5] webhook + query...")
    try:
        result = client.call_tool("execute_workflow", {
            "workflowId": workflow_id,
            "inputs": {
                "type": "webhook",
                "webhookData": {
                    "method": "GET",
                    "query": {"lot": lot_id}
                }
            }
        })
        print(f"  ✓ 成功")
        print_result(result)
        return
    except MCPError as e:
        print(f"  ✗ 失败: {e}")

    print("\n" + "=" * 60)
    print("所有方式都失败了。请把以上错误信息贴给我。")
    print("也可能是工作流需要先 publish（activate）。")
    print("=" * 60)


def print_result(result):
    """打印执行结果"""
    result_str = json.dumps(result, ensure_ascii=False, indent=2)
    if len(result_str) > 4000:
        print(f"  返回（截断）:\n{result_str[:4000]}...")
    else:
        print(f"  返回:\n{result_str}")

    # 尝试提取关键字段
    if isinstance(result, dict):
        print(f"\n  关键字段:")
        for k in ["executionId", "data", "success", "message", "lot", "product", "step"]:
            if k in result:
                val = result[k]
                if isinstance(val, (dict, list)):
                    print(f"    {k}: {json.dumps(val, ensure_ascii=False)[:200]}")
                else:
                    print(f"    {k}: {val}")
    elif isinstance(result, list):
        print(f"\n  返回数组，长度 {len(result)}")
        if result:
            print(f"  首项关键字段:")
            first = result[0]
            if isinstance(first, dict):
                for k in ["success", "lot", "message", "product", "step", "lotjobstatus"]:
                    if k in first:
                        print(f"    {k}: {first[k]}")

    print("\n" + "=" * 60)
    print("测试完成 - 此方式可用！")
    print("=" * 60)


if __name__ == "__main__":
    main()
