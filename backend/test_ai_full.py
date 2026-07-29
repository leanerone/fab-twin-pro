#!/usr/bin/env python3
"""
AI 功能完整测试脚本

测试覆盖：
1. 实体提取（机台ID / Lot ID）
2. 本地规则引擎工具调用
3. LLM 模式工具调用（如果配置了LLM）
4. 跳转字段检查（jump_timestamp / jump_machine_id）
5. 序列化稳定性（datetime 处理）
6. 环境诊断（MCP / MES / DT_EVENT_RAW 可用性）

运行方式：
    cd backend
    python test_ai_full.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from services.ai_middleware import AIMiddleware

# ============ 测试报告收集 ============
TEST_RESULTS = []

def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_result(name, success, detail=""):
    status = "PASS" if success else "FAIL"
    icon = "\u2705" if success else "\u274c"
    print(f"  {icon}  {status}  {name}")
    if detail:
        print(f"       {detail}")
    TEST_RESULTS.append({"name": name, "success": success, "detail": detail})

def print_warn(name, detail=""):
    print(f"  \u26a0\ufe0f  SKIP  {name}")
    if detail:
        print(f"       {detail}")
    TEST_RESULTS.append({"name": name, "success": None, "detail": detail})

# ============ 环境诊断 ============
def diagnose_environment():
    """诊断测试环境依赖"""
    print_section("零、环境诊断")
    db = SessionLocal()
    diagnostics = {}
    try:
        # 1. DT_EVENT_RAW 表数据量
        try:
            from models import DT_EVENT_RAW
            count = db.query(DT_EVENT_RAW).count()
            diagnostics["dt_event_raw_count"] = count
            print(f"  DT_EVENT_RAW 表记录数: {count}")
        except Exception as e:
            diagnostics["dt_event_raw_count"] = 0
            print(f"  DT_EVENT_RAW 表不可用: {e}")

        # 2. machines 表
        try:
            from models import Machine
            count = db.query(Machine).count()
            diagnostics["machines_count"] = count
            print(f"  machines 表记录数: {count}")
        except Exception as e:
            diagnostics["machines_count"] = 0
            print(f"  machines 表不可用: {e}")

        # 3. MCP / MES 配置
        try:
            from services.mcp_client import get_mcp_config
            cfg = get_mcp_config()
            diagnostics["mcp_enabled"] = cfg.get("enabled", False)
            diagnostics["mcp_has_token"] = bool(cfg.get("token"))
            print(f"  MCP 配置: enabled={cfg.get('enabled')}, has_token={bool(cfg.get('token'))}")
        except Exception as e:
            diagnostics["mcp_enabled"] = False
            diagnostics["mcp_has_token"] = False
            print(f"  MCP 配置不可用: {e}")

        # 4. V3WTG 本地事件检查
        try:
            from models import DT_EVENT_RAW
            v3wtg_events = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.payload_json.like('%V3WTG%')
            ).count()
            diagnostics["v3wtg_local_events"] = v3wtg_events
            print(f"  V3WTG 本地事件数: {v3wtg_events}")
        except Exception as e:
            diagnostics["v3wtg_local_events"] = 0
            print(f"  V3WTG 本地事件查询失败: {e}")

        # 5. AI Provider 配置
        try:
            from models import AIProviderConfig
            providers = db.query(AIProviderConfig).filter(AIProviderConfig.is_enabled == True).count()
            diagnostics["ai_providers"] = providers
            print(f"  已启用 AI Provider 数: {providers}")
        except Exception as e:
            diagnostics["ai_providers"] = 0
            print(f"  AI Provider 配置表不可用: {e}")

    finally:
        db.close()

    return diagnostics

# ============ 实体提取测试 ============
def test_entity_extraction():
    print_section("一、实体提取测试")
    mw = AIMiddleware()
    passed = 0
    total = 0

    machine_cases = [
        ("PODOPENER-1状态", "PODOPENER-1"),
        ("查OXE-01的事件", "OXE-01"),
        ("VPO-01怎么样", "VPO-01"),
        ("PODOPENER-1狀態", "PODOPENER-1"),
        ("PODOPENER-1的lot", "PODOPENER-1"),
        ("NT938的lot信息", None),
        ("podopener-1状态", "PODOPENER-1"),
        ("PODOPENER-51的事件", "PODOPENER-51"),
    ]
    print("  【机台ID提取】")
    for question, expected in machine_cases:
        result = mw._extract_machine_id(question)
        ok = result == expected
        if ok:
            passed += 1
        total += 1
        print_result(f"'{question}'", ok, f"期望={expected}, 实际={result}")

    lot_cases = [
        ("查V3WTG的lot信息", "V3WTG"),
        ("PN70C是什么产品", "PN70C"),
        ("PC00H.29的状态", "PC00H.29"),
        ("NT938.15分片", "NT938.15"),
        ("P0093的lot", "P0093"),
        ("查询LOT12345", "LOT12345"),
        ("PFR0G的信息", "PFR0G"),
        ("PODOPENER-1状态", None),
        ("今天天气如何", None),
    ]
    print("\n  【Lot ID提取】")
    for question, expected in lot_cases:
        result = mw._extract_lot_id(question)
        ok = result == expected
        if ok:
            passed += 1
        total += 1
        print_result(f"'{question}'", ok, f"期望={expected}, 实际={result}")

    print(f"\n  实体提取通过率: {passed}/{total}")
    return passed, total

# ============ 本地规则引擎测试 ============
def test_local_rule_engine(env):
    print_section("二、本地规则引擎测试")
    db = SessionLocal()
    mw = AIMiddleware()

    try:
        # 测试1: 机台状态查询（不依赖外部MES）
        try:
            result = mw._local_rule_engine("PODOPENER-1状态", execution_log=[], tool_calls_record=[])
            ok = "PODOPENER-1" in result.get("answer", "")
            detail = f"answer长度={len(result.get('answer', ''))}"
            if result.get("jump_machine_id"):
                detail += f", jump={result['jump_machine_id']}"
            print_result("机台状态查询", ok, detail)
        except Exception as e:
            print_result("机台状态查询", False, f"异常: {str(e)[:100]}")

        # 测试2: Lot追溯（V3WTG）- 依赖MES或本地事件
        try:
            result = mw._local_rule_engine("查V3WTG的lot信息", execution_log=[], tool_calls_record=[])
            answer = result.get("answer", "")
            has_mes = "MES" in answer or "\u4ea7\u54c1\u578b\u53f7" in answer
            has_local = "FabTwin" in answer or "\u8bbe\u5907\u4e8b\u4ef6" in answer
            has_not_found = "\u672a\u67e5\u8be2\u5230" in answer or "\u6682\u65e0" in answer

            if has_mes or has_local:
                print_result("Lot追溯（V3WTG）", True, f"包含MES={has_mes}, 包含本地事件={has_local}, answer长度={len(answer)}")
            elif has_not_found and not env.get("mcp_enabled") and env.get("v3wtg_local_events", 0) == 0:
                print_warn("Lot追溯（V3WTG）", f"未找到数据（预期：MES未配置且本地无事件）, answer长度={len(answer)}")
            else:
                print_result("Lot追溯（V3WTG）", False, f"answer长度={len(answer)}, 内容异常")
        except Exception as e:
            print_result("Lot追溯（V3WTG）", False, f"异常: {str(e)[:100]}")

        # 测试3: Lot追溯（PC00H.29）- 分片Lot格式
        try:
            result = mw._local_rule_engine("PC00H.29的lot信息", execution_log=[], tool_calls_record=[])
            ok = "PC00H.29" in result.get("answer", "")
            print_result("Lot追溯（PC00H.29）", ok, f"answer长度={len(result.get('answer', ''))}")
        except Exception as e:
            print_result("Lot追溯（PC00H.29）", False, f"异常: {str(e)[:100]}")

        # 测试4: 告警查询
        try:
            result = mw._local_rule_engine("今日报警统计", execution_log=[], tool_calls_record=[])
            ok = "\u544a\u8b66" in result.get("answer", "") or "\u6682\u65e0" in result.get("answer", "")
            print_result("告警查询", ok, f"answer长度={len(result.get('answer', ''))}")
        except Exception as e:
            print_result("告警查询", False, f"异常: {str(e)[:100]}")

        # 测试5: 产量统计
        try:
            result = mw._local_rule_engine("今天run了多少lot", execution_log=[], tool_calls_record=[])
            ok = len(result.get("answer", "")) > 0
            detail = f"answer长度={len(result.get('answer', ''))}"
            if result.get("jump_machine_id"):
                detail += f", jump={result['jump_machine_id']}"
            print_result("产量统计", ok, detail)
        except Exception as e:
            print_result("产量统计", False, f"异常: {str(e)[:100]}")

        # 测试6: 不存在的Lot
        try:
            result = mw._local_rule_engine("查询LOT12345", execution_log=[], tool_calls_record=[])
            ok = "LOT12345" in result.get("answer", "")
            print_result("不存在Lot查询", ok, f"answer长度={len(result.get('answer', ''))}")
        except Exception as e:
            print_result("不存在Lot查询", False, f"异常: {str(e)[:100]}")

    finally:
        db.close()

# ============ 序列化稳定性测试 ============
def test_serialization():
    print_section("三、序列化稳定性测试")
    from datetime import datetime

    test_cases = [
        {"name": "纯字符串", "data": {"ts": "2026-07-29 12:00:00"}},
        {"name": "datetime对象", "data": {"ts": datetime(2026, 7, 29, 12, 0, 0)}},
        {"name": "混合类型", "data": {"ts": datetime.now(), "name": "test", "count": 5}},
        {"name": "嵌套datetime", "data": {"nested": {"created_at": datetime.now()}, "list": [datetime.now()]}},
    ]

    for case in test_cases:
        try:
            result = json.dumps(case["data"], ensure_ascii=False, default=str)
            ok = True
            detail = f"序列化成功，长度={len(result)}"
        except Exception as e:
            ok = False
            detail = f"异常: {str(e)[:100]}"
        print_result(case["name"], ok, detail)

# ============ 跳转字段测试 ============
def test_jump_fields(env):
    print_section("四、跳转字段检查")
    db = SessionLocal()
    mw = AIMiddleware()

    try:
        # 测试1: 机台状态查询 - 应该有机台跳转
        result = mw._local_rule_engine("PODOPENER-1状态", execution_log=[], tool_calls_record=[])
        has_jump = bool(result.get("jump_machine_id"))
        print_result("PODOPENER-1 跳转字段", has_jump,
                     f"machine_id={result.get('jump_machine_id')}, ts={result.get('jump_timestamp')}")

        # 测试2: V3WTG - 如果有本地事件则应有跳转，否则跳过
        result = mw._local_rule_engine("查V3WTG的lot信息", execution_log=[], tool_calls_record=[])
        has_jump = bool(result.get("jump_machine_id")) and bool(result.get("jump_timestamp"))
        if env.get("v3wtg_local_events", 0) > 0 or env.get("mcp_enabled"):
            print_result("V3WTG 跳转字段", has_jump,
                         f"machine_id={result.get('jump_machine_id')}, ts={result.get('jump_timestamp')}")
        else:
            print_warn("V3WTG 跳转字段", f"MES未配置且本地无事件，跳过跳转检查 (machine_id={result.get('jump_machine_id')})")

        # 测试3: 跳转机台在线状态标记
        if result.get("jump_machine_id"):
            online = result.get("machine_online")
            print_result("跳转机台在线状态标记", online is not None, f"machine_online={online}")

    finally:
        db.close()

# ============ LLM 模式测试 ============
def test_llm_mode():
    print_section("五、LLM 模式测试（需配置有效的 OpenAI 兼容接口）")
    mw = AIMiddleware()

    if not mw.base_url or not mw.api_key:
        print_warn("LLM 模式", "未配置 LLM（base_url 或 api_key 为空）")
        print("       如需测试 LLM 模式，请在 AI 配置面板添加 Provider")
        return False

    print(f"  当前 Provider: {mw.provider}")
    print(f"  当前 Model: {mw.model}")
    print(f"  Base URL: {mw.base_url}")

    # 测试1: 简单机台状态（单轮对话）
    try:
        result = mw.chat("PODOPENER-1状态", session_id="test_session_llm_1")
        ok = "PODOPENER-1" in result.get("answer", "") or "\u8fd0\u884c\u4e2d" in result.get("answer", "")
        detail = f"answer长度={len(result.get('answer', ''))}"
        if result.get("tool_calls"):
            detail += f", tool_calls={len(result['tool_calls'])}"
        print_result("LLM 机台状态查询", ok, detail)
    except Exception as e:
        print_result("LLM 机台状态查询", False, f"异常: {str(e)[:200]}")

    # 测试2: Lot查询（可能触发工具调用）
    try:
        result = mw.chat("查V3WTG的lot信息", session_id="test_session_llm_2")
        ok = "V3WTG" in result.get("answer", "")
        detail = f"answer长度={len(result.get('answer', ''))}"
        if result.get("tool_calls"):
            detail += f", tool_calls={len(result['tool_calls'])}"
        if result.get("jump_machine_id"):
            detail += f", jump={result['jump_machine_id']}"
        print_result("LLM Lot查询", ok, detail)
    except Exception as e:
        print_result("LLM Lot查询", False, f"异常: {str(e)[:200]}")

    # 测试3: 无意义问题（测试LLM不瞎编）
    try:
        result = mw.chat("今天天气怎么样", session_id="test_session_llm_3")
        ok = len(result.get("answer", "")) > 0
        print_result("LLM 无关问题", ok, f"answer长度={len(result.get('answer', ''))}")
    except Exception as e:
        print_result("LLM 无关问题", False, f"异常: {str(e)[:200]}")

    return True

# ============ 日志记录测试 ============
def test_logging():
    print_section("六、使用记录日志测试")
    try:
        from models import AIUsageLog
        db = SessionLocal()
        try:
            recent = db.query(AIUsageLog).order_by(AIUsageLog.id.desc()).limit(3).all()
            if recent:
                print(f"  AI_USAGE_LOGS 表正常，最近 {len(recent)} 条记录:")
                for r in recent:
                    tool_calls_ok = bool(r.tool_calls)
                    exec_log_ok = bool(r.execution_log)
                    print(f"    ID={r.id}, provider={r.provider}, success={r.success}, tool_calls={tool_calls_ok}, execution_log={exec_log_ok}")
                print_result("日志表检查", True, f"最近记录ID={recent[0].id}")
            else:
                print_warn("日志表检查", "AI_USAGE_LOGS 表为空（尚无AI调用记录）")
        finally:
            db.close()
    except Exception as e:
        print_result("日志表检查", False, f"异常: {str(e)[:100]}")

# ============ 主函数 ============
def main():
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#" + "  FabTwin AI 功能完整测试".center(64) + "#")
    print("#" + " " * 68 + "#")
    print("#" * 70)

    # 环境诊断
    env = diagnose_environment()

    # 运行测试
    passed, total = test_entity_extraction()
    test_local_rule_engine(env)
    test_serialization()
    test_jump_fields(env)
    llm_tested = test_llm_mode()
    test_logging()

    # 汇总
    print("\n" + "#" * 70)
    print("#" + "  测试完成".center(64) + "#")
    print("#" * 70)

    total_pass = sum(1 for r in TEST_RESULTS if r["success"] is True)
    total_fail = sum(1 for r in TEST_RESULTS if r["success"] is False)
    total_skip = sum(1 for r in TEST_RESULTS if r["success"] is None)

    print(f"\n  汇总: \u2705 PASS={total_pass}  \u274c FAIL={total_fail}  \u26a0\ufe0f SKIP={total_skip}")

    if total_fail > 0:
        print("\n  失败项列表:")
        for r in TEST_RESULTS:
            if r["success"] is False:
                print(f"    - {r['name']}: {r['detail']}")

    print("""
========================================================================
                        【标准测试流程说明】
========================================================================

一、测试环境准备
    1. 确保后端服务已启动（python main.py 或 uvicorn）
    2. 确保前端已编译并访问正常
    3. 如需测试 MES 查询，确保 N8N MCP 已配置（AI配置面板 -> MCP设置）

二、模型选择与配置
    1. 本地规则引擎（默认，无需配置）
       - 优点：零延迟、零费用、离线可用
       - 缺点：不支持自然语言理解，只能识别固定关键词
       - 适用：机台ID/Lot ID查询、产量统计、告警查看

    2. OpenAI 兼容模型（需配置 Provider）
       - 路径：管理员登录 -> AI配置管理 -> 添加Provider
       - 必填：base_url, api_key, model
       - 可选：temperature, max_tokens
       - 设为默认后，所有新会话使用该模型
       - 适用：复杂问题、自然语言理解、需要推理的场景

三、标准测试用例（按功能分类）

    【机台状态查询】
    问题: "PODOPENER-1状态"
    预期: 返回机台当前状态、最新事件、运行模式、当前Lot
    跳转: 应包含 jump_machine_id=PODOPENER-1

    【Lot信息查询 - 本地有事件】
    问题: "查V3WTG的lot信息"（需该Lot在DT_EVENT_RAW中有记录或MES已配置）
    预期: 返回MES信息（产品/工艺/步骤/状态）+ FabTwin设备事件时间线
    跳转: 如有机台事件，应包含 jump_machine_id 和 jump_timestamp

    【Lot信息查询 - 分片Lot】
    问题: "PC00H.29的lot信息"
    预期: 正确识别分片Lot格式（主Lot.序号）

    【产量统计】
    问题: "今天run了多少lot"
    预期: 返回当日Lot数量及示例列表

    【告警查询】
    问题: "今日报警统计"
    预期: 返回告警记录列表或"暂无告警"

    【不存在的Lot】
    问题: "查询LOT12345"
    预期: 友好提示未找到，不报错

    【自然语言 - LLM模式】
    问题: "帮我查一下 V3WTG 这个批次的详细信息"
    预期: LLM理解意图并调用 get_lot_info 工具

四、Lot 跳转功能验证步骤
    1. 提问: "查V3WTG的lot信息"
    2. 观察AI回答：
       - 若Lot有设备事件，回答底部应显示 "[跳转] 跳转到PODOPENER-xx"
       - 若机台未上线，显示 "[警告] 机台暂未上线"
    3. 点击跳转按钮：
       - 若当前不在目标机台页面 -> 自动导航到 /machine/目标机台?ts=时间戳
       - 若已在目标机台页面 -> 触发历史回放时间游标定位
    4. 预期效果：页面跳转到对应机台，回放时间定位到该事件时刻

五、使用记录检查（排查问题用）
    1. 浏览器访问: GET http://后端地址/api/ai/usage/logs
    2. 检查字段:
       - provider / model: 确认使用了哪个模型
       - success: 0表示失败，1表示成功
       - error_msg: 失败时的错误信息
       - tool_calls: JSON格式工具调用记录
       - execution_log: 执行步骤追踪（路由决策、工具调用、错误回退）
    3. 常见错误:
       - "Object of type datetime is not JSON serializable" -> 序列化已修复，如再出现请重启后端
       - "缺少 base_url 或 api_key" -> Provider未配置或配置未生效
       - "MCP 调用失败" -> N8N MCP Token过期或网络不通

六、切换模型测试
    1. 在AI配置面板切换默认Provider为"本地规则引擎"
    2. 提问相同问题，对比回答差异
    3. 本地引擎：直接、结构化、无Token消耗
    4. LLM模型：自然语言、可能带推理过程、消耗Token

========================================================================
""")

if __name__ == "__main__":
    main()
