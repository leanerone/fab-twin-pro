# -*- coding: utf-8 -*-
"""docker n8n 工作流重建（本机 5678 docker 实例适配版）

与 tests/ai/n8n_local/n8n_rebuild_workflows.py 的差异：
- 该脚本面向公司 npm 版 n8n（已有工作流 ID），本脚本面向全新 docker 实例（新建）
- npm 版工作流内回访 FabTwin 用 127.0.0.1；docker 容器内 localhost 是容器自己，
  必须用 host.docker.internal:8002
用法：cd backend && python integrations/dify_n8n/n8n_docker_setup.py   （要求后端 8002 在跑以生成 FABTWIN_TOKEN）
"""
import json
import os
import urllib.request
import urllib.error

os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
BASE = "http://localhost:5678"
FABTWIN_INTERNAL = "http://host.docker.internal:8002"

cookie = None


def call(method, path, body=None):
    global cookie
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            sc = r.headers.get("Set-Cookie", "")
            if sc.startswith("n8n-auth="):
                cookie = sc.split(";")[0]
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def main():
    # 1. 取后端 token（注入报警工作流的 HTTP 节点）
    st, r = _login_fabtwin()
    fab_token = r.get("token") if isinstance(r, dict) else None
    print("[OK] FabTwin token 获取", "成功" if fab_token else "失败")

    # 2. n8n 登录
    st, r = call("POST", "/rest/login", {
        "emailOrLdapLoginId": "admin@fabtwin.local",
        "password": "FabTwin#2026!N8n",
    })
    print("[OK] n8n 登录" if st == 200 else f"[FAIL] n8n 登录 {st}: {str(r)[:150]}")

    general_query = {
        "name": "FabTwin 通用查询",
        "nodes": [
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
        ],
        "connections": {"Webhook": {"main": [[{"node": "Build", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
        "active": False,
    }

    alarm_report = {
        "name": "FabTwin 报警报表导出",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": "export_alarm_report",
                            "responseMode": "lastNode", "options": {}},
             "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [-400, 0],
             "webhookId": "fabtwin-export-alarm"},
            {"parameters": {
                "url": f"={FABTWIN_INTERNAL}/api/alarms?machine_id={{ $json.body.machine_id || 'OXE-51' }}",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Authorization", "value": "Bearer " + (fab_token or "")},
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
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Query FabTwin", "type": "main", "index": 0}]]},
            "Query FabTwin": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "active": False,
    }

    for spec in (general_query, alarm_report):
        st, created = call("POST", "/rest/workflows", spec)
        if st != 200:
            print(f"[FAIL] 创建 {spec['name']}: {st} {str(created)[:150]}")
            continue
        wf = created.get("data", created)
        wid, vid = wf["id"], wf.get("versionId", "")
        st2, act = call("POST", f"/rest/workflows/{wid}/activate", {"versionId": vid})
        print(f"[OK] {spec['name']}: id={wid} activate={st2} active={(act.get('data', act) or {}).get('active')}")
    print("[DONE]")


def _login_fabtwin():
    import urllib.request as _u
    req = _u.Request("http://127.0.0.1:8002/api/auth/login-password", method="POST")
    req.add_header("Content-Type", "application/json")
    with _u.urlopen(req, data=json.dumps(
            {"username": "admin", "password": "admin123"}).encode(), timeout=30) as r:
        return 200, json.loads(r.read().decode())


if __name__ == "__main__":
    main()
