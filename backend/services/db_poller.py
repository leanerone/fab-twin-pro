"""DB事件轮询服务：从DT_EVENT_RAW表读取新事件并通过WebSocket推送

与模拟器的区别：
- 模拟器：主动生成事件写入DB
- 轮询服务：从DB读取外部写入的事件（如WinForm工具写入），推送到前端

两种模式可以同时运行：
- DEMO模式：模拟器生成事件
- 真实模式：WinForm/外部系统写入DB，轮询服务读取推送

2026-10-22 减重：
- SQL 层直接按 received_ts_utc > last_ts 过滤（TIMESTAMP 列），空转时查询近零行
- CUR 表不再 .all() 全表扫，增量过滤后仅对有变化的机台广播
- Python 层过滤仍保留为 VARCHAR2 列形态兜底

2026-10-25 解阻塞（test31）：
- 全部DB查询与payload解析移入 asyncio.to_thread 工作线程，事件循环只做 broadcast
- 修复此前每秒一次同步查询期间冻结整个后端（HTTP/WS/AI流式全部停顿）的问题
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import DateTime, inspect

from database import SessionLocal
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager
from services.time_utils import parse_ts

logger = logging.getLogger("fabtwin.db_poller")

# 全局状态
_poller_task = None
_running = False
# 列类型缓存：_TS_IS_TEMPORAL["raw"]=True 表示量产 TIMESTAMP 形态
_TS_IS_TEMPORAL = {}

# 2026-10-29 可观测性：轮询健康指标。此前 db_poller 因同步 startup 从未启动，
# 但 /health 无条件返回 ok，故障完全不可见。用这些指标让 /health 真正能探出它活着。
# VARCHAR2 形态下的轮询窗口（按 raw_id 倒序取的行数）。
# 默认 300：原来硬编码 100，事件突发时容易漏推且无从察觉。
_POLL_WINDOW = int(os.getenv("FABTWIN_POLL_WINDOW", "300"))

_poll_stats = {
    "started_at": None,
    "last_poll_at": None,
    "poll_count": 0,
    "events_pushed": 0,
    "last_error": None,
    "error_count": 0,
}


def poller_health() -> dict:
    """给 /health 用的轮询存活探针。

    判定：任务存在且未完成 + 最近一次轮询在 30s 内 → ok。
    """
    task_alive = _poller_task is not None and not _poller_task.done()
    last = _poll_stats["last_poll_at"]
    if not task_alive:
        return {"status": "dead", "detail": "poller task not running"}
    if last is None:
        return {"status": "starting", "detail": "no poll cycle completed yet"}
    age = (datetime.now() - last).total_seconds()
    status = "ok" if age < 30 else "stalled"
    return {
        "status": status,
        "poll_count": _poll_stats["poll_count"],
        "events_pushed": _poll_stats["events_pushed"],
        "seconds_since_last_poll": round(age, 1),
        "error_count": _poll_stats["error_count"],
        "last_error": _poll_stats["last_error"],
    }


def _detect_ts_column_type(db, table_name: str) -> bool:
    """探测某表的 received_ts_utc 列是否为 TIMESTAMP/DATE 类型"""
    if table_name in _TS_IS_TEMPORAL:
        return _TS_IS_TEMPORAL[table_name]
    temporal = False
    try:
        cols = inspect(db.get_bind()).get_columns(table_name)
        col = next(
            (c for c in cols if str(c.get("name", "")).lower() == "received_ts_utc"),
            None,
        )
        temporal = isinstance(col.get("type"), DateTime) if col else False
    except Exception as e:
        logger.warning("[DB Poller] 探测 %s.received_ts_utc 列类型失败，按字符列处理: %s", table_name, e)
    _TS_IS_TEMPORAL[table_name] = temporal
    return temporal


def _parse_event_payload(raw_event: DT_EVENT_RAW) -> dict:
    """解析DT_EVENT_RAW的payload，返回前端可用的事件格式"""
    try:
        payload = json.loads(raw_event.payload_json) if raw_event.payload_json else {}
    except Exception:
        payload = {}

    event_name = payload.get("event_name", "UNKNOWN")
    event_type = payload.get("event_type", "VFEI")

    # 分类
    category = "other"
    if event_name == "EC_ALARM_REPORT":
        category = "alarm"
    elif event_name in ("POD_PLACED", "POD_REMOVED", "COMPLETED_PORT_LOCK",
                        "COMPLETED_PORT_UNLOCK", "READ_TAG", "WRITE_TAG",
                        "READ_BATTERY", "OPEN_POD", "CLOSE_POD"):
        category = "pod"
    elif event_name in ("BATCH_INFO_FROM_ECUI", "UI_CONFIRM", "ACK_UI_DOUBLECHECK",
                        "REACH_STAGE", "REACH_POS"):
        category = "process"

    # alarm信息
    alarm_info = None
    if category == "alarm":
        alarm_info = {
            "alarm_id": payload.get("alarm_id", ""),
            "alarm_text": payload.get("alarm_text", ""),
            "severity": "warn"
        }

    ts_dt = parse_ts(raw_event.event_ts_utc or raw_event.received_ts_utc)
    ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S") if ts_dt else ""

    # 构造可读描述
    description = payload.get("alarm_text") or payload.get("description") or event_name

    return {
        "raw_id": raw_event.raw_id,
        "tool_id": raw_event.tool_id,
        "event_name": event_name,
        "event_type": event_type,
        "category": category,
        "timestamp": ts_str,
        "description": description,
        "lot_id": payload.get("lot_id"),
        "port_id": payload.get("port_id"),
        "cassette_id": payload.get("cassette_id"),
        "pod_id": payload.get("pod_id"),
        "mode": payload.get("run_mode"),
        "alarm_info": alarm_info,
        "payload": payload,
    }


def _initial_snapshot():
    """启动快照（同步，在 to_thread 中运行）：取最近50条事件并解析，返回正序列表"""
    db = SessionLocal()
    try:
        recent_rows = (
            db.query(DT_EVENT_RAW)
            .order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(50)
            .all()
        )
        if recent_rows:
            recent_rows.sort(key=lambda r: r.raw_id)
            events = [_parse_event_payload(ev) for ev in recent_rows]
            last_ts = parse_ts(recent_rows[-1].received_ts_utc)
            return {"events": events, "last_ts": last_ts}
        return {"events": [], "last_ts": datetime.now() - timedelta(seconds=10)}
    finally:
        db.close()


def _poll_once(state: dict) -> dict:
    """单轮轮询的DB部分（同步，在 to_thread 中运行，绝不阻塞事件循环）

    state: {"last_ts", "raw_is_ts", "cur_is_ts", "poll_count"}，函数内原地更新
    返回: {"raw_events": [...], "cur_list": [...]}
    """
    db = SessionLocal()
    try:
        # 列类型探测一次（量产 TIMESTAMP / 本地 VARCHAR2）
        if state["raw_is_ts"] is None:
            state["raw_is_ts"] = _detect_ts_column_type(db, "dt_event_raw")
            state["cur_is_ts"] = _detect_ts_column_type(db, "dt_event_raw_cur")
            logger.info("[DB Poller] 列类型: raw=%s, cur=%s", state["raw_is_ts"], state["cur_is_ts"])

        # ── DT_EVENT_RAW 增量查询 ──────────────────────────────
        # 窗口大小可配。前提：raw_id 字典序单调（真实 EAP 写 TID.<时间戳> 满足）。
        # 若某路生产者用了别的前缀（如 E2E.xxx），其新事件可能排在窗口之外被漏掉，
        # 故窗口被新事件打满时打告警，便于及早发现。
        window = _POLL_WINDOW
        q_raw = db.query(DT_EVENT_RAW)
        if state["last_ts"] and state["raw_is_ts"]:
            # TIMESTAMP 列：SQL 层直接比时间，空转时查询近零行
            q_raw = q_raw.filter(DT_EVENT_RAW.received_ts_utc > state["last_ts"])
            new_events = q_raw.order_by(DT_EVENT_RAW.raw_id.desc()).limit(window).all()
        else:
            # VARCHAR2 列 / 首次无 last_ts：退化成拉 N 行 + Python 兜底过滤
            all_recent = q_raw.order_by(DT_EVENT_RAW.raw_id.desc()).limit(window).all()
            new_events = []
            for ev in all_recent:
                ev_ts = parse_ts(ev.received_ts_utc)
                if ev_ts and state["last_ts"] and ev_ts > state["last_ts"]:
                    new_events.append(ev)
            if len(all_recent) >= window and len(new_events) >= window:
                logger.warning(
                    "[DB Poller] 轮询窗口(%d)被新事件打满，可能有事件被漏推；"
                    "可调大 FABTWIN_POLL_WINDOW 或确认 raw_id 字典序单调", window
                )

        # 按 raw_id 正序推送
        new_events.sort(key=lambda e: e.raw_id)
        raw_events = []
        for ev in new_events:
            raw_events.append(_parse_event_payload(ev))
            ev_ts = parse_ts(ev.received_ts_utc)
            if ev_ts and (state["last_ts"] is None or ev_ts > state["last_ts"]):
                state["last_ts"] = ev_ts

        # ── DT_EVENT_RAW_CUR 增量查询（不再 .all() 全表扫）──────────
        q_cur = db.query(DT_EVENT_RAW_CUR)
        if state["last_ts"] and state["cur_is_ts"]:
            # 只查变化的机台（空转时零行）
            cur_rows = q_cur.filter(
                DT_EVENT_RAW_CUR.received_ts_utc > state["last_ts"]
            ).all()
        else:
            cur_rows = q_cur.all() if state["poll_count"] == 0 else []  # VARCHAR2 退化成首轮全扫，后续跳过

        cur_list = [_parse_event_payload(ce) for ce in cur_rows]
        state["poll_count"] += 1

        return {"raw_events": raw_events, "cur_list": cur_list}
    finally:
        db.close()


async def poll_db_events():
    """主循环：定期轮询DB中的新事件并通过WebSocket推送

    所有DB查询与payload解析都在 asyncio.to_thread 的工作线程中执行，
    事件循环只负责 broadcast —— 修复此前每秒一次同步查询冻结整个后端的问题。

    启动时先推送最近N条历史事件作为初始快照，让前端一连接就能看到内容。
    之后才开始轮询新事件（时间戳大于state['last_ts']的事件）。
    """
    global _running

    logger.info("[DB Poller] 启动DB事件轮询服务")
    print("[DB Poller] 启动DB事件轮询服务", flush=True)
    _running = True
    _poll_stats["started_at"] = datetime.now()

    # 启动时：推送最近50条历史事件作为初始快照
    try:
        snap = await asyncio.to_thread(_initial_snapshot)
    except Exception as e:
        logger.error("[DB Poller] 启动快照失败: %s", e)
        snap = {"events": [], "last_ts": datetime.now() - timedelta(seconds=10)}
    for event_data in snap["events"]:
        await manager.broadcast({"type": "raw_event", "data": event_data})
    logger.info(
        "[DB Poller] 启动推送 %d 条历史事件，last_ts=%s", len(snap["events"]), snap["last_ts"]
    )
    print(
        f"[DB Poller] 启动推送 {len(snap['events'])} 条历史事件，last_ts={snap['last_ts']}",
        flush=True,
    )

    state = {"last_ts": snap["last_ts"], "raw_is_ts": None, "cur_is_ts": None, "poll_count": 0}

    while _running:
        try:
            result = await asyncio.to_thread(_poll_once, state)

            for event_data in result["raw_events"]:
                await manager.broadcast({"type": "raw_event", "data": event_data})
            if result["raw_events"]:
                logger.info(
                    "[DB Poller] 推送 %d 条事件，最新=%s，tool=%s",
                    len(result["raw_events"]), state["last_ts"], result["raw_events"][0].get("tool_id"),
                )
            if result["cur_list"]:
                await manager.broadcast({"type": "cur_status", "data": result["cur_list"]})

            _poll_stats["last_poll_at"] = datetime.now()
            _poll_stats["poll_count"] += 1
            _poll_stats["events_pushed"] += len(result["raw_events"])

            if state["poll_count"] % 30 == 0:
                print(
                    f"[DB Poller] 心跳: 已轮询{state['poll_count']}次，当前last_ts={state['last_ts']}，"
                    f"WebSocket连接数={len(manager.active)}",
                    flush=True,
                )
        except Exception as e:
            logger.error(f"[DB Poller] 轮询错误: {e}")
            print(f"[DB Poller] 轮询错误: {e}", flush=True)
            _poll_stats["last_error"] = str(e)[:300]
            _poll_stats["error_count"] += 1

        await asyncio.sleep(1.0)  # 每秒轮询一次

    logger.info("[DB Poller] 轮询服务已停止")
    print("[DB Poller] 轮询服务已停止", flush=True)


async def start_db_poller():
    """启动DB轮询服务（单例）"""
    global _poller_task
    if _poller_task is not None and not _poller_task.done():
        logger.warning("[DB Poller] 轮询服务已在运行")
        return
    _poller_task = asyncio.create_task(poll_db_events())


async def stop_db_poller():
    """停止DB轮询服务"""
    global _running, _poller_task
    _running = False
    if _poller_task:
        _poller_task.cancel()
        try:
            await _poller_task
        except asyncio.CancelledError:
            pass
        _poller_task = None
    logger.info("[DB Poller] 已停止")
