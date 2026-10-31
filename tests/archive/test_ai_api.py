#!/usr/bin/env python3
"""
AI /api/ai/chat 接口自测脚本

模拟前端直接调用 FastAPI 接口，捕获完整请求/响应和 500 错误堆栈。

运行方式：
    cd backend
    python test_ai_api.py

如果在本地开发环境运行，默认访问 http://localhost:8000/api/ai/chat
如果后端部署在其他地址，修改 BASE_URL。
"""
import sys
import os
import json
import traceback
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = os.environ.get("AI_API_BASE", "http://localhost:8000")
API_URL = f"{BASE_URL.rstrip('/')}/api/ai/chat"

# 测试用例（覆盖截图中报错的问题）
TEST_CASES = [
    {"name": "机台状态查询", "question": "PODOPENER-1状态", "machine_id": ""},
    {"name": "Lot追溯(V3WTG)", "question": "查V3WTG的lot信息", "machine_id": ""},
    {"name": "分片Lot(PC00H.29)", "question": "PC00H.29的lot信息", "machine_id": ""},
    {"name": "今日报警统计", "question": "今日报警统计", "machine_id": ""},
    {"name": "产量统计", "question": "今天run了多少lot", "machine_id": ""},
    {"name": "不存在的Lot", "question": "查询LOT12345", "machine_id": ""},
]


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def call_chat(question, machine_id="", session_id=None):
    """调用 /api/ai/chat 接口，返回 (success, response_dict_or_text, status_code)"""
    payload = {
        "question": question,
        "machine_id": machine_id or None,
        "session_id": session_id,
        "user_role": "user",
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text}
        return resp.status_code == 200, data, resp.status_code
    except Exception as e:
        return False, {"error": str(e), "trace": traceback.format_exc()}, 0


def test_api():
    print_section(f"接口测试: {API_URL}")
    print(f"  Base URL: {BASE_URL}")
    print(f"  当前时间: {__import__('datetime').datetime.now().isoformat()}")

    pass_count = 0
    fail_count = 0

    session_id = None
    for case in TEST_CASES:
        ok, data, status = call_chat(case["question"], case.get("machine_id", ""), session_id)

        if ok and isinstance(data, dict):
            session_id = data.get("session_id") or session_id

        print(f"\n  [{'PASS' if ok else 'FAIL'}] {case['name']} (HTTP {status})")
        print(f"       问题: {case['question']}")

        if ok:
            pass_count += 1
            answer = data.get("answer", "")[:120]
            print(f"       回答: {answer}{'...' if len(data.get('answer', '')) > 120 else ''}")
            print(f"       provider: {data.get('provider_name') or data.get('provider')}")
            print(f"       tool_calls: {len(data.get('tool_calls') or [])}")
            if data.get("jump_machine_id"):
                print(f"       jump: {data['jump_machine_id']} @ {data.get('jump_timestamp')}")
        else:
            fail_count += 1
            print(f"       状态码: {status}")
            print(f"       响应: {json.dumps(data, ensure_ascii=False, default=str)[:500]}")

    print_section("汇总")
    print(f"  PASS: {pass_count}")
    print(f"  FAIL: {fail_count}")

    if fail_count > 0:
        print("\n  请检查后端控制台日志获取完整 500 错误堆栈。")
        print("  常见排查方向：")
        print("    1. Pydantic schema 字段不匹配（如 tool_calls 中 args 字段未声明）")
        print("    2. 返回结果中包含 datetime 对象未序列化")
        print("    3. 数据库会话或模型加载异常")


def test_schema_validation():
    """本地验证 AIChatResponse schema 是否能容纳中间件返回的数据结构"""
    print_section("本地 Schema 验证")
    try:
        from schemas import AIChatResponse, AIToolCall

        # 模拟本地规则引擎返回的 tool_calls（含 args）
        tool_calls = [
            {"tool": "get_machine_status", "args": {"machine_id": "PODOPENER-1"}, "status": "success"},
            {"tool": "get_lot_info", "args": {"lot_id": "V3WTG", "machine_id": None}, "status": "success"},
        ]

        # 模拟完整响应
        result = {
            "answer": "测试回答",
            "sql": "SELECT * FROM ...",
            "jump_timestamp": "2026-07-29T15:21:55",
            "jump_machine_id": "PODOPENER-51",
            "machine_online": True,
            "table_data": {"headers": ["时间", "机台"], "rows": [["2026-07-29", "PODOPENER-51"]]},
            "tool_calls": tool_calls,
            "sources": [{"type": "db", "model": None}],
            "session_id": "test_session",
            "provider": "local",
            "provider_name": "本地规则引擎",
            "model": None,
            "config_id": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        resp = AIChatResponse(**result)
        print(f"  Schema 验证通过: answer={resp.answer[:20]}")
        print(f"  tool_calls 数量: {len(resp.tool_calls or [])}")
        print(f"  第一个 tool_call: {resp.tool_calls[0].model_dump() if resp.tool_calls else None}")
        return True
    except Exception as e:
        print(f"  Schema 验证失败: {e}")
        traceback.print_exc()
        return False


def test_middleware_directly():
    """直接调用中间件，确认不是中间件逻辑问题"""
    print_section("直接调用中间件验证")
    try:
        from services.ai_middleware import ai_middleware
        result = ai_middleware.chat("PODOPENER-1状态", session_id="test_direct")
        print(f"  中间件返回成功: answer={result.get('answer', '')[:60]}...")
        print(f"  tool_calls: {result.get('tool_calls')}")
        return True
    except Exception as e:
        print(f"  中间件调用失败: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 1. 先本地验证 schema
    schema_ok = test_schema_validation()

    # 2. 直接调用中间件
    middleware_ok = test_middleware_directly()

    # 3. 调用真实 API
    test_api()

    print("\n" + "=" * 70)
    print("  自测完成")
    print("=" * 70)
