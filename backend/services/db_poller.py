"""DB事件轮询服务：从DT_EVENT_RAW表读取新事件并通过WebSocket推送

与模拟器的区别：
- 模拟器：主动生成事件写入DB
- 轮询服务：从DB读取外部写入的事件（如WinForm工具写入），推送到前端

两种模式可以同时运行：
- DEMO模式：模拟器生成事件
- 真实模式：WinForm/外部系统写入DB，轮询服务读取推送
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta

from database import SessionLocal
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager
from services.time_utils import parse_ts

logger = logging.getLogger("fabtwin.db_poller")

# 全局状态
_poller_task = None
_last_poll_ts = None
_running = False


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
    while _running:
        try:
            db = SessionLocal()
            try:
                # 查询最近事件（用raw_id降序，近似时间顺序；VARCHAR2时间排序不可靠）
                all_recent = db.query(DT_EVENT_RAW).order_by(
                    DT_EVENT_RAW.raw_id.desc()
                ).limit(100).all()

                new_events = []
                for ev in all_recent:
                    ev_ts = parse_ts(ev.received_ts_utc)
                    if ev_ts and _last_poll_ts and ev_ts > _last_poll_ts:
                        new_events.append(ev)

                # 按raw_id正序排列（近似时间正序）
                new_events.sort(key=lambda e: e.raw_id)

                if new_events:
                    for ev in new_events:
                        event_data = _parse_event_payload(ev)
                        # 通过WebSocket广播
                        await manager.broadcast({
                            "type": "raw_event",
                            "data": event_data
                        })
                        # 更新时间戳
                        ev_ts = parse_ts(ev.received_ts_utc)
                        if ev_ts and ev_ts > _last_poll_ts:
                            _last_poll_ts = ev_ts

                    logger.info(f"[DB Poller] 推送 {len(new_events)} 条新事件，最新时间: {_last_poll_ts}")
                    print(f"[DB Poller] 推送 {len(new_events)} 条新事件，最新时间: {_last_poll_ts}", flush=True)
                    # 打印第一条事件详情便于调试
                    first_ev = new_events[0]
                    first_data = _parse_event_payload(first_ev)
                    print(f"[DB Poller] 首条事件: tool_id={first_data.get('tool_id')}, event_name={first_data.get('event_name')}, ts={first_data.get('timestamp')}", flush=True)

                # 也检查CUR表，推送当前状态
                cur_events = db.query(DT_EVENT_RAW_CUR).all()
                if cur_events:
                    cur_list = []
                    for ce in cur_events:
                        cur_list.append(_parse_event_payload(ce))
                    await manager.broadcast({
                        "type": "cur_status",
                        "data": cur_list
                    })

                poll_count += 1
                # 每30秒打印一次心跳日志，确认轮询服务存活
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
