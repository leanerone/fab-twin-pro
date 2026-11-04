"""WebSocket 实时推送服务：管理连接并广播事件"""
import asyncio
import logging
from typing import List, Optional

from fastapi import WebSocket

logger = logging.getLogger("fabtwin.realtime")

# raw_event 广播去重（FIFO 有界集合；去重判定在事件循环内串行执行，无并发问题）
_RAW_DEDUP_MAX = 512
_raw_dedup_order: list = []
_raw_dedup_seen: set = set()


def _raw_event_seen(raw_id) -> bool:
    """登记并判断 raw_id 是否已广播过；空 raw_id 不去重"""
    key = str(raw_id or "").strip()
    if not key:
        return False
    if key in _raw_dedup_seen:
        return True
    _raw_dedup_seen.add(key)
    _raw_dedup_order.append(key)
    if len(_raw_dedup_order) > _RAW_DEDUP_MAX:
        _raw_dedup_seen.discard(_raw_dedup_order.pop(0))
    return False


class ConnectionManager:
    """管理所有 WebSocket 连接，支持向全部客户端广播消息"""

    def __init__(self):
        self.active: List[WebSocket] = []
        # 事件循环引用：在 async 上下文（WS连接）中捕获，
        # 供线程池里的同步代码（如 rvmessages）通过 run_coroutine_threadsafe 广播
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        """接受新连接并加入活跃列表"""
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active.append(websocket)
        logger.info("WebSocket 已连接，当前连接数 %d", len(self.active))

    def disconnect(self, websocket: WebSocket):
        """移除断开的连接"""
        if websocket in self.active:
            self.active.remove(websocket)
        logger.info("WebSocket 已断开，当前连接数 %d", len(self.active))

    def broadcast_from_thread(self, message: dict):
        """线程池上下文安全广播：调度到事件循环执行；无循环/无连接时静默跳过"""
        if self.loop is not None and not self.loop.is_closed() and self.active:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

    async def broadcast(self, message: dict):
        """向所有活跃连接广播 JSON 消息，自动清理失效连接

        2026-10-29 修复：原实现是串行 await，每个连接最长等 3s，N 个客户端最坏
        O(N × 3s)——100 个客户端时一轮广播可能耗时 300s，直接把 db_poller 的轮询
        协程堵死（每秒一轮，广播不返回就永远不轮询下一轮）。
        改为 asyncio.gather 并发发送：单连接仍有 3s 超时保护，但总耗时取决于
        最慢的那个连接，而不是所有连接之和。

        2026-10-30 修复（raw_event 重复投递）：同一条事件会经过两条广播路径——
        POST /api/rv/message 写库后即时广播一次，db_poller 扫描又对同一 raw_id
        广播一次（tests/perf/test_dup_delivery.py 复现）。前端按 raw_id 消费，
        重复投递导致事件计数 / 告警数 / 晶圆数翻倍。在广播汇聚点按 raw_id 去重：
        首次广播登记 raw_id（有界 FIFO，512 条），重复投递静默丢弃。
        """
        if message.get("type") == "raw_event":
            raw_id = (message.get("data") or {}).get("raw_id")
            if raw_id and _raw_event_seen(raw_id):
                return
        targets = list(self.active)
        if not targets:
            return

        async def _send(ws):
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=3.0)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*(_send(ws) for ws in targets),
                                       return_exceptions=True)
        for ws, res in zip(targets, results):
            if res is not None and not isinstance(res, BaseException):
                self.disconnect(res)


# 全局连接管理器单例
manager = ConnectionManager()
