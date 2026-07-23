"""AI 工具层：统一数据访问（本地规则引擎 + OpenAI Function Calling 共用）

所有数据查询函数都返回 dict，格式统一：
{
    "answer": "给用户看的自然语言回答",
    "sql": "对应的SQL（调试用）",
    "jump_timestamp": "可跳转回放的时间戳（可选）",
    "table_data": {"headers": [...], "rows": [...]}  # 表格数据（可选）
}

数据源优先级：
1. DT_EVENT_RAW（21万条真实VFEI事件）→ 机台状态/事件时间线/告警
2. lots（567条真实批次）→ Lot查询/产量统计
3. recipes（76条真实配方）→ 工艺配方
4. machines（56台机台主数据）→ 基础信息（id/name/state）
"""
import json
import re
from datetime import datetime
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models import (
    Machine, Lot, Recipe, Alarm,
    DT_EVENT_RAW, DT_EVENT_RAW_CUR,
    DT_STATE_SNAPSHOT, DT_ALARM_EVENT,
)


def _parse_payload(payload_json: str) -> dict:
    """安全解析 payload_json"""
    if not payload_json:
        return {}
    try:
        return json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _is_null(val) -> bool:
    """判断值是否为空（Oracle 中 'NULL' 字符串也算空）"""
    if val is None:
        return True
    if isinstance(val, str) and val.strip().upper() in ("NULL", "", "NONE"):
        return True
    return False


def _resolve_tool_ids(db: Session, machine_id: str) -> list:
    """获取机台对应的 tool_id 列表（前缀匹配 + MachineToolMapping）"""
    tool_ids = [machine_id]
    # PODOPENER 系列特殊处理：PODOPENER-1 也匹配 PODOPENER
    if machine_id.upper().startswith("PODOPENER"):
        tool_ids.append("PODOPENER")
    # 尝试 MachineToolMapping（生产可能没有此表）
    try:
        from models import MachineToolMapping
        mappings = db.query(MachineToolMapping).filter(
            (MachineToolMapping.machine_id == machine_id) |
            (MachineToolMapping.tool_id == machine_id)
        ).all()
        for m in mappings:
            tool_ids.append(m.tool_id)
            tool_ids.append(m.machine_id)
    except Exception:
        pass
    return list(set(tool_ids))


# ==================== 工具1: 机台状态 ====================

def get_machine_status(db: Session, machine_id: str = None) -> dict:
    """查询机台实时状态（从 DT_EVENT_RAW 最新事件取真实状态）"""
    if not machine_id:
        # 全厂概览
        machines = db.query(Machine).all()
        running = sum(1 for m in machines if m.state == "run")
        idle = sum(1 for m in machines if m.state == "idle")
        maint = sum(1 for m in machines if m.state == "maint")

        # 从 DT_EVENT_RAW 取最近有事件的前 5 台机台
        recent_tools = db.query(
            DT_EVENT_RAW.tool_id,
            func.max(DT_EVENT_RAW.received_ts_utc).label("last_ts")
        ).group_by(DT_EVENT_RAW.tool_id).order_by(
            func.max(DT_EVENT_RAW.received_ts_utc).desc()
        ).limit(5).all()

        answer = (
            f"当前厂区共 {len(machines)} 台机台：\n"
            f"• 运行中：{running} 台\n"
            f"• 空闲：{idle} 台\n"
            f"• 维护：{maint} 台\n\n"
            f"最近有活动的机台：\n"
        )
        for t in recent_tools:
            answer += f"  • {t.tool_id}（最后事件: {t.last_ts}）\n"
        answer += "\n可以问我具体某台机台的详细状态。"

        return {
            "answer": answer,
            "sql": "SELECT state, COUNT(*) FROM machines GROUP BY state",
        }

    # 单台机台：machines 基础信息 + DT_EVENT_RAW 最新事件
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        return {"answer": f"未找到机台 {machine_id}", "sql": ""}

    # 从 DT_EVENT_RAW 取最新 1 条事件
    tool_ids = _resolve_tool_ids(db, machine_id)
    latest_event = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.tool_id.in_(tool_ids)
    ).order_by(DT_EVENT_RAW.raw_id.desc()).first()

    answer = f"机台 {m.id}"
    if m.name:
        answer += f"（{m.name}）"
    answer += f" 当前状态：\n"

    # 基础信息（真实）
    state_cn = {"run": "运行中", "idle": "空闲", "maint": "维护中", "down": "停机"}.get(m.state, m.state)
    answer += f"• 状态：{state_cn}\n"
    answer += f"• 工艺类型：{m.process_type}\n"

    # 从最新事件取真实状态
    if latest_event:
        payload = _parse_payload(latest_event.payload_json)
        answer += f"• 最新事件：{payload.get('event_name', '未知')}\n"
        answer += f"• 事件状态：{payload.get('machine_state', '未知')}\n"
        if not _is_null(payload.get("machine_mode")):
            answer += f"• 运行模式：{payload.get('machine_mode')}\n"
        if not _is_null(payload.get("lot_id")):
            answer += f"• 当前 Lot：{payload.get('lot_id')}\n"
        if not _is_null(payload.get("cassette_id")):
            answer += f"• Cassette：{payload.get('cassette_id')}\n"
        if not _is_null(payload.get("alarm_code")):
            answer += f"• 告警代码：{payload.get('alarm_code')}\n"
        answer += f"• 最后更新：{latest_event.received_ts_utc}\n"
    else:
        answer += "• 暂无实时事件数据\n"

    # 传感器数据说明（诚实告知）
    answer += "\n（注：当前系统采集VFEI事件流，不含温度/压力等传感器数据）"

    return {
        "answer": answer,
        "sql": f"SELECT * FROM machines WHERE id='{machine_id}' "
               f"UNION SELECT * FROM dt_event_raw WHERE tool_id='{machine_id}' ORDER BY raw_id DESC LIMIT 1",
        "jump_timestamp": latest_event.received_ts_utc if latest_event else m.updated_at,
    }


# ==================== 工具2: 告警查询 ====================

def get_machine_alarms(db: Session, machine_id: str = None, limit: int = 20) -> dict:
    """查询告警（从 DT_EVENT_RAW 中 alarm_code IS NOT NULL 的事件提取）"""
    tool_ids = _resolve_tool_ids(db, machine_id) if machine_id else None

    # 从 DT_EVENT_RAW payload 中查告警事件
    # 用原生 SQL 提取 JSON 中的 alarm_code（Oracle 12c+ 可用 JSON_VALUE，10g 用 LIKE）
    try:
        if tool_ids:
            # 查有告警的事件
            sql = text("""
                SELECT raw_id, tool_id, received_ts_utc, payload_json
                FROM dt_event_raw
                WHERE tool_id IN :tool_ids
                  AND payload_json LIKE '%"alarm_code":%'
                  AND payload_json NOT LIKE '%"alarm_code": null%'
                  AND payload_json NOT LIKE '%"alarm_code":"null"%'
                  AND rownum <= :limit
                ORDER BY raw_id DESC
            """)
            rows = db.execute(sql, {"tool_ids": tuple(tool_ids) if len(tool_ids) > 1 else tool_ids[0],
                                    "limit": limit * 3}).fetchall()
        else:
            sql = text("""
                SELECT raw_id, tool_id, received_ts_utc, payload_json
                FROM dt_event_raw
                WHERE payload_json LIKE '%"alarm_code":%'
                  AND payload_json NOT LIKE '%"alarm_code": null%'
                  AND payload_json NOT LIKE '%"alarm_code":"null"%'
                  AND rownum <= :limit
                ORDER BY raw_id DESC
            """)
            rows = db.execute(sql, {"limit": limit * 3}).fetchall()
    except Exception:
        # 回退到 alarms 表
        return _get_alarms_fallback(db, machine_id, limit)

    # 解析 payload 提取告警信息
    alarms = []
    for r in rows:
        payload = _parse_payload(r.payload_json)
        alarm_code = payload.get("alarm_code")
        if _is_null(alarm_code):
            continue
        alarms.append({
            "timestamp": r.received_ts_utc,
            "tool_id": r.tool_id,
            "alarm_code": alarm_code,
            "alarm_text": payload.get("alarm_text", ""),
            "lot_id": payload.get("lot_id", ""),
            "machine_state": payload.get("machine_state", ""),
        })
        if len(alarms) >= limit:
            break

    if not alarms:
        scope = f"机台 {machine_id}" if machine_id else "全厂"
        return {"answer": f"{scope} 暂无告警记录。", "sql": ""}

    scope = f"机台 {machine_id}" if machine_id else "全厂"
    answer = f"{scope} 告警统计（从事件流提取，最近 {len(alarms)} 条）：\n"

    # 统计告警类型分布
    code_counts = {}
    for a in alarms:
        code = a["alarm_code"]
        code_counts[code] = code_counts.get(code, 0) + 1
    answer += "• 告警类型分布：\n"
    for code, cnt in sorted(code_counts.items(), key=lambda x: -x[1]):
        answer += f"  {code}: {cnt} 次\n"

    # 表格数据（前 10 条）
    table_data = {
        "headers": ["时间", "机台", "告警代码", "告警描述", "Lot"],
        "rows": [
            [a["timestamp"], a["tool_id"], a["alarm_code"], a["alarm_text"], a["lot_id"]]
            for a in alarms[:10]
        ],
    }

    answer += f"\n最近 {min(10, len(alarms))} 条告警见下表。"

    return {
        "answer": answer,
        "sql": "SELECT * FROM dt_event_raw WHERE payload_json LIKE '%alarm_code%' ORDER BY raw_id DESC",
        "table_data": table_data,
        "jump_timestamp": alarms[0]["timestamp"] if alarms else None,
    }


def _get_alarms_fallback(db: Session, machine_id: str = None, limit: int = 20) -> dict:
    """告警查询回退：使用 alarms 表"""
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)
    alarms = q.order_by(Alarm.timestamp.desc()).limit(limit).all()

    if not alarms:
        scope = f"机台 {machine_id}" if machine_id else "全厂"
        return {"answer": f"{scope} 暂无告警记录。", "sql": ""}

    scope = f"机台 {machine_id}" if machine_id else "全厂"
    crit = sum(1 for a in alarms if a.level == "crit")
    warn = sum(1 for a in alarms if a.level == "warn")
    unresolved = sum(1 for a in alarms if not a.resolved)

    table_data = {
        "headers": ["时间", "描述", "等级", "状态"],
        "rows": [
            [a.timestamp, a.description, a.level, "未解决" if not a.resolved else "已解决"]
            for a in alarms[:10]
        ],
    }

    answer = (
        f"{scope} 告警统计（最近{len(alarms)}条）：\n"
        f"• 严重：{crit} 条\n"
        f"• 警告：{warn} 条\n"
        f"• 未解决：{unresolved} 条\n\n"
        f"最近 10 条告警见下表。"
    )

    return {
        "answer": answer,
        "sql": f"SELECT * FROM alarms{' WHERE machine_id=' + repr(machine_id) if machine_id else ''} ORDER BY timestamp DESC",
        "table_data": table_data,
        "jump_timestamp": alarms[0].timestamp if alarms else None,
    }


# ==================== 工具3: 事件时间线（替代温度趋势） ====================

def get_event_timeline(db: Session, machine_id: str = None, limit: int = 20) -> dict:
    """查询事件时间线（DB 无传感器数据，用事件分布替代温度趋势）"""
    if not machine_id:
        return {"answer": "请指定机台 ID 以查询事件时间线。", "sql": ""}

    tool_ids = _resolve_tool_ids(db, machine_id)
    events = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.tool_id.in_(tool_ids)
    ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(limit).all()

    if not events:
        return {"answer": f"机台 {machine_id} 暂无事件记录。", "sql": ""}

    # 统计事件类型分布
    event_counts = {}
    mode_counts = {}
    for e in events:
        payload = _parse_payload(e.payload_json)
        event_name = payload.get("event_name", "未知")
        machine_mode = payload.get("machine_mode", "未知")
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
        if not _is_null(machine_mode):
            mode_counts[machine_mode] = mode_counts.get(machine_mode, 0) + 1

    answer = f"机台 {machine_id} 事件时间线（最近 {len(events)} 条）：\n\n"

    answer += "• 事件类型分布：\n"
    for name, cnt in sorted(event_counts.items(), key=lambda x: -x[1]):
        answer += f"  {name}: {cnt} 次\n"

    if mode_counts:
        answer += "\n• 运行模式分布：\n"
        for mode, cnt in sorted(mode_counts.items(), key=lambda x: -x[1]):
            answer += f"  {mode}: {cnt} 次\n"

    # 表格数据
    table_data = {
        "headers": ["时间", "事件", "状态", "模式", "Lot", "Cassette"],
        "rows": [],
    }
    for e in events[:10]:
        p = _parse_payload(e.payload_json)
        table_data["rows"].append([
            e.received_ts_utc,
            p.get("event_name", ""),
            p.get("machine_state", ""),
            p.get("machine_mode", "") if not _is_null(p.get("machine_mode")) else "",
            p.get("lot_id", "") if not _is_null(p.get("lot_id")) else "",
            p.get("cassette_id", "") if not _is_null(p.get("cassette_id")) else "",
        ])

    answer += f"\n最近 {min(10, len(events))} 条事件见下表。"

    return {
        "answer": answer,
        "sql": f"SELECT * FROM dt_event_raw WHERE tool_id IN {tuple(tool_ids)} ORDER BY raw_id DESC LIMIT {limit}",
        "table_data": table_data,
        "jump_timestamp": events[0].received_ts_utc if events else None,
    }


# ==================== 工具4: 产量统计 ====================

def get_yield_stats(db: Session, machine_id: str = None) -> dict:
    """查询产量统计（从 lots 表取真实数据）"""
    q = db.query(Lot)
    if machine_id:
        q = q.filter(Lot.machine_id == machine_id)
    lots = q.all()

    if not lots:
        scope = f"机台 {machine_id}" if machine_id else "全厂"
        return {"answer": f"{scope} 暂无 Lot 记录。", "sql": ""}

    lot_count = len(lots)
    done = sum(1 for l in lots if l.status == "done")
    processing = sum(1 for l in lots if l.status == "processing")
    pending = sum(1 for l in lots if l.status == "pending")
    total_wafers = sum(l.wafer_count for l in lots if l.wafer_count)

    scope = f"机台 {machine_id}" if machine_id else "全厂"

    # 最近 5 个 Lot
    recent_q = db.query(Lot)
    if machine_id:
        recent_q = recent_q.filter(Lot.machine_id == machine_id)
    recent_lots = recent_q.order_by(Lot.start_time.desc()).limit(5).all()

    table_data = {
        "headers": ["Lot ID", "机台", "产品", "晶圆数", "状态", "开始时间"],
        "rows": [
            [l.id, l.machine_id, l.product, l.wafer_count, l.status, l.start_time]
            for l in recent_lots
        ],
    }

    answer = (
        f"{scope} 产量统计（真实数据）：\n"
        f"• Lot 批次：{lot_count} 个\n"
        f"• 已完成：{done} 个\n"
        f"• 加工中：{processing} 个\n"
        f"• 等待中：{pending} 个\n"
        f"• 累计晶圆：{total_wafers} 片\n\n"
        f"最近 5 个 Lot 见下表。"
    )

    where = f" WHERE machine_id='{machine_id}'" if machine_id else ""
    return {
        "answer": answer,
        "sql": f"SELECT COUNT(*), SUM(wafer_count) FROM lots{where}",
        "table_data": table_data,
    }


# ==================== 工具5: Lot 查询 ====================

def get_lot_info(db: Session, lot_id: str = None, machine_id: str = None) -> dict:
    """查询 Lot 信息（从 lots 表 + DT_EVENT_RAW 事件）"""
    if lot_id:
        # 查指定 Lot
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if lot:
            status_cn = {
                "done": "已完成", "processing": "加工中",
                "pending": "等待中", "hold": "暂停"
            }.get(lot.status, lot.status)

            answer = (
                f"Lot {lot.id} 详情：\n"
                f"• 机台：{lot.machine_id}\n"
                f"• 产品：{lot.product}\n"
                f"• 晶圆数：{lot.wafer_count} 片\n"
                f"• 状态：{status_cn}\n"
                f"• 开始时间：{lot.start_time}\n"
                f"• 结束时间：{lot.end_time or '进行中'}\n"
                f"• 工艺配方：{lot.recipe_id or '未指定'}"
            )

            # 从 DT_EVENT_RAW 查该 Lot 的事件记录
            try:
                events = db.query(DT_EVENT_RAW).filter(
                    DT_EVENT_RAW.payload_json.like(f'%{lot_id}%')
                ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(5).all()
                if events:
                    answer += f"\n\n相关事件（最近 {len(events)} 条）："
                    for e in events:
                        p = _parse_payload(e.payload_json)
                        answer += f"\n  • {e.received_ts_utc} - {p.get('event_name', '')} ({e.tool_id})"
            except Exception:
                pass

            return {
                "answer": answer,
                "sql": f"SELECT * FROM lots WHERE id='{lot_id}'",
                "jump_timestamp": lot.start_time,
            }
        return {"answer": f"未找到 Lot {lot_id}。", "sql": ""}

    # 未指定 Lot ID，列出最近的
    q = db.query(Lot)
    if machine_id:
        q = q.filter(Lot.machine_id == machine_id)
    lots = q.order_by(Lot.id.desc()).limit(10).all()

    if not lots:
        return {"answer": "未找到相关 Lot 记录。", "sql": ""}

    table_data = {
        "headers": ["Lot ID", "机台", "产品", "状态", "开始时间"],
        "rows": [
            [l.id, l.machine_id, l.product, l.status, l.start_time]
            for l in lots
        ],
    }

    answer = f"最近 {len(lots)} 个 Lot：\n"
    answer += "（点击下方表格或输入 Lot ID 查看详情）"

    return {
        "answer": answer,
        "sql": "SELECT * FROM lots ORDER BY start_time DESC LIMIT 10",
        "table_data": table_data,
        "jump_timestamp": lots[0].start_time if lots else None,
    }


# ==================== 工具6: 工艺配方 ====================

def get_recipe_info(db: Session, machine_id: str = None) -> dict:
    """查询工艺配方（从 recipes 表取真实数据，不再硬编码）"""
    if not machine_id:
        # 列出所有配方类型
        recipes = db.query(Recipe).all()
        if not recipes:
            return {"answer": "配方表为空。", "sql": ""}

        # 按工艺类型分组统计
        type_counts = {}
        for r in recipes:
            t = r.process_type or "未分类"
            type_counts[t] = type_counts.get(t, 0) + 1

        answer = f"共有 {len(recipes)} 个配方，按工艺类型分布：\n"
        for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            answer += f"  • {t}: {cnt} 个\n"
        answer += "\n请指定机台 ID 查看具体配方。"
        return {"answer": answer, "sql": "SELECT process_type, COUNT(*) FROM recipes GROUP BY process_type"}

    # 查指定机台的配方
    recipes = db.query(Recipe).filter(Recipe.machine_id == machine_id).all()
    if not recipes:
        # 尝试模糊匹配（如 WAT-01 匹配 REC-ETCH-A-WAT-01）
        recipes = db.query(Recipe).filter(
            Recipe.id.like(f"%{machine_id}%")
        ).all()

    if not recipes:
        return {"answer": f"机台 {machine_id} 暂无配方数据。\n\n（配方需在 MES/RCMS 系统中下发）", "sql": ""}

    answer = f"机台 {machine_id} 工艺配方（共 {len(recipes)} 个）：\n\n"
    table_data = {
        "headers": ["配方ID", "名称", "温度(°C)", "压力(Pa)", "RF功率(W)", "气体(sccm)", "时间(秒)"],
        "rows": [],
    }
    for r in recipes:
        answer += f"• {r.name or r.id}：{r.temperature}°C / {r.pressure}Pa / {r.rf_power}W\n"
        table_data["rows"].append([
            r.id, r.name, r.temperature, r.pressure, r.rf_power, r.gas_flow, r.process_time
        ])

    return {
        "answer": answer,
        "sql": f"SELECT * FROM recipes WHERE machine_id='{machine_id}'",
        "table_data": table_data,
    }


# ==================== OpenAI Function Calling 工具定义 ====================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_machine_status",
            "description": "查询机台实时状态，包括最新事件、运行模式、当前Lot。不传machine_id则返回全厂概览。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID，如 PODOPENER-1。不传则查询全厂。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_machine_alarms",
            "description": "查询机台告警记录，从VFEI事件流中提取alarm_code非空的事件。不传machine_id则查询全厂。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID，如 PODOPENER-1。不传则查询全厂。"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回告警条数上限，默认20",
                        "default": 20
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_timeline",
            "description": "查询机台事件时间线，包括事件类型分布和运行模式分布。注意：系统采集VFEI事件流，不含温度/压力等传感器数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID，如 PODOPENER-1"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回事件条数上限，默认20",
                        "default": 20
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_yield_stats",
            "description": "查询产量统计，包括Lot数量、晶圆总数、完成率。不传machine_id则查询全厂。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID。不传则查询全厂。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_lot_info",
            "description": "查询Lot批次信息。可按lot_id查询单个批次，或按machine_id列出该机台最近的Lot。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lot_id": {
                        "type": "string",
                        "description": "Lot ID，如 V3TY2。不传则列出最近的Lot。"
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID，用于筛选该机台的Lot"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe_info",
            "description": "查询工艺配方，包括温度、压力、RF功率、气体流量、工艺时间。不传machine_id则列出所有配方类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "机台ID。不传则列出所有配方类型。"
                    }
                },
                "required": []
            }
        }
    },
]

# 工具名 → 处理函数映射
TOOL_HANDLERS = {
    "get_machine_status": get_machine_status,
    "get_machine_alarms": get_machine_alarms,
    "get_event_timeline": get_event_timeline,
    "get_yield_stats": get_yield_stats,
    "get_lot_info": get_lot_info,
    "get_recipe_info": get_recipe_info,
}
