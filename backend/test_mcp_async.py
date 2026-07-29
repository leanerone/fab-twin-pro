"""完整 MES_LotInfo_Query 异步调用流程测试（含 includeData）

步骤：
1. execute_workflow 发起执行，拿到 executionId
2. get_execution(includeData=true) 获取完整输出
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.mcp_client import MCPClient, MCPError

def main():
    url = os.environ.get("MCP_URL", "http://10.30.116.137/mcp-server/http")
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        print("请设置 MCP_TOKEN")
        sys.exit(1)

    client = MCPClient(url, token, timeout=60)
    workflow_id = "ymOYQpVMhHr7cWJH"
    lot_id = "PC00H.29"

    print("=" * 60)
    print(f"MES_LotInfo_Query 完整异步流程")
    print(f"workflowId: {workflow_id}")
    print(f"lot: {lot_id}")
    print("=" * 60)

    # 1. 发起执行
    print("\n[1] execute_workflow (发起执行)...")
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
        print(f"  返回: {json.dumps(result, ensure_ascii=False)}")
    except MCPError as e:
        print(f"  ✗ 失败: {e}")
        return

    execution_id = result.get("executionId")
    if not execution_id:
        print("  ✗ 未拿到 executionId")
        return

    print(f"  executionId: {execution_id}")

    # 2. 轮询执行结果（带 includeData=true）
    print(f"\n[2] get_execution (includeData=true, 轮询最多 10 秒)...")
    final_result = None
    for i in range(5):
        time.sleep(2)
        try:
            exec_result = client.call_tool("get_execution", {
                "executionId": str(execution_id),
                "workflowId": workflow_id,
                "includeData": True
            })
            status = exec_result.get("status", "?")
            print(f"  [{i+1}] status={status}")

            if status in ("success", "finished", "completed"):
                final_result = exec_result
                break
            elif status in ("error", "failed", "crashed"):
                print(f"  ✗ 执行失败: {json.dumps(exec_result, ensure_ascii=False)[:500]}")
                return
        except MCPError as e:
            print(f"  [{i+1}] 错误: {e}")

    if not final_result:
        # 再查一次
        print("\n[3] 再查一次，打印完整响应...")
        try:
            exec_result = client.call_tool("get_execution", {
                "executionId": str(execution_id),
                "workflowId": workflow_id,
                "includeData": True
            })
            print(f"  完整响应:\n{json.dumps(exec_result, ensure_ascii=False, indent=2)[:4000]}")
            return
        except MCPError as e:
            print(f"  ✗ 失败: {e}")
            return

    # 3. 打印最终结果
    print(f"\n{'='*60}")
    print("执行成功！最终结果：")
    print(f"{'='*60}")
    result_str = json.dumps(final_result, ensure_ascii=False, indent=2)
    if len(result_str) > 4000:
        print(result_str[:4000])
    else:
        print(result_str)

    # 4. 提取 N8N 输出数据
    print(f"\n[4] 提取 N8N 输出数据...")
    if isinstance(final_result, dict):
        # N8N 执行数据通常在 data.resultData.runData 或 data.resultData 里
        data = final_result.get("data", {})
        if isinstance(data, dict):
            result_data = data.get("resultData", {})
            run_data = result_data.get("runData", {})
            
            print(f"  resultData keys: {list(result_data.keys())}")
            
            # 找最后一个节点的输出
            for node_name, node_runs in run_data.items():
                if node_name in ("Webhook", "Execute Workflow Trigger", "When Executed by Another Workflow"):
                    continue
                if isinstance(node_runs, list) and node_runs:
                    last_run = node_runs[-1]
                    if isinstance(last_run, dict):
                        output_data = last_run.get("data", {}).get("main", [])
                        if output_data and isinstance(output_data, list):
                            for item_list in output_data:
                                if isinstance(item_list, list) and item_list:
                                    for item in item_list:
                                        if isinstance(item, dict) and "json" in item:
                                            json_data = item["json"]
                                            print(f"\n  节点 [{node_name}] 输出:")
                                            print(json.dumps(json_data, ensure_ascii=False, indent=2)[:2000])

if __name__ == "__main__":
    main()
