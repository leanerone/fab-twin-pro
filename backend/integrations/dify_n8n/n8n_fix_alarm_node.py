# -*- coding: utf-8 -*-
"""修复 docker n8n 报警工作流的 Build Report 节点：
HTTP Request 节点会把 JSON 数组响应拆成多个 item，必须用 $input.all() 聚合
（tests/ai/n8n_local/README.md 已知坑第四条）。
"""
import json
import os
import sys
import urllib.request
import urllib.error

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BACKEND_DIR)
from config import BASE_DIR

os.environ["no_proxy"] = "localhost,127.0.0.1"
BASE = "http://localhost:5678"
WF_ID = "YUnrcU5cGALZZ9pm"
TMP_COOKIE = os.path.join(BASE_DIR, ".n8n_cookie")

cookie = ""
if os.path.exists(TMP_COOKIE):
    cookie = open(TMP_COOKIE, encoding="utf-8").read().strip()


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
                open(TMP_COOKIE, "w", encoding="utf-8").write(cookie)
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def main():
    st, d = call("POST", "/rest/login", {
        "emailOrLdapLoginId": "admin@fabtwin.local",
        "password": "FabTwin#2026!N8n",
    })
    assert st == 200, f"登录失败 {st}: {str(d)[:150]}"

    st, d = call("GET", f"/api/v1/workflows/{WF_ID}")
    assert st == 200, f"取工作流失败 {st}: {str(d)[:200]}"
    wf = d.get("data", d)
    print("[OK] 取工作流, nodes =", len(wf.get("nodes", [])))

    for n in wf["nodes"]:
        if n["name"] == "Query FabTwin":
            # 修正表达式：必须双花括号（此前误写单花括号成字面量）
            n["parameters"]["url"] = (
                "=http://host.docker.internal:8002/api/alarms"
                "?machine_id={{ $json.body.machine_id || 'OXE-51' }}"
            )
        if n["name"] == "Build Report":
            n["parameters"]["jsCode"] = (
                "const items = $input.all().map(i => i.json);\n"
                "let list = [];\n"
                "if (items.length && items[0].id && items[0].alarm_code !== undefined) {\n"
                "  list = items;\n"
                "} else {\n"
                "  const resp = items[0] || {};\n"
                "  list = Array.isArray(resp) ? resp : (resp.alarms || resp.data || []);\n"
                "}\n"
                "return [{ json: {\n"
                "  answer: '报警报表导出完成：共 ' + list.length + ' 条告警（来源：FabTwin API 实时查询）',\n"
                "  data: list.slice(0, 10),\n"
                "  executionId: $execution.id,\n"
                "}}];"
            )

    body = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {"executionOrder": "v1"},
    }
    st, updated = call("PUT", f"/api/v1/workflows/{WF_ID}", body)
    assert st == 200, f"更新失败 {st}: {str(updated)[:200]}"
    wfu = updated.get("data", updated)
    st2, act = call("POST", f"/api/v1/workflows/{wfu['id']}/activate",
                    {"versionId": wfu.get("versionId", "")})
    print(f"[OK] 节点已修复并激活: {st2} active={(act.get('data', act) or {}).get('active')}")


if __name__ == "__main__":
    main()
