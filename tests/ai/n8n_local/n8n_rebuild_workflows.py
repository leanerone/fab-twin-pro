# -*- coding: utf-8 -*-
"""重建 n8n 工作流为 lastNode 响应模式（修复空响应问题）。"""
import json
import os
import urllib.request

os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
BASE = "http://localhost:5678"
WFS = {
    "zNDim7ruktS7yDNe": "general_query",
    "zInzpTwtDk3n226f": "export_alarm_report",
}


def call(method, path, body=None, cookie=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        set_cookie = r.headers.get("Set-Cookie", "")
        cookie_line = set_cookie.split(";")[0] if set_cookie else cookie
        return json.loads(r.read().decode()), cookie_line


# 登录
_, cookie = call("POST", "/rest/login", {
    "emailOrLdapLoginId": "admin@fabtwin.local",
    "password": "FabTwin#2026!N8n",
})
print("[OK] 登录")

for wf_id, wf_type in WFS.items():
    raw, _ = call("GET", f"/rest/workflows/{wf_id}")
    wf = raw.get("data", raw)

    if wf_type == "general_query":
        nodes = [
            {"parameters": {"httpMethod": "POST", "path": "general_query",
                            "responseMode": "lastNode", "options": {}},
             "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [-200, 0],
             "webhookId": "fabtwin-general-query"},
            {"parameters": {"jsCode": (
                "const body = $input.first().json.body || {};\n"
                "return [{ json: {\n"
                "  answer: 'N8N 工作流执行正常。收到问题：' + (body.question || ''),\n"
                "  workflow: 'general_query',\n"
                "  executionId: $execution.id,\n"
                "}}];")},
             "name": "Build", "type": "n8n-nodes-base.code",
             "typeVersion": 2, "position": [100, 0]},
        ]
        connections = {"Webhook": {"main": [[{"node": "Build", "type": "main", "index": 0}]]}}
    else:
        nodes = [
            {"parameters": {"httpMethod": "POST", "path": "export_alarm_report",
                            "responseMode": "lastNode", "options": {}},
             "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [-400, 0],
             "webhookId": "fabtwin-export-alarm"},
            {"parameters": {
                "url": "=http://localhost:8002/api/alarms?machine_id={{ $json.body.machine_id || 'OXE-51' }}",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Authorization", "value": "Bearer " + os.environ.get("FABTWIN_TOKEN", "")},
                ]},
                "options": {}},
             "name": "Query FabTwin", "type": "n8n-nodes-base.httpRequest",
             "typeVersion": 4.2, "position": [-100, 0]},
            {"parameters": {"jsCode": (
                "const resp = $input.first().json;\n"
                "const list = Array.isArray(resp) ? resp : (resp.alarms || resp.data || []);\n"
                "return [{ json: {\n"
                "  answer: '报警报表导出完成：共 ' + list.length + ' 条告警（来源：FabTwin API 实时查询）',\n"
                "  data: list.slice(0, 10),\n"
                "  executionId: $execution.id,\n"
                "}}];")},
             "name": "Build Report", "type": "n8n-nodes-base.code",
             "typeVersion": 2, "position": [200, 0]},
        ]
        connections = {
            "Webhook": {"main": [[{"node": "Query FabTwin", "type": "main", "index": 0}]]},
            "Query FabTwin": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        }

    body = {
        "name": wf.get("name"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings") or {"executionOrder": "v1"},
        "active": False,
    }
    updated, _ = call("PUT", f"/rest/workflows/{wf_id}", body, cookie)
    new_id = (updated.get("data", updated) or {}).get("id", wf_id)
    vid = (updated.get("data", updated) or {}).get("versionId", "")
    act, _ = call("POST", f"/rest/workflows/{new_id}/activate", {"versionId": vid}, cookie)
    active = (act.get("data", act) or {}).get("active")
    print(f"[OK] {wf_type}: id={new_id} active={active}")

print("[DONE] 重建完成")
