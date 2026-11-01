# -*- coding: utf-8 -*-
"""Dify 0.10.3 自动初始化：管理员注册 → 登录 → 建应用 → 生成 API Key。
用法：python dify_init.py   （Dify API 需已在 http://localhost:8088 运行）
输出：打印 API Key 并写入 E:/AI/fab-ai-services/dify_credentials.json
"""
import json
import os
import urllib.request

os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
BASE = "http://localhost:8088/console/api"
EMAIL = "admin@fabtwin.local"
PASSWORD = "FabTwin#2026!Dify"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    # 1. 系统初始化（首次部署创建管理员）
    try:
        r = call("POST", "/setup", {
            "email": EMAIL, "name": "FabTwin Admin", "password": PASSWORD,
        })
        print("[OK] 管理员已创建")
    except Exception as e:
        body = str(e)
        if "already" in body or "400" in body:
            print("[OK] 管理员已存在（跳过 setup）")
        else:
            print(f"[WARN] setup 响应: {body[:150]}")

    # 2. 登录拿 access_token
    r = call("POST", "/login", {"email": EMAIL, "password": PASSWORD,
                                "remember_me": True})
    token = (r.get("data") or {}).get("access_token") or r.get("access_token")
    if not token:
        print("[FAIL] 登录失败:", json.dumps(r, ensure_ascii=False)[:200])
        return
    print("[OK] 登录成功")

    # 3. 创建 Chat 应用
    app = call("POST", "/apps", {"name": "FabTwin 对话测试",
                                 "mode": "chat",
                                 "icon_type": "emoji", "icon": "🤖",
                                 "icon_background": "#FFEAD5"},
               token=token)
    app_id = app.get("id")
    print(f"[OK] 应用已创建 id={app_id}")

    # 4. 生成 API Key（service API）
    key_resp = call("POST", f"/apps/{app_id}/api-keys", {}, token=token)
    keys = key_resp if isinstance(key_resp, list) else key_resp.get("data", [])
    api_key = keys[0]["key"] if keys else None
    print(f"[OK] API Key: {api_key}")

    # 5. 落盘凭据
    creds = {"app_id": app_id, "api_key": api_key,
             "base_url": "http://localhost:8088/v1",
             "email": EMAIL, "password": PASSWORD}
    out = "E:/AI/fab-ai-services/dify_credentials.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)
    print(f"[OK] 凭据已写入 {out}")


if __name__ == "__main__":
    main()
