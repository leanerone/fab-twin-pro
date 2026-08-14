"""测试 AI 聊天接口（通过后端 API）"""
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import json
import urllib.request

BASE = "http://localhost:8002/api/ai"

def call_chat(question, machine_id=None, session_id=None):
    """调用 AI 聊天接口"""
    payload = {
        "question": question,
        "machine_id": machine_id,
        "session_id": session_id,
        "user_role": "admin",
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return {"error": f"HTTP {e.code}", "body": body}
    except Exception as e:
        return {"error": str(e)}


print("=" * 60)
print("测试 1: 简单问候（无机台上下文）")
print("=" * 60)
r = call_chat("你好，请简单介绍一下你能做什么")
print(f"provider: {r.get('provider', 'N/A')}")
print(f"model: {r.get('model', 'N/A')}")
print(f"tokens: in={r.get('tokens_in')}, out={r.get('tokens_out')}, total={r.get('tokens_total')}")
ans = r.get('answer', '')
print(f"answer (前300字): {ans[:300]}")
if r.get('error'):
    print(f"ERROR: {r['error']}")
    if r.get('body'):
        print(f"BODY: {r['body'][:500]}")

print("\n" + "=" * 60)
print("测试 2: OXE 机台上下文 - 查询 Chamber 状态")
print("=" * 60)
r = call_chat("3个Chamber当前状态", machine_id="OXE-61")
print(f"provider: {r.get('provider', 'N/A')}")
print(f"model: {r.get('model', 'N/A')}")
print(f"tokens: in={r.get('tokens_in')}, out={r.get('tokens_out')}, total={r.get('tokens_total')}")
print(f"tool_calls: {r.get('tool_calls')}")
ans = r.get('answer', '')
print(f"answer (前500字): {ans[:500]}")
if r.get('error'):
    print(f"ERROR: {r['error']}")
    if r.get('body'):
        print(f"BODY: {r['body'][:800]}")

print("\n" + "=" * 60)
print("测试 3: OXE 机台上下文 - 晶圆流向分析")
print("=" * 60)
r = call_chat("最新Lot的晶圆流向", machine_id="OXE-61")
print(f"provider: {r.get('provider', 'N/A')}")
print(f"model: {r.get('model', 'N/A')}")
print(f"tokens: in={r.get('tokens_in')}, out={r.get('tokens_out')}, total={r.get('tokens_total')}")
print(f"tool_calls: {r.get('tool_calls')}")
ans = r.get('answer', '')
print(f"answer (前500字): {ans[:500]}")
if r.get('error'):
    print(f"ERROR: {r['error']}")
    if r.get('body'):
        print(f"BODY: {r['body'][:800]}")

print("\n测试完成!")
