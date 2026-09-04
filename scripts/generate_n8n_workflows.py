# -*- coding: utf-8 -*-
"""
生成 FabTwin n8n 工作流 JSON 模板（DB Proxy 版）
架构: Webhook → HTTP Request(db_proxy) → Respond
n8n 不直连 Oracle，通过 DB Proxy 服务中转。

用法: python scripts/generate_n8n_workflows.py
产物: docs/integration/n8n/F1~F10*.json
"""
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs", "integration", "n8n"))
os.makedirs(OUT_DIR, exist_ok=True)

DB_PROXY_URL = "http://10.30.116.150:8001"
DB_PROXY_KEY = "fabtwin-proxy-2026"

def _node(name, node_type, params, position, type_version, extra=None):
    n = {
        "parameters": params,
        "name": name,
        "type": node_type,
        "typeVersion": type_version,
        "position": position,
    }
    if extra:
        n.update(extra)
    return n

def webhook_node(path):
    return _node(
        "Webhook", "n8n-nodes-base.webhook",
        {"httpMethod": "POST", "path": path, "responseMode": "responseNode", "options": {}},
        [240, 300], 2,
        extra={"webhookId": path + "-wh-id"},
    )

def http_request_node(endpoint, body_template):
    return _node(
        "Query DB Proxy", "n8n-nodes-base.httpRequest",
        {
            "method": "POST",
            "url": f"{DB_PROXY_URL}/query/{endpoint}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "X-API-Key", "value": DB_PROXY_KEY},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body_template,
            "options": {"timeout": 30000},
        },
        [480, 300], 4,
    )

def respond_node():
    return _node(
        "Respond", "n8n-nodes-base.respondToWebhook",
        {"responseCode": 200, "responseBody": "={{ JSON.stringify($json) }}", "options": {}},
        [720, 300], 1,
    )

def make_workflow(name, title, webhook_path, endpoint, body_template):
    nodes = [webhook_node(webhook_path), http_request_node(endpoint, body_template), respond_node()]
    conns = {
        "Webhook": {"main": [[{"node": "Query DB Proxy", "type": "main", "index": 0}]]},
        "Query DB Proxy": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return name, title, nodes, conns

def save(name, title, nodes, conns):
    payload = {
        "name": title,
        "nodes": nodes,
        "pinData": {},
        "connections": conns,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": str(uuid.uuid4()),
        "meta": {"templateCredsSetupCompleted": True, "instanceId": "fabtwin-local"},
        "id": str(uuid.uuid4()),
        "tags": [],
    }
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {name}  ({len(payload['nodes'])} nodes)")

def main():
    print("生成 n8n 工作流模板（DB Proxy 版）...")

    workflows = [
        # (filename, title, webhook_path, endpoint, body_template)
        ("F1_get_machine_status.json", "F1 机台状态", "get_machine_status", "machine_status",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "" }) }}'),
        ("F2_get_lot_info.json", "F2 Lot信息", "get_lot_info", "lot_info",
         '={{ JSON.stringify({ lot_id: $json.body.lot_id || "", machine_id: $json.body.machine_id || "" }) }}'),
        ("F3_get_machine_alarms.json", "F3 报警统计", "get_machine_alarms", "machine_alarms",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "", severity: $json.body.severity || "", days: $json.body.days || 7 }) }}'),
        ("F4_get_event_timeline.json", "F4 事件时间线", "get_event_timeline", "event_timeline",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "", time_range: $json.body.time_range || "today" }) }}'),
        ("F5_get_yield_stats.json", "F5 产量统计", "get_yield_stats", "yield_stats",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "", time_range: $json.body.time_range || "today" }) }}'),
        ("F6_get_recipe_info.json", "F6 工艺配方", "get_recipe_info", "recipe_info",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "" }) }}'),
        ("F7_get_mes_lot_info.json", "F7 MES Lot详情", "get_mes_lot_info", "mes_lot_info",
         '={{ JSON.stringify({ lot_id: $json.body.lot_id || "" }) }}'),
        ("F8_export_alarm_report.json", "F8 导出报警报表", "export_alarm_report", "export_alarm_report",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "", days: $json.body.days || 7 }) }}'),
        ("F9_generate_work_order.json", "F9 生成故障工单", "generate_work_order", "generate_work_order",
         '={{ JSON.stringify({ machine_id: $json.body.machine_id || "", fault_type: $json.body.fault_type || "", severity: $json.body.severity || "medium" }) }}'),
        ("F10_list_capabilities.json", "F10 功能清单", "list_capabilities", "list_capabilities",
         '={{ JSON.stringify({}) }}'),
    ]

    for filename, title, wh_path, endpoint, body in workflows:
        name, t, nodes, conns = make_workflow(filename, title, wh_path, endpoint, body)
        save(name, t, nodes, conns)

    print(f"\n[DONE] 10 个工作流生成到 {OUT_DIR}")
    print(f"  DB Proxy: {DB_PROXY_URL}")
    print(f"  节点结构: Webhook → HTTP Request(DB Proxy) → Respond (3节点2连接)")

if __name__ == "__main__":
    main()
