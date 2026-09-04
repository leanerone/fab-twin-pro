# -*- coding: utf-8 -*-
"""
自测脚本：直接打 Dify /v1/chat-messages 接口
通过 4 组不同 payload 对照，找出 400 BAD REQUEST 的根因。
使用方法（会先读取数据库里的全局 Dify URL+API Key，避免手动输入 Key）：
  cd fab-twin-pro
  set PYTHONIOENCODING=utf-8
  python scripts\test_dify_direct.py --question "你能帮我干什么"
如果数据库读取失败，可手动指定：
  python scripts\test_dify_direct.py --base-url "http://10.30.116.151/v1" --api-key "app-XXXXXX" --question "你能帮我干什么"
"""
import argparse
import json
import os
import sys
import requests

# 允许 backend 作为模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def load_global_dify_from_db():
    """从数据库读取全局 Dify base_url + api_key（复用 ai_middleware 的 DB 逻辑）。
    返回 (base_url, api_key) 或 (None, None)
    """
    try:
        from services.ai_middleware import AIMiddleware
        mw = AIMiddleware()
        base = (mw.dify_base_url or "").rstrip("/")
        key = mw.dify_api_key or ""
        print(f"[DB读取] dify_base_url={base!r}, dify_enabled={mw.dify_enabled}, "
              f"api_key={'*' * 8 + key[-4:] if len(key) > 4 else '(空)'}, provider={mw.provider}")
        if not base:
            # 兼容用户填写了不带 /v1 的 URL，AIConfigPanel 提交时已去版本
            # _load_dify_n8n_from_db 不会自动加 /v1，所以若没 /v1 这里也保留原样，
            # 后面 URL 拼接会按 endswith('/v1') 分支
            pass
        return base, key
    except Exception as e:
        print(f"[DB读取失败] {e}")
        return None, None


def build_url(base: str) -> str:
    """与 _call_dify 相同的 URL 拼接逻辑"""
    base = (base or "").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat-messages"
    return f"{base}/v1/chat-messages"


def run_case(name: str, url: str, headers: dict, payload: dict):
    print(f"\n{'='*70}\n[CASE] {name}\nURL  : {url}\nHEADER Authorization: {headers.get('Authorization','')[:28]}...")
    # 截断显示 payload，避免打印长 Key
    show = dict(payload)
    if "files" in show:
        show["files"] = f"<{len(show['files'])} items>"
    print("BODY :", json.dumps(show, ensure_ascii=False, indent=2))
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=90)
        body = resp.text
        # 尝试 JSON 美化
        try:
            body = json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception:
            pass
        print(f"STATUS: {resp.status_code}")
        if resp.status_code >= 400:
            print(f"BODY:\n{body[:2000]}")
            return False, resp.status_code, body
        else:
            # 只截取 answer 前 300 字
            try:
                j = resp.json()
                ans = j.get("answer") or "(no answer field)"
                print(f"ANSWER(前300字): {ans[:300]}")
                print(f"其他字段: conversation_id={j.get('conversation_id')}, "
                      f"event={j.get('event')}, mode={j.get('mode')}, "
                      f"metadata keys={list((j.get('metadata') or {}).keys())}")
            except Exception:
                print(f"BODY:\n{body[:800]}")
            return True, resp.status_code, body
    except Exception as e:
        print(f"网络异常: {type(e).__name__}: {e}")
        return False, None, str(e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=None, help="Dify API URL（含 /v1 或不含都可）")
    p.add_argument("--api-key", default=None, help="app- 开头的 Dify API Key")
    p.add_argument("--question", "-q", default="你能帮我干什么", help="提问内容")
    args = p.parse_args()

    base_url = args.base_url
    api_key = args.api_key
    if not base_url or not api_key:
        b, k = load_global_dify_from_db()
        base_url = base_url or b or ""
        api_key = api_key or k or ""

    if not base_url or not api_key:
        print("[错误] 未获取到 Dify base_url / api_key，请用 --base-url 和 --api-key 手动指定。")
        sys.exit(1)

    url = build_url(base_url)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    question = args.question
    print(f"\n本次提问: {question!r}")
    print(f"最终请求 URL: {url}")

    cases = []

    # Case 1: 与当前 ai_middleware._call_dify 完全一致
    cases.append((
        "① 当前代码 payload（含 conversation_id=空 与 inputs.machine_id+user_role）",
        {
            "inputs": {
                "machine_id": "",
                "user_role": "user",
            },
            "query": question,
            "response_mode": "blocking",
            "conversation_id": "",  # ← 可能导致 400（Dify 要求省略或传有效的 conversation_id）
            "user": "fabtwin_user",
            "files": [],
        },
    ))

    # Case 2: 去掉 conversation_id + 简化 inputs（Chatbot 应用 约定）
    cases.append((
        "② 去掉 conversation_id + files 字段 + user=fabtwin_user",
        {
            "inputs": {
                "machine_id": "",
                "user_role": "user",
            },
            "query": question,
            "response_mode": "blocking",
            "user": "fabtwin_user",
        },
    ))

    # Case 3: inputs 直接传空对象（某些 Dify 应用没有定义 inputs 变量会拒绝）
    cases.append((
        "③ inputs={}（空对象），去掉 files",
        {
            "inputs": {},
            "query": question,
            "response_mode": "blocking",
            "user": "fabtwin_user",
        },
    ))

    # Case 4: Workflow 应用格式（inputs={query, machine_id, user_role}, 不用 query 顶层字段）—— 若用户是 Dify Workflow
    cases.append((
        "④ Workflow 格式：inputs 带 query（顶层不传 query）",
        {
            "inputs": {
                "query": question,
                "machine_id": "",
                "user_role": "user",
            },
            "response_mode": "blocking",
            "user": "fabtwin_user",
        },
    ))

    # Case 5: 只传最小必需字段（极端保守）
    cases.append((
        "⑤ 最小字段：仅 query+response_mode+user（最宽松）",
        {
            "query": question,
            "response_mode": "blocking",
            "user": "fabtwin_user",
        },
    ))

    results = []
    for name, payload in cases:
        ok, status, _ = run_case(name, url, headers, payload)
        results.append((name, "✅PASS" if ok else "❌FAIL", status))

    print("\n" + "=" * 70)
    print("汇总：")
    for n, s, c in results:
        print(f"  {s} HTTP {c}  {n[:50]}")
    print("=" * 70)


if __name__ == "__main__":
    main()
