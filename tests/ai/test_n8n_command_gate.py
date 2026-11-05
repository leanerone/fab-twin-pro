# -*- coding: utf-8 -*-
"""T1 回归：admin N8N 指令识别收紧（2026-11-06）

旧缺陷：_is_n8n_command 用 8 个宽泛关键词（导出/报表/工单/批量/自动/推送/...），
管理员一句"批量查一下告警"就会直通 n8n 工作流、绕过 LLM 智能路由。

新设计三层：
  ① 显式前缀 n8n: / n8n：        → 无条件命中
  ② 强匹配   动词+名词共现        → 命中（导出…报表 / 生成…工单 / 推送…日报）
  ③ 弱关键词 仅在无智能引擎时兜底  → llm_ready=True 时不命中

运行：python tests/ai/test_n8n_command_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

from modules.ai_assistant.services.middleware import AIMiddleware  # noqa: E402

RESULTS = []


def check(name, actual, expect):
    ok = (actual == expect)
    RESULTS.append(ok)
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"  {mark} {name} —— got={actual!r} expect={expect!r}")


def main():
    m = AIMiddleware()

    # ── ① 显式前缀：无条件命中 ─────────────────────────────
    print("== ① 显式前缀 n8n: ==")
    check("n8n:导出报警报表", m._is_n8n_command("n8n:导出报警报表"), True)
    check("全角冒号 n8n：生成日报", m._is_n8n_command("n8n：生成日报"), True)
    check("大写 N8N: 也能命中", m._is_n8n_command("N8N:推送周报"), True)

    # ── ② 强匹配：动词+名词共现 ────────────────────────────
    print("== ② 强匹配 动词+名词 ==")
    check("帮我导出报警报表", m._is_n8n_command("帮我导出报警报表"), True)
    check("生成一份今天的产量报告", m._is_n8n_command("生成一份今天的产量报告"), True)
    check("推送今天的日报", m._is_n8n_command("推送今天的日报"), True)
    check("给我发一下昨天的故障工单", m._is_n8n_command("给我发一下昨天的故障工单"), True)

    # ── ③ 弱关键词：有智能引擎时让路 ────────────────────────
    print("== ③ 弱关键词让路（llm_ready=True）==")
    check("批量查一下告警（有LLM）", m._is_n8n_command("批量查一下告警", llm_ready=True), False)
    check("自动推送一下（有LLM）", m._is_n8n_command("自动推送一下", llm_ready=True), False)
    check("这个报表怎么看（有LLM）", m._is_n8n_command("这个报表怎么看", llm_ready=True), False)
    check("帮我导出（有LLM，无名词）", m._is_n8n_command("帮我把数据导出", llm_ready=True), False)

    # ── ③' 弱关键词：无智能引擎时保持旧兜底 ─────────────────
    print("== ③' 无引擎兜底（llm_ready=False）==")
    check("批量查一下告警（无LLM）", m._is_n8n_command("批量查一下告警", llm_ready=False), True)
    check("导出数据（无LLM）", m._is_n8n_command("导出数据", llm_ready=False), True)

    # ── 日常问题绝不误触发 ─────────────────────────────────
    print("== 日常问题不误触发 ==")
    check("今天产量多少", m._is_n8n_command("今天产量多少", llm_ready=True), False)
    check("OXE-51状态怎么样", m._is_n8n_command("OXE-51状态怎么样", llm_ready=True), False)
    check("查一下LOT100131", m._is_n8n_command("查一下LOT100131", llm_ready=True), False)
    check("空字符串", m._is_n8n_command("", llm_ready=True), False)

    # ── _smart_route_ready 判定 ────────────────────────────
    print("== _smart_route_ready ==")
    check("route=dify", m._smart_route_ready("dify", None), True)
    check("route=hybrid", m._smart_route_ready("hybrid", None), True)
    check("机台专属Dify命中", m._smart_route_ready("local", {"dify_base_url": "x"}), True)
    check("route=local", m._smart_route_ready("local", None), False)

    old_bu, old_key = m.base_url, m.api_key
    try:
        m.base_url, m.api_key = "http://x", "k"
        check("custom+有key", m._smart_route_ready("custom", None), True)
        m.base_url, m.api_key = "", ""
        check("custom+缺key", m._smart_route_ready("custom", None), False)
    finally:
        m.base_url, m.api_key = old_bu, old_key

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（n8n 指令门控行为符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
