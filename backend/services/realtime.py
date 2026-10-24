"""WebSocket 实时推送服务：管理连接并广播事件"""
import asyncio
import logging
from typing import List, Optional

from fastapi import WebSocket

logger = logging.getLogger("fabtwin.realtime")


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

        test31：单连接发送加 3s 超时——此前串行 await 无超时，一个慢客户端
        （弱网/挂起页）能让广播卡住，进而拖住 db_poller 轮询协程。
        超时的连接视为失效并清理。
        """
        dead = []
        for ws in self.active:
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=3.0)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# 全局连接管理器单例
manager = ConnectionManager()
