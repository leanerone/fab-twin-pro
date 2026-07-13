"""WebSocket 实时推送服务：管理连接并广播事件"""
import logging
from typing import List

from fastapi import WebSocket

logger = logging.getLogger("fabtwin.realtime")


class ConnectionManager:
    """管理所有 WebSocket 连接，支持向全部客户端广播消息"""

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受新连接并加入活跃列表"""
        await websocket.accept()
        self.active.append(websocket)
        logger.info("WebSocket 已连接，当前连接数 %d", len(self.active))

    def disconnect(self, websocket: WebSocket):
        """移除断开的连接"""
        if websocket in self.active:
            self.active.remove(websocket)
        logger.info("WebSocket 已断开，当前连接数 %d", len(self.active))

    async def broadcast(self, message: dict):
        """向所有活跃连接广播 JSON 消息，自动清理失效连接"""
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# 全局连接管理器单例
manager = ConnectionManager()
