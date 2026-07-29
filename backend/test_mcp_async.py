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
    print(f"\n[2] get_execution (includeData=true, 最多 5 次)...")
    final_result = None
    for i in range(5):
        time.sleep(2)
        try:
            exec_result = client.call_tool("get_execution", {
                "executionId": str(execution_id),
                "workflowId": workflow_id,
                "includeData": True
            })
            status = exec_result.get("execution", {}).get("status", "?")
            print(f"  [{i+1}] status={status}")

            if status in ("success", "finished", "completed"):
                final_result = exec_result
                break
            elif status in ("error", "failed", "crashed"):
                print(f"  ✗ 执行失败: {status}")
                return
        except MCPError as e:
            print(f"  [{i+1}] 错误: {e}")

    if not final_result:
        print("  ⚠ 超时或状态未变，继续尝试...")
        final_result = exec_result  # 用最后一次的结果

    # 3. 打印最终结果统计
    print(f"\n{'='*60}")
    print(f"执行成功！状态: {final_result.get('execution', {}).get('status', '?')}")
    print(f"耗时: {final_result.get('execution', {}).get('startedAt', '?')} ~ {final_result.get('execution', {}).get('stoppedAt', '?')}")
    
    # 统计节点
    data = final_result.get("data", {})
    if isinstance(data, dict):
        result_data = data.get("resultData", {})
        run_data = result_data.get("runData", {})
        print(f"节点数: {len(run_data)}")
        for node_name, node_runs in run_data.items():
            run_count = len(node_runs) if isinstance(node_runs, list) else 0
            exec_time = sum(r.get("executionTime", 0) for r in node_runs) if isinstance(node_runs, list) else 0
            status = "success"
            if isinstance(node_runs, list) and node_runs:
                status = node_runs[-1].get("executionStatus", "?")
            print(f"  - {node_name}: {run_count}次, {exec_time}ms, {status}")

    # 4. 提取最后一个节点的最终输出
    print(f"\n[4] 提取最终输出（最后一个节点）...")
    if isinstance(final_result, dict):
        data = final_result.get("data", {})
        if isinstance(data, dict):
            result_data = data.get("resultData", {})
            run_data = result_data.get("runData", {})
            
            # 找到最后一个有输出的节点（排除触发节点）
            skip_nodes = {"Webhook", "Execute Workflow Trigger", "When Executed by Another Workflow", "Start", "Merge", "IF", "If"}
            last_node_output = None
            last_node_name = ""
            
            for node_name, node_runs in run_data.items():
                if node_name in skip_nodes:
                    continue
                if isinstance(node_runs, list) and node_runs:
                    last_run = node_runs[-1]
                    if isinstance(last_run, dict):
                        output_data = last_run.get("data", {}).get("main", [])
                        if output_data and isinstance(output_data, list):
                            # 取最后一个输出项
                            for item_list in reversed(output_data):
                                if isinstance(item_list, list) and item_list:
                                    for item in item_list:
                                        if isinstance(item, dict) and "json" in item:
                                            last_node_output = item["json"]
                                            last_node_name = node_name
                                            break
                                    if last_node_output:
                                        break
                            if last_node_output:
                                break
            
            if last_node_output:
                print(f"  最终输出来自节点: [{last_node_name}]")
                print(f"\n  最终数据:")
                print(json.dumps(last_node_output, ensure_ascii=False, indent=2)[:3000])
            else:
                print("  ⚠ 未找到最终输出节点")
                print("  可用节点:", list(run_data.keys()))

if __name__ == "__main__":
    main()
