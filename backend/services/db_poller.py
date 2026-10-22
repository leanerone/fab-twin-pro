"""DB事件轮询服务：从DT_EVENT_RAW表读取新事件并通过WebSocket推送

与模拟器的区别：
- 模拟器：主动生成事件写入DB
- 轮询服务：从DB读取外部写入的事件（如WinForm工具写入），推送到前端

两种模式可以同时运行：
- DEMO模式：模拟器生成事件
- 真实模式：WinForm/外部系统写入DB，轮询服务读取推送

2026-10-22 减重：
- SQL 层直接按 received_ts_utc > _last_poll_ts 过滤（TIMESTAMP 列），空转时查询近零行
- CUR 表不再 .all() 全表扫，增量过滤后仅对有变化的机台广播
- Python 层过滤仍保留为 VARCHAR2 列形态兜底
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import DateTime, inspect

from database import SessionLocal
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager
from services.time_utils import parse_ts

logger = logging.getLogger("fabtwin.db_poller")

# 全局状态
_poller_task = None
_last_poll_ts = None
_running = False
# 列类型缓存：_TS_IS_TEMPORAL["raw"]=True 表示量产 TIMESTAMP 形态
_TS_IS_TEMPORAL = {}


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


async def poll_db_events():
    """主循环：定期轮询DB中的新事件

    启动时先推送最近N条历史事件作为初始快照，让前端一连接就能看到内容。
    之后才开始轮询新事件（时间戳大于_last_poll_ts的事件）。
    """
    global _last_poll_ts, _running

    logger.info("[DB Poller] 启动DB事件轮询服务")
    print("[DB Poller] 启动DB事件轮询服务", flush=True)
    _running = True

    # 启动时：推送最近50条历史事件作为初始快照
    db = SessionLocal()
    try:
        recent_rows = (
            db.query(DT_EVENT_RAW)
            .order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(50)
            .all()
        )
        if recent_rows:
            # 按时间正序推送（raw_id升序，近似时间顺序）
            recent_rows.sort(key=lambda r: r.raw_id)
            pushed = 0
            for ev in recent_rows:
                event_data = _parse_event_payload(ev)
                await manager.broadcast({
                    "type": "raw_event",
                    "data": event_data
                })
                pushed += 1
            # _last_poll_ts 设为最新事件时间，之后只推送更新的
            last_ev = recent_rows[-1]
            _last_poll_ts = parse_ts(last_ev.received_ts_utc)
            logger.info(f"[DB Poller] 启动推送 {pushed} 条历史事件，_last_poll_ts={_last_poll_ts}")
            print(f"[DB Poller] 启动推送 {pushed} 条历史事件，_last_poll_ts={_last_poll_ts}", flush=True)
        else:
            _last_poll_ts = datetime.now() - timedelta(seconds=10)
            logger.info(f"[DB Poller] 数据库无数据，初始时间设置为当前时间前10秒: {_last_poll_ts}")
            print(f"[DB Poller] 数据库无数据，初始时间设置为当前时间前10秒: {_last_poll_ts}", flush=True)
    finally:
        db.close()

    poll_count = 0
    # 列类型探测一次（量产 TIMESTAMP / 本地 VARCHAR2）
    raw_is_ts = None
    cur_is_ts = None

    while _running:
        try:
            db = SessionLocal()
            try:
                if raw_is_ts is None:
                    raw_is_ts = _detect_ts_column_type(db, "dt_event_raw")
                    cur_is_ts = _detect_ts_column_type(db, "dt_event_raw_cur")
                    logger.info("[DB Poller] 列类型: raw=%s, cur=%s", raw_is_ts, cur_is_ts)

                # ── DT_EVENT_RAW 增量查询 ──────────────────────────────
                q_raw = db.query(DT_EVENT_RAW)
                if _last_poll_ts and raw_is_ts:
                    # TIMESTAMP 列：SQL 层直接比时间，空转时查询近零行
                    q_raw = q_raw.filter(DT_EVENT_RAW.received_ts_utc > _last_poll_ts)
                    recent = q_raw.order_by(DT_EVENT_RAW.raw_id.desc()).limit(100).all()
                    new_events = recent  # 已经是增量，跳过 Python 层二次过滤
                else:
                    # VARCHAR2 列 / 首次无 _last_poll_ts：退化成拉 100 行 + Python 兜底过滤
                    all_recent = q_raw.order_by(DT_EVENT_RAW.raw_id.desc()).limit(100).all()
                    new_events = []
                    for ev in all_recent:
                        ev_ts = parse_ts(ev.received_ts_utc)
                        if ev_ts and _last_poll_ts and ev_ts > _last_poll_ts:
                            new_events.append(ev)

                # 按 raw_id 正序推送
                new_events.sort(key=lambda e: e.raw_id)
                for ev in new_events:
                    event_data = _parse_event_payload(ev)
                    await manager.broadcast({"type": "raw_event", "data": event_data})
                    ev_ts = parse_ts(ev.received_ts_utc)
                    if ev_ts and (_last_poll_ts is None or ev_ts > _last_poll_ts):
                        _last_poll_ts = ev_ts

                if new_events:
                    first_data = _parse_event_payload(new_events[0])
                    logger.info("[DB Poller] 推送 %d 条事件，最新=%s，tool=%s", len(new_events), _last_poll_ts, first_data.get('tool_id'))

                # ── DT_EVENT_RAW_CUR 增量查询（不再 .all() 全表扫）──────────
                q_cur = db.query(DT_EVENT_RAW_CUR)
                if _last_poll_ts and cur_is_ts:
                    # 只查变化的机台（空转时零行）
                    cur_rows = q_cur.filter(
                        DT_EVENT_RAW_CUR.received_ts_utc > _last_poll_ts
                    ).all()
                else:
                    cur_rows = q_cur.all() if poll_count == 0 else []  # VARCHAR2 退化成首轮全扫，后续跳过

                if cur_rows:
                    cur_list = [_parse_event_payload(ce) for ce in cur_rows]
                    await manager.broadcast({"type": "cur_status", "data": cur_list})

                poll_count += 1
                if poll_count % 30 == 0:
                    print(f"[DB Poller] 心跳: 已轮询{poll_count}次，当前_last_poll_ts={_last_poll_ts}，WebSocket连接数={len(manager.active)}", flush=True)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"[DB Poller] 轮询错误: {e}")
            print(f"[DB Poller] 轮询错误: {e}", flush=True)

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
