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

    # 4. 提取最终输出（优先 Build Success Response / Respond to Webhook）
    print(f"\n[4] 提取最终输出...")
    if isinstance(final_result, dict):
        data = final_result.get("data", {})
        if isinstance(data, dict):
            result_data = data.get("resultData", {})
            run_data = result_data.get("runData", {})
            
            # 优先级：Build Success Response > Respond to Webhook > 最后一个非触发节点
            priority_nodes = ["Build Success Response", "Respond to Webhook", "Respond"]
            skip_nodes = {"Webhook", "Execute Workflow Trigger", "When Executed by Another Workflow", 
                         "Start", "Merge", "IF", "If", "Need Clarification?", "Query Success?", "Normalize Request"}
            
            def extract_output(node_runs):
                """从节点运行数据中提取 json 输出"""
                if not isinstance(node_runs, list) or not node_runs:
                    return None
                last_run = node_runs[-1]
                if not isinstance(last_run, dict):
                    return None
                output_data = last_run.get("data", {}).get("main", [])
                if not isinstance(output_data, list):
                    return None
                for item_list in reversed(output_data):
                    if isinstance(item_list, list) and item_list:
                        for item in item_list:
                            if isinstance(item, dict) and "json" in item:
                                return item["json"]
                return None
            
            # 优先查找
            result = None
            for target in priority_nodes:
                if target in run_data:
                    result = extract_output(run_data[target])
                    if result:
                        print(f"  从 [{target}] 提取到数据")
                        break
            
            # 兜底：找最后一个非跳过节点
            if not result:
                for node_name, node_runs in reversed(run_data.items()):
                    if node_name in skip_nodes:
                        continue
                    result = extract_output(node_runs)
                    if result:
                        print(f"  兜底：从 [{node_name}] 提取到数据")
                        break
            
            if result:
                print(f"\n  ═══ MES 返回数据 ═══")
                # 只打印关键字段
                if isinstance(result, dict):
                    print(f"  lot: {result.get('lot', '?')}")
                    print(f"  product: {result.get('product', '?')}")
                    print(f"  step: {result.get('step', '?')}")
                    print(f"  status: {result.get('lotjobstatus', result.get('status', '?'))}")
                    print(f"  quantity: {result.get('currentquantity', '?')}")
                    print(f"  message: {result.get('message', '?')}")
                    # 如果有 data 字段，提取 rows
                    if "data" in result and isinstance(result["data"], dict):
                        rows = result["data"].get("rows", [])
                        if rows and isinstance(rows, list):
                            print(f"\n  详细数据 (rows[{len(rows)}]):")
                            if rows:
                                row = rows[0]
                                for k in ["lot", "product", "process", "route", "step", 
                                         "lotjobstatus", "currentquantity", "cassette",
                                         "wafertype", "isrework"]:
                                    if k in row:
                                        print(f"    {k}: {row[k]}")
                    # 打印完整 JSON（截断）
                    print(f"\n  完整响应:")
                    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
                else:
                    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
            else:
                print("  ⚠ 未找到输出数据")
                print("  所有节点:", list(run_data.keys()))
                # 打印所有节点的输出结构
                for node_name, node_runs in run_data.items():
                    if isinstance(node_runs, list) and node_runs:
                        last_run = node_runs[-1]
                        if isinstance(last_run, dict):
                            output_data = last_run.get("data", {}).get("main", [])
                            print(f"    {node_name}: main={len(output_data)} items, {sum(len(x) if isinstance(x,list) else 0 for x in output_data)} total outputs")

if __name__ == "__main__":
    main()
