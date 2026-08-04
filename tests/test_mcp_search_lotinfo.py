"""精确搜索 MES_LotInfo_Query 工作流

排查为什么 search_workflows 没返回 MES_LotInfo_Query。
尝试跨项目搜索，并用 get_workflow_details 查看详情。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.mcp_client import MCPClient, MCPError

def main():
    url = os.environ.get("MCP_URL", "http://10.30.116.137/mcp-server/http")
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        print("请设置 MCP_TOKEN")
        sys.exit(1)

    client = MCPClient(url, token, timeout=30)

    # 1. 先列出所有项目
    print("[1] search_projects - 列出所有项目...")
    try:
        projects = client.call_tool("search_projects", {})
        print(json.dumps(projects, ensure_ascii=False, indent=2)[:1500])
    except MCPError as e:
        print(f"  失败: {e}")

    # 2. 尝试用 query 参数精确搜索 LotInfo
    print("\n[2] search_workflows (query='LotInfo')...")
    try:
        result = client.call_tool("search_workflows", {"query": "LotInfo", "limit": 50})
        workflows = result.get("data", []) if isinstance(result, dict) else []
        if not workflows and isinstance(result, list):
            workflows = result
        print(f"  找到 {len(workflows)} 个工作流：")
        for wf in workflows:
            print(f"    id={wf.get('id')}, name={wf.get('name')}, active={wf.get('active')}, availableInMCP={wf.get('availableInMCP')}")
    except MCPError as e:
        print(f"  失败: {e}")

    # 3. 尝试用 query 参数搜 MES
    print("\n[3] search_workflows (query='MES_')...")
    try:
        result = client.call_tool("search_workflows", {"query": "MES_", "limit": 100})
        workflows = result.get("data", []) if isinstance(result, dict) else []
        print(f"  找到 {len(workflows)} 个工作流：")
        for wf in workflows:
            print(f"    id={wf.get('id')}, name={wf.get('name')}, active={wf.get('active')}, availableInMCP={wf.get('availableInMCP')}")
    except MCPError as e:
        print(f"  失败: {e}")

    # 4. 如果还是找不到，直接列出全部工作流（不带 query，limit=200）
    print("\n[4] search_workflows (全部, limit=200)...")
    try:
        result = client.call_tool("search_workflows", {"limit": 200})
        workflows = result.get("data", []) if isinstance(result, dict) else []
        print(f"  共 {len(workflows)} 个工作流")
        # 只找名字含 Lot 的
        lot_wfs = [w for w in workflows if "lot" in w.get("name", "").lower()]
        print(f"  含 'lot' 的: {len(lot_wfs)} 个")
        for wf in lot_wfs:
            print(f"    id={wf.get('id')}, name={wf.get('name')}, active={wf.get('active')}, availableInMCP={wf.get('availableInMCP')}")
        
        # 如果还是没有，打印所有的 MES 开头的
        mes_wfs = [w for w in workflows if w.get("name", "").lower().startswith("mes")]
        print(f"\n  MES 开头的: {len(mes_wfs)} 个")
        for wf in mes_wfs:
            print(f"    id={wf.get('id')}, name={wf.get('name')}, active={wf.get('active')}, availableInMCP={wf.get('availableInMCP')}")
    except MCPError as e:
        print(f"  失败: {e}")

if __name__ == "__main__":
    main()
