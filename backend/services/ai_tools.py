"""AI 工具层：统一数据访问（本地规则引擎 + OpenAI Function Calling 共用）

所有数据查询函数都返回 dict，格式统一：
{
    "answer": "给用户看的自然语言回答",
    "sql": "对应的SQL（调试用）",
    "jump_timestamp": "可跳转回放的时间戳（可选）",
    "table_data": {"headers": [...], "rows": [...]}  # 表格数据（可选）
}

数据源（生产环境真实数据）：
1. DT_EVENT_RAW（21万条 VFEI 事件）→ 机台状态/事件时间线/告警/Lot 提取
2. DT_EVENT_RAW_CUR（当前事件快照）→ 实时状态补充
3. machines（机台主数据）→ 仅 id/name/state 基础信息

注意：lots/alarms/recipes/DT_ALARM_EVENT/DT_STATE_SNAPSHOT 均为假数据，不查询
"""
import json
import re
import time
from datetime import datetime
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models import Machine, DT_EVENT_RAW
from services.time_utils import normalize_ts


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


def _format_ts(ts) -> str:
    """将时间戳标准化为 'YYYY-MM-DD HH:MM:SS' 格式

    使用 normalize_ts 处理所有格式（datetime对象、ISO格式、Oracle NLS中文格式等），
    确保前端能正确解析日期和跳转。
    """
    if ts is None:
        return None
    return normalize_ts(ts) or None


def _resolve_tool_ids(db: Session, machine_id: str) -> list:
    """获取机台对应的 tool_id 列表（前缀匹配 + MachineToolMapping）"""
    tool_ids = [machine_id]
    upper_id = machine_id.upper() if machine_id else ""
    # PODOPENER 系列特殊处理：PODOPENER-1 也匹配 PODOPENER
    if upper_id.startswith("PODOPENER"):
        tool_ids.append("PODOPENER")
    # OXE 系列特殊处理：OXE-61 也匹配 OXE 前缀
    if upper_id.startswith("OXE"):
        tool_ids.append("OXE")
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


# ALARM 类事件名：port_id/chamber_id 等字段被错误填充为告警描述词，需清空
_ALARM_EVENT_NAMES = {"ALARM_REPORT", "EC_ALARM_REPORT"}
# ALARM 事件需要清空的字段（这些字段在 ALARM 报文中是错误解析的描述词）
_ALARM_FIELDS_TO_CLEAR = (
    "port_id", "chamber_id", "cassette_id", "smif_id",
    "slot_id", "wafer_id", "pod_id", "unit_id", "batch_id",
)


def clean_alarm_event(payload: dict) -> dict:
    """清理 ALARM 事件中被错误填充的字段

    量产 DB 中 ALARM_REPORT/EC_ALARM_REPORT 事件的 port_id/chamber_id 等字段
    被 bridge.py 错误填充为告警描述词（如 "AGC"/"Time"/"Sensor-2"），
    需清空这些字段，只保留 alarm_text/alarm_code 等告警字段。

    与 oxe.py 中的 _convert_event 保持一致，提取为公共函数供 AI 工具复用。
    """
    if not payload:
        return payload
    event_name = str(payload.get("event_name", "")).upper().strip()
    if event_name in _ALARM_EVENT_NAMES:
        for field in _ALARM_FIELDS_TO_CLEAR:
            if field in payload:
                payload[field] = "NULL"
    return payload


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
        "jump_timestamp": _format_ts(latest_event.received_ts_utc if latest_event else m.updated_at),
        "jump_machine_id": m.id,
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
        # 清理 ALARM_REPORT/EC_ALARM_REPORT 事件中被错误填充的字段（与 oxe.py 保持一致）
        payload = clean_alarm_event(payload)
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
        "jump_machine_id": machine_id,
    }


def _get_alarms_fallback(db: Session, machine_id: str = None, limit: int = 20) -> dict:
    """告警查询回退：用 Python 解析 payload（兼容 Oracle 10g，不查假数据 alarms 表）"""
    tool_ids = _resolve_tool_ids(db, machine_id) if machine_id else None

    q = db.query(DT_EVENT_RAW)
    if tool_ids:
        q = q.filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
    events = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(limit * 5).all()

    alarms = []
    for e in events:
        payload = _parse_payload(e.payload_json)
        # 清理 ALARM_REPORT/EC_ALARM_REPORT 事件中被错误填充的字段（与主路径保持一致）
        payload = clean_alarm_event(payload)
        alarm_code = payload.get("alarm_code")
        if alarm_code and alarm_code.upper() not in ("NULL", ""):
            alarms.append({
                "timestamp": e.received_ts_utc,
                "tool_id": e.tool_id,
                "alarm_code": alarm_code,
                "alarm_text": payload.get("alarm_text", ""),
                "lot_id": payload.get("lot_id", ""),
            })
            if len(alarms) >= limit:
                break

    if not alarms:
        scope = f"机台 {machine_id}" if machine_id else "全厂"
        return {"answer": f"{scope} 暂无告警记录。", "sql": ""}

    scope = f"机台 {machine_id}" if machine_id else "全厂"
    answer = f"{scope} 告警统计（从事件流提取）：\n"

    code_counts = {}
    for a in alarms:
        code_counts[a["alarm_code"]] = code_counts.get(a["alarm_code"], 0) + 1
    answer += "• 告警类型分布：\n"
    for code, cnt in sorted(code_counts.items(), key=lambda x: -x[1]):
        answer += f"  {code}: {cnt} 次\n"

    table_data = {
        "headers": ["时间", "机台", "告警代码", "描述", "Lot"],
        "rows": [
            [a["timestamp"], a["tool_id"], a["alarm_code"], a["alarm_text"], a["lot_id"]]
            for a in alarms[:10]
        ],
    }

    return {
        "answer": answer,
        "sql": "",
        "table_data": table_data,
        "jump_timestamp": alarms[0]["timestamp"] if alarms else None,
        "jump_machine_id": machine_id,
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
        "jump_timestamp": _format_ts(events[0].received_ts_utc) if events else None,
        "jump_machine_id": machine_id,
    }


# ==================== 工具4: 产量统计（从 DT_EVENT_RAW 聚合） ====================

def get_yield_stats(db: Session, machine_id: str = None) -> dict:
    """查询产量统计（从 DT_EVENT_RAW 的 lot_id 字段聚合真实数据）"""
    tool_ids = _resolve_tool_ids(db, machine_id) if machine_id else None

    # 从 DT_EVENT_RAW 提取唯一 lot_id
    try:
        if tool_ids:
            sql = text("""
                SELECT DISTINCT JSON_VALUE(payload_json, '$.lot_id') as lot_id,
                       tool_id
                FROM dt_event_raw
                WHERE tool_id IN :tool_ids
                  AND payload_json LIKE '%"lot_id":%'
                  AND JSON_VALUE(payload_json, '$.lot_id') IS NOT NULL
                  AND JSON_VALUE(payload_json, '$.lot_id') NOT IN ('NULL', 'null', '')
            """)
            rows = db.execute(sql, {"tool_ids": tuple(tool_ids) if len(tool_ids) > 1 else tool_ids[0]}).fetchall()
        else:
            sql = text("""
                SELECT DISTINCT JSON_VALUE(payload_json, '$.lot_id') as lot_id,
                       tool_id
                FROM dt_event_raw
                WHERE payload_json LIKE '%"lot_id":%'
                  AND JSON_VALUE(payload_json, '$.lot_id') IS NOT NULL
                  AND JSON_VALUE(payload_json, '$.lot_id') NOT IN ('NULL', 'null', '')
                  AND rownum <= 10000
            """)
            rows = db.execute(sql).fetchall()
    except Exception as e:
        # JSON_VALUE 不支持（Oracle 10g），用 Python 解析
        return _get_yield_stats_fallback(db, machine_id)

    # 统计唯一 lot_id
    lot_ids = set()
    lot_tools = {}  # lot_id -> [tool_ids]
    for r in rows:
        lot = r.lot_id
        if lot and lot.upper() not in ("NULL", ""):
            lot_ids.add(lot)
            if lot not in lot_tools:
                lot_tools[lot] = set()
            lot_tools[lot].add(r.tool_id)

    lot_count = len(lot_ids)
    scope = f"机台 {machine_id}" if machine_id else "全厂"

    if lot_count == 0:
        return {"answer": f"{scope} 暂无 Lot 记录。", "sql": ""}

    # 统计每个机台处理的 Lot 数
    tool_lot_counts = {}
    for lot, tools in lot_tools.items():
        for t in tools:
            tool_lot_counts[t] = tool_lot_counts.get(t, 0) + 1

    answer = (
        f"{scope} 产量统计（从事件流提取真实数据）：\n"
        f"• Lot 批次：{lot_count} 个（唯一 lot_id）\n"
    )
    if machine_id:
        answer += f"• 机台：{machine_id}\n"
    else:
        # 全厂统计时，显示各机台 Lot 数量
        answer += f"\n各机台 Lot 数量：\n"
        for tid, cnt in sorted(tool_lot_counts.items(), key=lambda x: -x[1])[:10]:
            answer += f"  {tid}: {cnt} 个\n"

    # 最近 10 个 Lot 的表格
    recent_lots = list(lot_ids)[:10]
    table_data = {
        "headers": ["Lot ID", "关联机台"],
        "rows": [
            [lot, ", ".join(lot_tools.get(lot, set()))]
            for lot in recent_lots
        ],
    }

    return {
        "answer": answer,
        "sql": "SELECT DISTINCT lot_id FROM dt_event_raw payload_json",
        "table_data": table_data,
    }


def _get_yield_stats_fallback(db: Session, machine_id: str = None) -> dict:
    """产量统计回退：用 Python 解析 payload（兼容 Oracle 10g）"""
    tool_ids = _resolve_tool_ids(db, machine_id) if machine_id else None

    q = db.query(DT_EVENT_RAW)
    if tool_ids:
        q = q.filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
    events = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(5000).all()

    lot_ids = set()
    lot_tools = {}
    for e in events:
        payload = _parse_payload(e.payload_json)
        lot = payload.get("lot_id")
        if lot and lot.upper() not in ("NULL", ""):
            lot_ids.add(lot)
            if lot not in lot_tools:
                lot_tools[lot] = set()
            lot_tools[lot].add(e.tool_id)

    lot_count = len(lot_ids)
    scope = f"机台 {machine_id}" if machine_id else "全厂"

    if lot_count == 0:
        return {"answer": f"{scope} 暂无 Lot 记录。", "sql": ""}

    answer = f"{scope} 产量统计（从事件流提取）：\n• Lot 批次：{lot_count} 个\n"

    table_data = {
        "headers": ["Lot ID", "关联机台"],
        "rows": [[lot, ", ".join(lot_tools.get(lot, set()))] for lot in list(lot_ids)[:10]],
    }

    return {"answer": answer, "sql": "", "table_data": table_data}


# ==================== 工具5: Lot 查询（MES + 设备事件双源融合） ====================

def _extract_n8n_output(run_data: dict) -> dict:
    """从 N8N get_execution 的 runData 中提取最终输出"""
    if not isinstance(run_data, dict):
        return None

    priority_nodes = ["Build Success Response", "Respond to Webhook", "Respond"]
    skip_nodes = {"Webhook", "Execute Workflow Trigger", "When Executed by Another Workflow",
                  "Start", "Merge", "IF", "If", "Need Clarification?", "Query Success?", "Normalize Request"}

    def _extract(node_runs):
        if not isinstance(node_runs, list) or not node_runs:
            return None
        last_run = node_runs[-1]
        if not isinstance(last_run, dict):
            return None
        output_data = last_run.get("data", {}).get("main", [])
        if not isinstance(output_data, list):
            return None
        for item_list in reversed(output_data):
            if isinstance(item_list, list) and item_list:
                for item in item_list:
                    if isinstance(item, dict) and "json" in item:
                        return item["json"]
        return None

    # 优先查找
    for target in priority_nodes:
        if target in run_data:
            result = _extract(run_data[target])
            if result:
                return result

    # 兜底：找最后一个非跳过节点
    for node_name, node_runs in reversed(run_data.items()):
        if node_name in skip_nodes:
            continue
        result = _extract(node_runs)
        if result:
            return result
    return None


def get_mes_lot_info(db: Session, lot_id: str) -> dict:
    """通过 MCP 调用 N8N MES_LotInfo_Query 查询 Lot MES 信息（异步 execute_workflow + get_execution）

    数据源：N8N MCP Server（MES_ExecuteQuery_Tool）
    返回字段：product / process / route / step / lotjobstatus / currentquantity / cassette 等
    """
    if not lot_id:
        return {"answer": "请提供 Lot ID。", "sql": ""}

    try:
        from services.mcp_client import get_mcp_client, get_mcp_config, MCPError
    except ImportError:
        return {"answer": "⚠️ MCP 客户端模块未安装。", "sql": ""}

    cfg = get_mcp_config()
    if not cfg["enabled"]:
        return {"answer": "⚠️ N8N MCP 未启用，请在 AI 配置面板中开启。", "sql": ""}
    if not cfg["token"]:
        return {"answer": "⚠️ N8N MCP Token 未配置，请在 AI 配置面板中录入。", "sql": ""}

    try:
        client = get_mcp_client()
        if not client:
            return {"answer": "⚠️ MCP 客户端初始化失败。", "sql": ""}

        workflow_id = "ymOYQpVMhHr7cWJH"

        # 1. 发起执行
        exec_resp = client.call_tool("execute_workflow", {
            "workflowId": workflow_id,
            "inputs": {
                "type": "webhook",
                "webhookData": {
                    "method": "POST",
                    "body": {"lot": lot_id}
                }
            }
        })
        execution_id = exec_resp.get("executionId")
        if not execution_id:
            return {"answer": "⚠️ MCP 未返回 executionId", "sql": ""}

        # 2. 轮询结果（最多 5 次，每次 2 秒）
        final_result = None
        for i in range(5):
            time.sleep(2)
            exec_result = client.call_tool("get_execution", {
                "executionId": str(execution_id),
                "workflowId": workflow_id,
                "includeData": True
            })
            status = exec_result.get("execution", {}).get("status", "?")
            if status in ("success", "finished", "completed"):
                final_result = exec_result
                break
            elif status in ("error", "failed", "crashed"):
                return {"answer": f"⚠️ MES 工作流执行失败: {status}", "sql": ""}

        if not final_result:
            return {"answer": "⚠️ MES 工作流执行超时", "sql": ""}

        # 3. 提取最终输出
        data = final_result.get("data", {})
        result_data = data.get("resultData", {})
        run_data = result_data.get("runData", {})
        result = _extract_n8n_output(run_data)

        if not result:
            return {"answer": f"⚠️ 无法从 N8N 输出中提取 Lot {lot_id} 的数据", "sql": ""}

    except MCPError as e:
        return {"answer": f"⚠️ MCP 调用失败：{e}", "sql": ""}
    except Exception as e:
        return {"answer": f"⚠️ MES 查询异常：{e}", "sql": ""}

    if not result.get("success", True):
        return {"answer": f"Lot {lot_id} 查询失败：{result.get('message', '未知错误')}", "sql": ""}

    # 提取行数据
    rows = result.get("data", {}).get("rows", []) if isinstance(result.get("data"), dict) else []
    if not rows and isinstance(result.get("data"), list):
        rows = result["data"]

    if not rows:
        message = result.get("message", "")
        return {
            "answer": f"Lot {lot_id} MES 信息：\n{message}" if message else f"Lot {lot_id} 在 MES 中无详细记录。",
            "sql": "",
        }

    row = rows[0] if isinstance(rows[0], dict) else {}

    # 构造自然语言回答
    answer = f"📦 Lot **{lot_id}** MES 信息：\n"
    answer += f"• 产品型号：{row.get('product', 'N/A')}\n"
    answer += f"• 工艺：{row.get('process', 'N/A')}（版本 {row.get('processversion', 'N/A')}）\n"
    answer += f"• 工艺路线：{row.get('route', 'N/A')}\n"
    answer += f"• 当前步骤：{row.get('step', 'N/A')}\n"

    status = row.get("lotjobstatus", "N/A")
    status_cn = {"RUN": "运行中", "HOLD": "暂停", "COMPLETE": "已完成", "WAIT": "等待中"}.get(status, status)
    answer += f"• 状态：{status}（{status_cn}）\n"
    answer += f"• 晶圆数量：{row.get('currentquantity', 'N/A')}\n"
    answer += f"• 花篮号：{row.get('cassette', 'N/A')}\n"
    answer += f"• Lot 类型：{row.get('lottype', 'N/A')}\n"
    answer += f"• Wafer 类型：{row.get('wafertype', 'N/A')}\n"
    answer += f"• 是否返工：{row.get('isrework', 'N/A')}\n"

    table_data = {
        "headers": list(row.keys()),
        "rows": [[str(v) if v is not None else "" for v in row.values()]],
    }

    return {
        "answer": answer,
        "sql": f"-- MCP execute_workflow: MES_LotInfo_Query(lot='{lot_id}')",
        "table_data": table_data,
    }


def get_lot_info(db: Session, lot_id: str = None, machine_id: str = None,
                 use_mes: bool = True) -> dict:
    """查询 Lot 信息（MES + 设备事件双源融合）

    Args:
        lot_id: Lot ID
        machine_id: 关联机台（可选）
        use_mes: 是否尝试调用 MES（True 时先查 MES）
    """
    if not lot_id:
        # 未指定 Lot ID，从 DT_EVENT_RAW 聚合最近 Lot
        tool_ids = _resolve_tool_ids(db, machine_id) if machine_id else None

        q = db.query(DT_EVENT_RAW)
        if tool_ids:
            q = q.filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
        events = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(1000).all()

        lot_set = {}
        for e in events:
            payload = _parse_payload(e.payload_json)
            lot = payload.get("lot_id")
            if lot and lot.upper() not in ("NULL", ""):
                if lot not in lot_set:
                    lot_set[lot] = {"tool_id": e.tool_id, "ts": e.received_ts_utc}

        if not lot_set:
            return {"answer": "未找到相关 Lot 记录。请提供具体 Lot ID（如 NT938、VC001、PC00H.29）。", "sql": ""}

        table_data = {
            "headers": ["Lot ID", "机台", "最后事件时间"],
            "rows": [[lot, info["tool_id"], info["ts"]] for lot, info in list(lot_set.items())[:10]],
        }

        answer = f"最近 {len(lot_set)} 个 Lot：\n（点击下方表格或输入 Lot ID 查看详情）"

        return {
            "answer": answer,
            "sql": "SELECT DISTINCT lot_id FROM dt_event_raw",
            "table_data": table_data,
            "jump_timestamp": _format_ts(list(lot_set.values())[0]["ts"]) if lot_set else None,
            "jump_machine_id": list(lot_set.values())[0]["tool_id"] if lot_set else None,
        }

    # 有 lot_id：先查 MES（如果启用），再查设备事件，最后融合
    answer_parts = []
    jump_machine_id = None
    jump_timestamp = None
    table_data = None

    # 1. 查 MES
    if use_mes:
        try:
            from services.mcp_client import get_mcp_config
            mcp_cfg = get_mcp_config()
            if mcp_cfg["enabled"] and mcp_cfg["token"]:
                mes_result = get_mes_lot_info(db, lot_id)
                if mes_result.get("answer"):
                    answer_parts.append(mes_result["answer"])
        except Exception as e:
            answer_parts.append(f"⚠️ MES 查询失败：{e}")
    else:
        answer_parts.append(f"(跳过 MES 查询)")

    # 2. 查 FabTwin 设备事件
    events = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.payload_json.like(f'%{lot_id}%')
    ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(50).all()

    if events:
        # 聚合：按机台分组
        machine_events = {}
        all_tools = set()
        for e in events:
            mid = e.tool_id
            all_tools.add(mid)
            payload = _parse_payload(e.payload_json)
            if mid not in machine_events:
                machine_events[mid] = {
                    "timestamp": e.received_ts_utc,
                    "event": payload.get("event_name", ""),
                    "state": payload.get("machine_state", ""),
                    "mode": payload.get("machine_mode", "") if not _is_null(payload.get("machine_mode")) else "",
                    "cassette": payload.get("cassette_id", "") if not _is_null(payload.get("cassette_id")) else "",
                }

        # 构造回答
        fab_answer = f"🏭 FabTwin 设备事件（共 {len(events)} 条，涉及 {len(all_tools)} 台机台）：\n"
        for mid, info in machine_events.items():
            fab_answer += f"  • {mid}：{info['event']} @ {info['timestamp']}\n"

        answer_parts.append(fab_answer)

        # 构造表格（机台时间线）
        timeline_rows = []
        for mid, info in machine_events.items():
            timeline_rows.append([
                info["timestamp"], mid, info["event"], info["state"], info["mode"]
            ])

        table_data = {
            "headers": ["时间", "机台", "事件", "状态", "模式"],
            "rows": timeline_rows[:10],
        }

        # 跳转：默认跳到最新事件所在机台
        first_mid = list(machine_events.keys())[0]
        jump_machine_id = first_mid
        jump_timestamp = _format_ts(machine_events[first_mid]["timestamp"])

    else:
        answer_parts.append(f"FabTwin 设备事件流中暂无 {lot_id} 的记录。")

    # 3. 检查跳转目标机台是否在平台上
    machine_online = None
    if jump_machine_id:
        exists = db.query(Machine).filter(Machine.id == jump_machine_id).first()
        machine_online = exists is not None

    # 4. 合并回答
    final_answer = "\n\n".join(answer_parts)
    if jump_machine_id:
        if machine_online:
            final_answer += f"\n\n📍 最近事件在 **{jump_machine_id}** ({jump_timestamp})，可点击下方表格行跳转查看历史回放。"
        else:
            final_answer += f"\n\n⚠️ 最近事件在 **{jump_machine_id}** ({jump_timestamp})，该机台暂未上线平台，暂不支持跳转查看历史回放。"

    return {
        "answer": final_answer,
        "sql": f"SELECT * FROM dt_event_raw WHERE payload_json LIKE '%{lot_id}%' ORDER BY raw_id DESC",
        "table_data": table_data,
        "jump_timestamp": jump_timestamp if machine_online else None,
        "jump_machine_id": jump_machine_id if machine_online else None,
        "machine_online": machine_online,
    }


# ==================== 工具6: 工艺配方（无真实数据，返回提示） ====================

def get_recipe_info(db: Session, machine_id: str = None) -> dict:
    """查询工艺配方（生产环境无真实配方数据，返回提示）"""
    if machine_id:
        return {
            "answer": (
                f"机台 {machine_id} 的工艺配方信息：\n\n"
                f"当前系统仅采集 VFEI 事件流，不包含配方参数数据。\n"
                f"请查询 MES 或 RCMS 系统获取详细配方参数。\n\n"
                f"如有需要，可将配方数据接入 Oracle 后再提供查询。"
            ),
            "sql": "",
        }

    return {
        "answer": (
            "工艺配方查询：\n\n"
            "当前系统仅采集 VFEI 事件流（POD 开盖/关盖等），不包含工艺配方参数。\n"
            "请查询 MES 或 RCMS 系统获取配方详情。"
        ),
        "sql": "",
    }


# ==================== OXE 专用工具 ====================

# OXE 晶圆加工相关事件名（ WaferLoaded/Unloaded 表示一片晶圆加工开始/结束）
_OXE_WAFER_LOAD_EVENT = "WaferLoaded"
_OXE_WAFER_UNLOAD_EVENT = "WaferUnloaded"
# OXE 工艺事件（Start=开始加工, PE=加工结束, PS=工艺步骤开始）
_OXE_PROCESS_EVENTS = {"Start", "PS", "PE"}
# OXE Chamber 标识
_OXE_CHAMBERS = ["CHAMBER_A", "CHAMBER_B", "CHAMBER_C"]


def _is_oxe_machine(machine_id: str) -> bool:
    """判断是否为 OXE 系列机台"""
    return bool(machine_id) and machine_id.upper().startswith("OXE")


def get_wafer_flow(db: Session, machine_id: str, lot_id: str = None) -> dict:
    """查询 OXE 机台某 Lot 的晶圆流向（PORT→PA→CHAMBER 加工流转）

    通过 WaferLoaded/WaferUnloaded/Start/PE 事件推算每片晶圆的加工状态。
    容错：如果某片晶圆缺少 Unloaded 事件，标记为"加工中/异常"。
    """
    if not machine_id:
        return {"answer": "请指定机台ID，如 OXE-61。", "sql": ""}

    tool_ids = _resolve_tool_ids(db, machine_id)
    q = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.in_(tool_ids))

    # 如果指定了 lot_id，按 lot_id 过滤
    if lot_id:
        q = q.filter(DT_EVENT_RAW.payload_json.like(f'%"{lot_id}"%'))

    # 取最近 5000 条事件（足够覆盖一个完整 Lot 的 25 片流程）
    rows = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(5000).all()

    # 解析并按时间正序排列（raw_id 升序 = 时间升序）
    events = []
    for r in rows:
        payload = _parse_payload(r.payload_json)
        payload = clean_alarm_event(payload)
        events.append({
            "raw_id": str(r.raw_id),
            "ts": r.received_ts_utc,
            "event_name": str(payload.get("event_name", "")).strip(),
            "lot_id": payload.get("lot_id", ""),
            "wafer_id": payload.get("wafer_id"),
            "slot": payload.get("slot"),
            "chamber_id": payload.get("chamber_id", ""),
            "port_id": payload.get("port_id", ""),
        })
    events.reverse()  # 时间正序

    # 如果未指定 lot_id，取最新的 lot_id
    if not lot_id:
        for ev in reversed(events):
            if ev["lot_id"]:
                lot_id = ev["lot_id"]
                break

    # 过滤指定 lot 的事件
    if lot_id:
        events = [e for e in events if e["lot_id"] == lot_id]

    if not events:
        return {"answer": f"机台 {machine_id} 暂无 Lot {lot_id or '(最新)'} 的晶圆加工事件。", "sql": ""}

    # 按 wafer_id 聚合：记录每片晶圆的 Loaded/Unloaded 时间
    wafer_records = {}  # {wafer_id: {"loaded_ts": ..., "unloaded_ts": ..., "chamber": ..., "slot": ...}}
    for ev in events:
        wid = ev["wafer_id"]
        if wid is None:
            continue
        wid = str(wid)
        if wid not in wafer_records:
            wafer_records[wid] = {"loaded_ts": None, "unloaded_ts": None, "chamber": ev["chamber_id"], "slot": ev["slot"]}
        if ev["event_name"] == _OXE_WAFER_LOAD_EVENT:
            wafer_records[wid]["loaded_ts"] = ev["ts"]
            if ev["chamber_id"]:
                wafer_records[wid]["chamber"] = ev["chamber_id"]
        elif ev["event_name"] == _OXE_WAFER_UNLOAD_EVENT:
            wafer_records[wid]["unloaded_ts"] = ev["ts"]

    if not wafer_records:
        return {"answer": f"机台 {machine_id} Lot {lot_id} 的事件中未找到 WaferLoaded/Unloaded 记录，可能事件类型不匹配。", "sql": ""}

    # 按晶圆号排序
    def _wafer_sort_key(wid):
        try:
            return int(wid)
        except (ValueError, TypeError):
            return 9999
    sorted_wafers = sorted(wafer_records.items(), key=lambda x: _wafer_sort_key(x[0]))

    completed = [w for w, d in sorted_wafers if d["unloaded_ts"]]
    in_progress = [w for w, d in sorted_wafers if d["loaded_ts"] and not d["unloaded_ts"]]
    pending = [w for w, d in sorted_wafers if not d["loaded_ts"]]

    # 计算平均加工时长（从 Loaded 到 Unloaded）
    durations = []
    for w, d in sorted_wafers:
        if d["loaded_ts"] and d["unloaded_ts"]:
            try:
                ts1 = datetime.fromisoformat(str(d["loaded_ts"]).replace("Z", "").replace("+00:00", ""))
                ts2 = datetime.fromisoformat(str(d["unloaded_ts"]).replace("Z", "").replace("+00:00", ""))
                dur = (ts2 - ts1).total_seconds()
                if dur > 0:
                    durations.append((w, dur))
            except Exception:
                pass

    avg_duration_sec = sum(d for _, d in durations) / len(durations) if durations else 0
    avg_min = int(avg_duration_sec // 60) if avg_duration_sec else 0
    avg_sec = int(avg_duration_sec % 60) if avg_duration_sec else 0

    # 检测异常片（加工时长超出平均 50%）
    anomalies = []
    if avg_duration_sec > 0:
        for w, dur in durations:
            if dur > avg_duration_sec * 1.5:
                anomalies.append((w, int(dur // 60), int(dur % 60)))

    answer = f"机台 {machine_id} Lot {lot_id} 的晶圆流向：\n"
    answer += f"- 总晶圆数：{len(sorted_wafers)} 片\n"
    answer += f"- 已完成：{len(completed)} 片"
    if completed:
        answer += f"（W{completed[0]}-W{completed[-1]}）"
    answer += f"\n- 加工中：{len(in_progress)} 片"
    if in_progress:
        answer += f"（当前 W{in_progress[-1]}）"
        current_chamber = wafer_records[in_progress[-1]]["chamber"]
        if current_chamber:
            answer += f"，位于 {current_chamber}"
    answer += f"\n- 待加工：{len(pending)} 片\n"

    if avg_duration_sec > 0:
        answer += f"- 平均加工时长：{avg_min}分{avg_sec}秒/片\n"

    if anomalies:
        answer += f"- 异常片（加工时长超出平均50%）：{len(anomalies)} 片\n"
        for w, m, s in anomalies[:3]:
            answer += f"  W{w}：{m}分{s}秒\n"

    # 表格数据
    table_rows = []
    for w, d in sorted_wafers[:25]:
        status = "已完成" if d["unloaded_ts"] else ("加工中" if d["loaded_ts"] else "待加工")
        table_rows.append([
            f"W{w}",
            str(d["slot"] or "-"),
            d["chamber"] or "-",
            str(d["loaded_ts"] or "-")[:19],
            str(d["unloaded_ts"] or "-")[:19],
            status,
        ])

    return {
        "answer": answer,
        "sql": "",
        "table_data": {
            "headers": ["晶圆ID", "Slot", "Chamber", "Loaded时间", "Unloaded时间", "状态"],
            "rows": table_rows,
        },
        "jump_timestamp": str(wafer_records[in_progress[-1]]["loaded_ts"]) if in_progress and wafer_records[in_progress[-1]]["loaded_ts"] else (str(events[-1]["ts"]) if events else None),
        "jump_machine_id": machine_id,
    }


def get_chamber_status(db: Session, machine_id: str) -> dict:
    """查询 OXE 机台 3 个 Chamber 的实时加工状态

    通过最近 N 条事件推算每个 Chamber 的当前状态（空闲/加工中/卸载中）。
    """
    if not machine_id:
        return {"answer": "请指定机台ID，如 OXE-61。", "sql": ""}

    tool_ids = _resolve_tool_ids(db, machine_id)
    rows = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.tool_id.in_(tool_ids)
    ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(500).all()

    if not rows:
        return {"answer": f"机台 {machine_id} 暂无事件数据。", "sql": ""}

    # 解析事件（时间倒序，最新在前）
    events = []
    for r in rows:
        payload = _parse_payload(r.payload_json)
        payload = clean_alarm_event(payload)
        events.append({
            "raw_id": str(r.raw_id),
            "ts": r.received_ts_utc,
            "event_name": str(payload.get("event_name", "")).strip(),
            "lot_id": payload.get("lot_id", ""),
            "wafer_id": payload.get("wafer_id"),
            "chamber_id": payload.get("chamber_id", ""),
            "machine_state": payload.get("machine_state", ""),
        })

    # 推算每个 Chamber 的状态
    chamber_states = {}
    current_lot = events[0]["lot_id"] if events else ""
    latest_ts = str(events[0]["ts"]) if events else ""

    for chamber in _OXE_CHAMBERS:
        chamber_events = [e for e in events if e["chamber_id"] == chamber]
        if not chamber_events:
            chamber_states[chamber] = {"state": "空闲", "wafer": None, "last_ts": None, "last_event": "无事件"}
            continue

        latest = chamber_events[0]  # 最新事件（倒序第一个）
        state = "空闲"
        wafer = None

        # 根据最新事件类型推算状态
        if latest["event_name"] == _OXE_WAFER_LOAD_EVENT:
            # 最新是 Loaded，说明刚放入，正在加工
            state = "加工中"
            wafer = latest["wafer_id"]
        elif latest["event_name"] == _OXE_WAFER_UNLOAD_EVENT:
            # 最新是 Unloaded，说明刚取出，空闲
            state = "空闲"
            wafer = None
        elif latest["event_name"] == "Start":
            state = "加工中"
            wafer = latest["wafer_id"]
        elif latest["event_name"] == "PE":
            state = "空闲"
        elif latest["event_name"] in ("PS",):
            state = "加工中"
            wafer = latest["wafer_id"]

        chamber_states[chamber] = {
            "state": state,
            "wafer": wafer,
            "last_ts": latest["ts"],
            "last_event": latest["event_name"],
        }

    # 统计今日产量（WaferUnloaded 事件数）
    today_prefix = str(latest_ts)[:10] if latest_ts else ""
    today_yield = 0
    for e in events:
        if e["event_name"] == _OXE_WAFER_UNLOAD_EVENT and str(e["ts"]).startswith(today_prefix):
            today_yield += 1

    # 当前 Lot 进度
    lot_events = [e for e in events if e["lot_id"] == current_lot]
    loaded_count = sum(1 for e in lot_events if e["event_name"] == _OXE_WAFER_LOAD_EVENT)
    unloaded_count = sum(1 for e in lot_events if e["event_name"] == _OXE_WAFER_UNLOAD_EVENT)

    answer = f"机台 {machine_id} Chamber 状态（截至 {str(latest_ts)[:19]}）：\n"
    for chamber in _OXE_CHAMBERS:
        s = chamber_states[chamber]
        wafer_info = f"，当前 W{s['wafer']}" if s["wafer"] else ""
        last_info = f"，上次事件 {str(s['last_ts'])[:19]}" if s["last_ts"] else ""
        answer += f"- {chamber}：{s['state']}{wafer_info}{last_info}\n"

    answer += f"- 今日产量：{today_yield} 片\n"
    if current_lot:
        answer += f"- 当前Lot：{current_lot}（已加载 {loaded_count} 片，已卸载 {unloaded_count} 片）\n"

    table_rows = []
    for chamber in _OXE_CHAMBERS:
        s = chamber_states[chamber]
        table_rows.append([
            chamber,
            s["state"],
            f"W{s['wafer']}" if s["wafer"] else "-",
            str(s["last_ts"])[:19] if s["last_ts"] else "-",
            s["last_event"],
        ])

    return {
        "answer": answer,
        "sql": "",
        "table_data": {
            "headers": ["Chamber", "状态", "当前晶圆", "最近事件时间", "最近事件"],
            "rows": table_rows,
        },
        "jump_timestamp": latest_ts,
        "jump_machine_id": machine_id,
    }


def get_oxe_lot_summary(db: Session, machine_id: str, date: str = None, lot_id: str = None) -> dict:
    """查询 OXE 机台某日/某 Lot 的加工汇总（多 Lot 对比、产量趋势）

    通过 WaferLoaded/Unloaded 事件聚合统计。
    """
    if not machine_id:
        return {"answer": "请指定机台ID，如 OXE-61。", "sql": ""}

    tool_ids = _resolve_tool_ids(db, machine_id)
    q = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.in_(tool_ids))

    # 如果指定了 lot_id，按 lot_id 过滤
    if lot_id:
        q = q.filter(DT_EVENT_RAW.payload_json.like(f'%"{lot_id}"%'))

    rows = q.order_by(DT_EVENT_RAW.raw_id.desc()).limit(5000).all()

    if not rows:
        return {"answer": f"机台 {machine_id} 暂无事件数据。", "sql": ""}

    # 解析事件
    events = []
    for r in rows:
        payload = _parse_payload(r.payload_json)
        payload = clean_alarm_event(payload)
        ts = str(r.received_ts_utc) if r.received_ts_utc else ""
        events.append({
            "ts": ts,
            "date": ts[:10] if ts else "",
            "event_name": str(payload.get("event_name", "")).strip(),
            "lot_id": payload.get("lot_id", ""),
            "wafer_id": payload.get("wafer_id"),
            "chamber_id": payload.get("chamber_id", ""),
        })

    # 按日期过滤
    if date:
        events = [e for e in events if e["date"] == date]
    else:
        # 默认取最新日期
        all_dates = sorted(set(e["date"] for e in events if e["date"]), reverse=True)
        if all_dates:
            date = all_dates[0]
            events = [e for e in events if e["date"] == date]

    if not events:
        return {"answer": f"机台 {machine_id} 在 {date or '指定日期'} 暂无事件数据。", "sql": ""}

    # 按 lot_id 聚合
    lot_summary = {}  # {lot_id: {"loaded": set(), "unloaded": set(), "alarms": 0, "chambers": set()}}
    for ev in events:
        lid = ev["lot_id"] or "(未知Lot)"
        if lid not in lot_summary:
            lot_summary[lid] = {"loaded": set(), "unloaded": set(), "alarms": 0, "chambers": set(), "first_ts": ev["ts"], "last_ts": ev["ts"]}
        if ev["event_name"] == _OXE_WAFER_LOAD_EVENT and ev["wafer_id"] is not None:
            lot_summary[lid]["loaded"].add(str(ev["wafer_id"]))
        elif ev["event_name"] == _OXE_WAFER_UNLOAD_EVENT and ev["wafer_id"] is not None:
            lot_summary[lid]["unloaded"].add(str(ev["wafer_id"]))
        elif ev["event_name"] in ("ALARM_REPORT", "EC_ALARM_REPORT"):
            lot_summary[lid]["alarms"] += 1
        if ev["chamber_id"]:
            lot_summary[lid]["chambers"].add(ev["chamber_id"])
        if ev["ts"] < lot_summary[lid]["first_ts"]:
            lot_summary[lid]["first_ts"] = ev["ts"]
        if ev["ts"] > lot_summary[lid]["last_ts"]:
            lot_summary[lid]["last_ts"] = ev["ts"]

    # 统计
    total_wafers = sum(len(s["loaded"]) for s in lot_summary.values())
    completed_wafers = sum(len(s["unloaded"]) for s in lot_summary.values())
    total_alarms = sum(s["alarms"] for s in lot_summary.values())
    in_progress = total_wafers - completed_wafers

    # 计算总加工时长（取最早和最晚时间戳）
    all_ts = [e["ts"] for e in events if e["ts"]]
    total_duration_sec = 0
    if len(all_ts) >= 2:
        try:
            ts_min = min(all_ts)
            ts_max = max(all_ts)
            dt_min = datetime.fromisoformat(ts_min.replace("Z", "").replace("+00:00", ""))
            dt_max = datetime.fromisoformat(ts_max.replace("Z", "").replace("+00:00", ""))
            total_duration_sec = (dt_max - dt_min).total_seconds()
        except Exception:
            pass

    total_hours = int(total_duration_sec // 3600) if total_duration_sec else 0
    total_minutes = int((total_duration_sec % 3600) // 60) if total_duration_sec else 0

    # 平均加工时长
    avg_per_wafer_sec = total_duration_sec / completed_wafers if completed_wafers > 0 else 0
    avg_min = int(avg_per_wafer_sec // 60) if avg_per_wafer_sec else 0
    avg_sec = int(avg_per_wafer_sec % 60) if avg_per_wafer_sec else 0

    # 机台利用率（有事件时间 / 总时间）
    utilization = 0
    if total_duration_sec > 0 and completed_wafers > 0:
        # 估算：每片加工时间 * 片数 / 总时间
        process_time = avg_per_wafer_sec * completed_wafers
        utilization = min(100, int(process_time / total_duration_sec * 100))

    answer = f"机台 {machine_id} 在 {date} 的加工汇总：\n"
    answer += f"- 加工Lot数：{len(lot_summary)} 个"
    if lot_summary:
        answer += f"（{'/'.join(list(lot_summary.keys())[:5])}）"
    answer += f"\n- 总晶圆数：{total_wafers} 片\n"
    answer += f"- 已完成：{completed_wafers} 片\n"
    answer += f"- 加工中：{in_progress} 片\n" if in_progress > 0 else ""
    answer += f"- 异常告警：{total_alarms} 次\n" if total_alarms > 0 else ""
    if avg_per_wafer_sec > 0:
        answer += f"- 平均加工时长：{avg_min}分{avg_sec}秒/片\n"
    if total_duration_sec > 0:
        answer += f"- 总加工时间：{total_hours}小时{total_minutes}分\n"
        answer += f"- 机台利用率：{utilization}%\n"

    # 表格数据（按 Lot 分组）
    table_rows = []
    for lid, s in sorted(lot_summary.items()):
        table_rows.append([
            lid,
            str(len(s["loaded"])),
            str(len(s["unloaded"])),
            "/".join(sorted(s["chambers"])) if s["chambers"] else "-",
            str(s["alarms"]),
            str(s["first_ts"])[:19],
            str(s["last_ts"])[:19],
        ])

    return {
        "answer": answer,
        "sql": "",
        "table_data": {
            "headers": ["Lot ID", "已加载", "已完成", "使用Chamber", "告警数", "开始时间", "结束时间"],
            "rows": table_rows,
        },
        "jump_timestamp": all_ts[-1] if all_ts else None,
        "jump_machine_id": machine_id,
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
            "description": "查询Lot完整追溯信息（MES产品/工艺/状态 + FabTwin设备事件时间线融合）。返回Lot经过的所有机台、时间、事件，并支持跳转历史回放。适用：用户问'Lot追溯'、'Lot走过哪些机台'、'Lot在哪台机台上'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lot_id": {
                        "type": "string",
                        "description": "Lot ID，如 PC00H.29、NT938、NT938.15、VC001"
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
            "name": "get_mes_lot_info",
            "description": "查询MES系统Lot详细信息（产品型号、工艺、路线、步骤、状态、晶圆数量、花篮号）。适用：用户提到具体Lot ID并询问产品/状态/晶圆数/工艺信息时，必须调用此工具。数据源：N8N MCP MES_LotInfo_Query。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lot": {
                        "type": "string",
                        "description": "Lot ID，如 PC00H.29、NT938、NT938.15、VC001"
                    }
                },
                "required": ["lot"]
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
    {
        "type": "function",
        "function": {
            "name": "get_wafer_flow",
            "description": "查询OXE机台某Lot的晶圆流向（PORT取片→PA对准→CHAMBER加工→PA放回→PORT放回）。返回每片晶圆的加工状态、平均时长、异常片。适用：用户问'晶圆流向'、'第几片在加工'、'晶圆进度'。仅适用于OXE系列机台。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "OXE机台ID，如 OXE-61"
                    },
                    "lot_id": {
                        "type": "string",
                        "description": "Lot ID。不传则查询最新Lot。"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_chamber_status",
            "description": "查询OXE机台3个Chamber（CHAMBER_A/B/C）的实时加工状态，包括每个Chamber当前是否加工中、加工哪片晶圆、最近事件时间、今日产量。适用：用户问'Chamber状态'、'3个腔体在做什么'、'当前加工情况'。仅适用于OXE系列机台。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "OXE机台ID，如 OXE-61"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_oxe_lot_summary",
            "description": "查询OXE机台某日或某Lot的加工汇总（多Lot对比、产量趋势、机台利用率）。返回每个Lot的晶圆数、完成数、告警数、加工时长。适用：用户问'今天加工了几个Lot'、'产量汇总'、'机台利用率'。仅适用于OXE系列机台。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "OXE机台ID，如 OXE-61"
                    },
                    "date": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD，如 2026-08-11。不传则查询最新日期。"
                    },
                    "lot_id": {
                        "type": "string",
                        "description": "Lot ID。指定则只查该Lot。"
                    }
                },
                "required": ["machine_id"]
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
    "get_mes_lot_info": lambda db, **kw: get_mes_lot_info(db, lot_id=kw.get("lot") or kw.get("lot_id")),
    "get_recipe_info": get_recipe_info,
    "get_wafer_flow": get_wafer_flow,
    "get_chamber_status": get_chamber_status,
    "get_oxe_lot_summary": get_oxe_lot_summary,
}
