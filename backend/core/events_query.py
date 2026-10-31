# -*- coding: utf-8 -*-
"""跨域事件查询公共层：收拢原 lots/history/ai_tools/machines/db_poller 五处重复实现。

- resolve_tool_ids   ：machine_id → tool_id 集合（原三份 _resolve_tool_ids）
- col_is_temporal    ：反射判定列是否 DATE/TIMESTAMP（原三份时间列反射）
- day_clause         ：按列真实类型生成"某一天"的 SQL 条件（原 machines._day_clause）
- find_raw_id_anchor ：raw_id 二分时间锚点（原 lots/history 两份）
- clean_alarm_event  ：ALARM 事件字段清洗（原 ai_tools 内定义、oxe/history 复用）

行为保持与原实现一致（OXE 前缀匹配仍只在 AI 工具层启用，见 extra_prefixes）。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy import DateTime, and_, func, inspect, or_

from models import DT_EVENT_RAW
from services.time_utils import parse_ts, build_date_like_patterns

logger = logging.getLogger("fabtwin.core.events_query")

# ALARM 类事件名：port_id/chamber_id 等字段被错误填充为告警描述词，需清空
ALARM_EVENT_NAMES = {"ALARM_REPORT", "EC_ALARM_REPORT"}
# ALARM 事件需要清空的字段（这些字段在 ALARM 报文中是错误解析的描述词）
_ALARM_FIELDS_TO_CLEAR = (
    "port_id", "chamber_id", "cassette_id", "smif_id",
    "slot_id", "wafer_id", "pod_id", "unit_id", "batch_id",
)

# 列类型反射缓存：key = "table.column"
_COL_TEMPORAL_CACHE = {}


def clean_alarm_event(payload: dict) -> dict:
    """清理 ALARM 事件中被错误填充的字段。

    量产 DB 中 ALARM_REPORT/EC_ALARM_REPORT 事件的 port_id/chamber_id 等字段
    被 bridge 错误填充为告警描述词（如 "AGC"/"Time"/"Sensor-2"），
    需清空这些字段，只保留 alarm_text/alarm_code 等告警字段。
    """
    if not payload:
        return payload
    event_name = str(payload.get("event_name", "")).upper().strip()
    if event_name in ALARM_EVENT_NAMES:
        for field in _ALARM_FIELDS_TO_CLEAR:
            if field in payload:
                payload[field] = "NULL"
    return payload


def col_is_temporal(db, table_name: str, col_name: str) -> bool:
    """反射判定某列是否 DATE/TIMESTAMP（量产形态）；字符列返回 False（本地形态）。

    结果按 (table, col) 缓存。探测失败按字符列处理，避免把查询打死。
    """
    key = f"{table_name}.{col_name}"
    if key in _COL_TEMPORAL_CACHE:
        return _COL_TEMPORAL_CACHE[key]
    temporal = False
    try:
        cols = inspect(db.get_bind()).get_columns(table_name)
        col = next((c for c in cols if str(c.get("name", "")).lower() == col_name.lower()), None)
        temporal = isinstance(col.get("type"), DateTime) if col else False
    except Exception as e:
        logger.warning("[core] 探测 %s 列类型失败，按字符列处理: %s", key, e)
    _COL_TEMPORAL_CACHE[key] = temporal
    return temporal


def day_clause(db, model, col, date_str: str):
    """生成「限定在 date_str 这一天」的 SQL 条件，按列真实类型选写法。

    - TIMESTAMP/DATE 列：半开区间 [当日00:00, 次日00:00)
    - 字符列：前缀 LIKE，兼容 ISO T分隔/空格分隔/NLS 月日不补零
    返回 None 表示 date_str 非法，调用方应跳过 SQL 层日期过滤。
    """
    table = model.__tablename__
    if col_is_temporal(db, table, col.key):
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        nxt = day + timedelta(days=1)
        return and_(col >= day, col < nxt)
    patterns = build_date_like_patterns(date_str)
    if not patterns:
        return None
    return or_(*[col.like(p) for p in patterns])


def resolve_tool_ids(db, machine_id: str, extra_prefixes: tuple = ()) -> Set[str]:
    """将 machine_id 解析为对应的 tool_id 集合。

    支持三种情况：
    1. machine_id 和 tool_id 相同（如 OXE-01）
    2. machine_id 通过 machine_tool_mappings 映射到 tool_id（如 VPO-01 -> PODOPENER-1）
    3. PODOPENER 机台：量产 Oracle 中 tool_id 为 PODOPENER（不带序号）

    extra_prefixes：额外的 tool_id 前缀匹配（AI 工具层传 ("OXE",)；
    history/lots 不传——PROJECT_STATUS 已知问题 #7，误伤面未确认前不改默认行为）。
    machine_tool_mappings 表可能不存在于量产 Oracle 中，需要 try-except。
    """
    # machine_id 为空时返回空集合（调用方查询命中空 IN 得到空列表，而非 None.upper() 500）
    if not machine_id:
        return set()
    tool_ids = {machine_id}
    upper_id = machine_id.upper()

    if upper_id.startswith("PODOPENER"):
        tool_ids.add("PODOPENER")
    for prefix in extra_prefixes:
        if upper_id.startswith(prefix):
            tool_ids.add(prefix)

    # 尝试查询映射表（可能不存在于量产 Oracle 中）
    try:
        from models import MachineToolMapping
        mappings = db.query(MachineToolMapping).filter(
            (MachineToolMapping.machine_id == machine_id) |
            (MachineToolMapping.tool_id == machine_id)
        ).all()
        for m in mappings:
            tool_ids.add(m.tool_id)
            tool_ids.add(m.machine_id)
    except Exception:
        pass  # 映射表不存在或查询失败，忽略
    return tool_ids


def find_raw_id_anchor(db, tool_ids, target_dt) -> Optional[int]:
    """在 raw_id 中定位到 ts <= target_dt 的最大 raw_id。

    解决 VARCHAR2 时间字段无法在 SQL 层做时间比较的问题：
    二分查找定位 ts <= target_dt 的最大 raw_id，作为时间锚点。
    由于 raw_id 随时间递增，后续查询应以 raw_id >= anchor 为条件，
    获取从该时间点往后的所有事件。
    """
    try:
        # 获取 raw_id 范围
        min_max = db.query(
            func.min(DT_EVENT_RAW.raw_id),
            func.max(DT_EVENT_RAW.raw_id)
        ).filter(DT_EVENT_RAW.tool_id.in_(tool_ids)).first()
        if not min_max or min_max[0] is None:
            return None
        rid_min, rid_max = min_max[0], min_max[1]
    except Exception:
        return None

    # 二分查找：找最大的 raw_id 使得 ts <= target_dt
    lo, hi = rid_min, rid_max
    best_anchor = None
    max_iterations = 15  # 15次迭代可覆盖2^15=32768范围，足以定位单机台事件
    for _ in range(max_iterations):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        # 取出 mid 位置之前的最近一条同机台事件
        # （raw_id 全表递增，mid 可能落在其他机台的行上，用 <= mid + DESC LIMIT 1 找到最近的）
        row = db.query(DT_EVENT_RAW).filter(
            DT_EVENT_RAW.tool_id.in_(tool_ids),
            DT_EVENT_RAW.raw_id <= mid
        ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(1).first()
        if not row:
            hi = mid - 1
            continue
        ts = row.event_ts_utc or row.received_ts_utc
        row_dt = parse_ts(ts) if ts else 0
        if row_dt and row_dt <= target_dt:
            best_anchor = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best_anchor
