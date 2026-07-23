"""AI 数据源自测脚本（只读，不修改任何代码）

目的：在改造 AI 规则引擎前，先验证每个数据源能查到什么真实资料，
     输出样例数据，便于决定如何替换假规则。

运行方式（在 backend 目录下）：
    python _debug_ai.py

或者指定机台：
    python _debug_ai.py PODOPENER-1
"""
import sys
import json
import os
from datetime import datetime

# 让 backend 目录可被导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import (
    Machine, Lot, Recipe, Alarm,
    DT_EVENT_RAW, DT_EVENT_RAW_CUR, DT_EVENT_STD,
    DT_STATE_SNAPSHOT, DT_ALARM_EVENT,
    MachineToolMapping,
)


SEP = "=" * 70
SUBSEP = "-" * 70


def _trunc(s, n=200):
    """截断字符串用于显示"""
    if s is None:
        return "(NULL)"
    s = str(s)
    return s if len(s) <= n else s[:n] + "...(truncated)"


def _print_list(items, label, limit=5):
    """打印列表的样例"""
    print(f"\n[{label}] 共 {len(items)} 条，展示前 {min(limit, len(items))} 条：")
    if not items:
        print("  (无数据)")
        return
    for i, item in enumerate(items[:limit]):
        if hasattr(item, "__dict__"):
            cols = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
            print(f"  #{i+1}: {_trunc(json.dumps(cols, ensure_ascii=False, default=str), 300)}")
        else:
            print(f"  #{i+1}: {_trunc(str(item), 300)}")


def check_machine_table(db, machine_id=None):
    """检查1: machines 表主数据"""
    print(f"\n{SEP}")
    print("【检查1】machines 表 - 机台主数据（AI 当前状态查询的数据源）")
    print(SEP)

    total = db.query(Machine).count()
    print(f"总机台数: {total}")

    if machine_id:
        m = db.query(Machine).filter(Machine.id == machine_id).first()
        if m:
            print(f"\n目标机台 {machine_id} 详情：")
            print(f"  id={m.id}, name={m.name}, model={m.model}")
            print(f"  state={m.state}, process_type={m.process_type}, process_step={m.process_step}")
            print(f"  temp={m.temp}, pressure={m.pressure}, rf_power={m.rf_power}, gas_flow={m.gas_flow}")
            print(f"  wafer_count={m.wafer_count}, alarm_count={m.alarm_count}")
            print(f"  updated_at={m.updated_at}")
            # 关键判断：这些值是不是默认值/假数据
            defaults = {
                "temp": 25.0, "pressure": 1.0, "gas_flow": 0.0,
                "rf_power": 0.0, "wafer_count": 0, "alarm_count": 0
            }
            fake_flags = []
            for k, default in defaults.items():
                val = getattr(m, k)
                if val == default:
                    fake_flags.append(f"{k}={val}(默认值)")
            if fake_flags:
                print(f"\n  ⚠️ 这些字段还是默认值（假数据）: {', '.join(fake_flags)}")
            else:
                print(f"\n  ✅ 字段非默认值，看起来有真实数据")
        else:
            print(f"\n  ❌ 未找到机台 {machine_id}")

    # 抽样 3 台机台看 state 分布
    print(f"\n前 3 台机台样例：")
    samples = db.query(Machine).limit(3).all()
    for m in samples:
        print(f"  {m.id}: state={m.state}, temp={m.temp}, wafer_count={m.wafer_count}")


def check_dt_state_snapshot(db, machine_id=None):
    """检查2: DT_STATE_SNAPSHOT 表 - 真实状态快照"""
    print(f"\n{SEP}")
    print("【检查2】DT_STATE_SNAPSHOT 表 - 真实状态快照（用于替换 machines.temp 假数据）")
    print(SEP)

    try:
        total = db.query(DT_STATE_SNAPSHOT).count()
        print(f"总记录数: {total}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return

    if total == 0:
        print("⚠️ 表为空，没有真实状态快照数据")
        return

    q = db.query(DT_STATE_SNAPSHOT)
    if machine_id:
        q = q.filter(DT_STATE_SNAPSHOT.tool_id == machine_id)
    snapshots = q.order_by(DT_STATE_SNAPSHOT.snapshot_ts_utc.desc()).limit(5).all()
    _print_list(snapshots, f"最近状态快照 machine={machine_id or 'ALL'}")

    # 统计 machine_state 分布
    print(f"\n机台状态分布：")
    from sqlalchemy import func
    rows = db.query(
        DT_STATE_SNAPSHOT.machine_state,
        func.count("*").label("cnt")
    ).group_by(DT_STATE_SNAPSHOT.machine_state).all()
    for r in rows:
        print(f"  {r.machine_state}: {r.cnt} 条")


def check_dt_event_raw(db, machine_id=None):
    """检查3: DT_EVENT_RAW 表 - 原始事件（温度趋势的真实数据源）"""
    print(f"\n{SEP}")
    print("【检查3】DT_EVENT_RAW 表 - 原始事件（温度趋势的真实数据源）")
    print(SEP)

    try:
        total = db.query(DT_EVENT_RAW).count()
        print(f"总记录数: {total}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return

    if total == 0:
        print("⚠️ 表为空")
        return

    q = db.query(DT_EVENT_RAW)
    if machine_id:
        q = q.filter(DT_EVENT_RAW.tool_id == machine_id)
    events = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(3).all()

    print(f"\n最近 3 条原始事件样例（machine={machine_id or 'ALL'}）：")
    for i, e in enumerate(events):
        print(f"\n  #{i+1}:")
        print(f"    raw_id={_trunc(e.raw_id, 50)}")
        print(f"    tool_id={e.tool_id}")
        print(f"    source_system={e.source_system}")
        print(f"    received_ts_utc={e.received_ts_utc}")
        print(f"    event_ts_utc={e.event_ts_utc}")
        print(f"    parse_status={e.parse_status}")
        # 关键：payload_json 里到底有什么
        print(f"    payload_json (前 500 字符):")
        print(f"      {_trunc(e.payload_json, 500)}")
        # 尝试解析 JSON 看有哪些字段
        if e.payload_json:
            try:
                payload = json.loads(e.payload_json)
                if isinstance(payload, dict):
                    print(f"    payload 顶层字段: {list(payload.keys())}")
                    # 看是否包含温度/压力等参数
                    param_keys = [k for k in payload.keys() if any(
                        x in k.lower() for x in
                        ["temp", "pressure", "rf", "gas", "flow", "power", "state", "lot", "step"]
                    )]
                    if param_keys:
                        print(f"    ✅ 发现参数字段: {param_keys}")
                        for k in param_keys[:5]:
                            print(f"       {k} = {payload[k]}")
                    else:
                        print(f"    ⚠️ payload 中未发现温度/压力等参数字段")
            except json.JSONDecodeError:
                print(f"    ⚠️ payload_json 不是合法 JSON")


def check_dt_event_std(db, machine_id=None):
    """检查4: DT_EVENT_STD 表 - 标准化事件（替代硬编码 PODOPENER 14 步）"""
    print(f"\n{SEP}")
    print("【检查4】DT_EVENT_STD 表 - 标准化事件（替代硬编码工艺步骤）")
    print(SEP)

    try:
        total = db.query(DT_EVENT_STD).count()
        print(f"总记录数: {total}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return

    if total == 0:
        print("⚠️ 表为空")
        return

    # 统计 event_type 分布（这是替换硬编码 14 步的关键）
    from sqlalchemy import func
    print(f"\nevent_type 分布（前 20 种）：")
    rows = db.query(
        DT_EVENT_STD.event_type,
        func.count("*").label("cnt")
    ).group_by(DT_EVENT_STD.event_type).order_by(func.count("*").desc()).limit(20).all()
    for r in rows:
        print(f"  {r.event_type}: {r.cnt} 条")

    # 指定机台的事件时间线
    if machine_id:
        events = db.query(DT_EVENT_STD).filter(
            DT_EVENT_STD.tool_id == machine_id
        ).order_by(DT_EVENT_STD.created_ts_utc.desc()).limit(10).all()
        _print_list(events, f"机台 {machine_id} 最近 10 条标准化事件")


def check_dt_alarm_event(db, machine_id=None):
    """检查5: DT_ALARM_EVENT 表 - 真实告警（替换 alarms 表）"""
    print(f"\n{SEP}")
    print("【检查5】DT_ALARM_EVENT 表 - 真实告警事件（生产表，替换演示用 alarms 表）")
    print(SEP)

    try:
        total = db.query(DT_ALARM_EVENT).count()
        print(f"总记录数: {total}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return

    if total == 0:
        print("⚠️ 表为空，仍需用 alarms 表做演示")
        return

    # 严重等级分布
    from sqlalchemy import func
    print(f"\nalarm_severity 分布：")
    rows = db.query(
        DT_ALARM_EVENT.alarm_severity,
        func.count("*").label("cnt")
    ).group_by(DT_ALARM_EVENT.alarm_severity).all()
    for r in rows:
        print(f"  {r.alarm_severity}: {r.cnt} 条")

    # 前 5 条样例
    q = db.query(DT_ALARM_EVENT)
    if machine_id:
        q = q.filter(DT_ALARM_EVENT.tool_id == machine_id)
    alarms = q.order_by(DT_ALARM_EVENT.start_ts_utc.desc()).limit(5).all()
    _print_list(alarms, f"最近告警 machine={machine_id or 'ALL'}")


def check_lots_and_recipes(db, machine_id=None):
    """检查6: lots + recipes 表"""
    print(f"\n{SEP}")
    print("【检查6】lots + recipes 表 - 批次与配方")
    print(SEP)

    lot_total = db.query(Lot).count()
    recipe_total = db.query(Recipe).count()
    print(f"lots 总数: {lot_total}")
    print(f"recipes 总数: {recipe_total}")

    # Lot 状态分布
    from sqlalchemy import func
    print(f"\nLot status 分布：")
    rows = db.query(Lot.status, func.count("*").label("cnt")).group_by(Lot.status).all()
    for r in rows:
        print(f"  {r.status}: {r.cnt} 条")

    # 配方表是否为空
    if recipe_total == 0:
        print("\n⚠️ recipes 表为空 → _query_recipe 只能继续硬编码或返回提示")
    else:
        print(f"\nrecipes 样例：")
        recipes = db.query(Recipe).limit(3).all()
        for r in recipes:
            print(f"  id={r.id}, machine_id={r.machine_id}, name={r.name}, temp={r.temperature}")

    # 指定机台的最近 5 个 Lot
    if machine_id:
        lots = db.query(Lot).filter(Lot.machine_id == machine_id).order_by(Lot.start_time.desc()).limit(5).all()
        _print_list(lots, f"机台 {machine_id} 最近 5 个 Lot")


def check_tool_mapping(db, machine_id=None):
    """检查7: MachineToolMapping 表 - 机台与 tool_id 映射"""
    print(f"\n{SEP}")
    print("【检查7】MachineToolMapping 表 - 机台ID ↔ tool_id 映射")
    print(SEP)

    try:
        total = db.query(MachineToolMapping).count()
        print(f"总记录数: {total}")
    except Exception as e:
        print(f"❌ 表不存在或查询失败: {e}")
        print("  （生产 Oracle 可能没有此表，代码里已加 try-except 兜底）")
        return

    if total == 0:
        print("⚠️ 表为空，AI 查询时 machine_id 与 tool_id 需要手工对应")
        return

    mappings = db.query(MachineToolMapping).limit(10).all()
    print(f"\n映射样例：")
    for m in mappings:
        print(f"  machine_id={m.machine_id} ↔ tool_id={m.tool_id}")


def check_ai_config_status():
    """检查8: 当前 AI 配置状态（验证 OpenAI 不工作的根因）"""
    print(f"\n{SEP}")
    print("【检查8】AI 配置状态（验证 OpenAI 不工作的根因）")
    print(SEP)

    from config import (
        AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
        AI_TEMPERATURE, AI_MAX_TOKENS,
        DIFY_ENABLED, DIFY_BASE_URL,
        N8N_ENABLED, N8N_BASE_URL,
    )

    print(f"AI_PROVIDER       = {AI_PROVIDER!r}")
    print(f"AI_BASE_URL       = {AI_BASE_URL!r}")
    print(f"AI_API_KEY        = {'(已设置, len=' + str(len(AI_API_KEY)) + ')' if AI_API_KEY else '(空!)'}")
    print(f"AI_MODEL          = {AI_MODEL!r}")
    print(f"AI_TEMPERATURE    = {AI_TEMPERATURE}")
    print(f"AI_MAX_TOKENS     = {AI_MAX_TOKENS}")
    print(f"DIFY_ENABLED      = {DIFY_ENABLED}, DIFY_BASE_URL={DIFY_BASE_URL!r}")
    print(f"N8N_ENABLED       = {N8N_ENABLED}, N8N_BASE_URL={N8N_BASE_URL!r}")

    print(f"\n根因诊断：")
    if AI_PROVIDER != "openai":
        print(f"  ❌ provider 不是 openai（当前={AI_PROVIDER}）→ 走本地规则引擎，OpenAI 根本没被调用")
    elif not AI_BASE_URL or not AI_API_KEY:
        print(f"  ❌ provider=openai 但 base_url 或 api_key 为空 → 回退本地规则")
    else:
        print(f"  ✅ provider=openai 且配置完整")
        # 检查 base_url 路径
        if "openai.com" in AI_BASE_URL and "/v1" not in AI_BASE_URL:
            print(f"  ⚠️ OpenAI 官方地址需以 /v1 结尾，当前={AI_BASE_URL}")
        elif "bigmodel.cn" in AI_BASE_URL and "/v4" not in AI_BASE_URL:
            print(f"  ⚠️ 智谱 GLM 地址需含 /api/paas/v4，当前={AI_BASE_URL}")


def main():
    machine_id = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"\n{'#' * 70}")
    print(f"# FabTwin AI 数据源自测脚本")
    print(f"# 时间: {datetime.now().isoformat()}")
    print(f"# 目标机台: {machine_id or '(全部)'}")
    print(f"{'#' * 70}")

    db = SessionLocal()
    try:
        check_ai_config_status()
        check_machine_table(db, machine_id)
        check_dt_state_snapshot(db, machine_id)
        check_dt_event_raw(db, machine_id)
        check_dt_event_std(db, machine_id)
        check_dt_alarm_event(db, machine_id)
        check_lots_and_recipes(db, machine_id)
        check_tool_mapping(db, machine_id)

        print(f"\n{'#' * 70}")
        print("# 自测完成。请把以上输出贴给我，我会根据真实数据结构改造 AI 规则引擎")
        print(f"{'#' * 70}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
