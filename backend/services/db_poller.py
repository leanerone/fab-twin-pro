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
import re
from datetime import datetime, timedelta

from database import SessionLocal
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager

logger = logging.getLogger("fabtwin.db_poller")

# 全局状态
_poller_task = None
_last_poll_ts = None
_running = False


def _parse_ts(ts) -> datetime:
    """将各种格式的时间戳转换为 datetime 对象

    支持格式：
    - datetime 对象（直接返回）
    - Oracle NLS 中文: "2026-7-23 下午12:01:14"
    - "2026-07-21T00:00:00" (ISO)
    - "2026-07-21 00:00:00" (空格分隔)
    - "2026-07-21T00:00:00.000Z" (带Z后缀)
    """
    if not ts:
        return datetime.min
    if isinstance(ts, datetime):
        return ts
    ts = str(ts).strip()
    if not ts:
        return datetime.min
    ts_clean = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)

    # Oracle NLS 中文格式 "2026-7-23 下午12:01:14"
    nls_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(上午|下午)\s*(\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if nls_match:
        year = int(nls_match.group(1))
        month = int(nls_match.group(2))
        day = int(nls_match.group(3))
        ampm = nls_match.group(4)
        hour = int(nls_match.group(5))
        minute = int(nls_match.group(6))
        second = int(nls_match.group(7))
        if ampm == '下午' and hour != 12:
            hour += 12
        elif ampm == '上午' and hour == 12:
            hour = 0
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass

    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_clean, fmt)
        except ValueError:
            continue

    # 月日不补零的24小时制
    loose_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if loose_match:
        try:
            return datetime(
                int(loose_match.group(1)),
                int(loose_match.group(2)),
                int(loose_match.group(3)),
                int(loose_match.group(4)),
                int(loose_match.group(5)),
                int(loose_match.group(6)),
            )
        except ValueError:
            pass

    return datetime.min


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

    return {
        "raw_id": raw_event.raw_id,
        "tool_id": raw_event.tool_id,
        "event_name": event_name,
        "event_type": event_type,
        "category": category,
        "timestamp": (_parse_ts(raw_event.event_ts_utc or raw_event.received_ts_utc)).strftime("%Y-%m-%d %H:%M:%S"),
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
            _last_poll_ts = _parse_ts(last_ev.received_ts_utc)
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
                    ev_ts = _parse_ts(ev.received_ts_utc)
                    if ev_ts > _last_poll_ts:
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
                        # 更新时间戳（使用datetime）
                        ev_ts = _parse_ts(ev.received_ts_utc)
                        if ev_ts > _last_poll_ts:
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
