# -*- coding: utf-8 -*-
"""AI 会话管理（批次2自 ai_middleware.py 拆出）。归属：AI 应用线。"""
import os
import re
import json
import time
import uuid
import asyncio
import logging
import httpx
import requests
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger("fabtwin.ai_middleware")

from config import (
    AI_MCP_ENABLED, AI_MCP_URL, AI_MCP_API_KEY,
    AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
    AI_TEMPERATURE, AI_MAX_TOKENS,
    DIFY_ENABLED, DIFY_BASE_URL, DIFY_API_KEY, DIFY_APP_ID,
    N8N_ENABLED, N8N_BASE_URL, N8N_WEBHOOK_SECRET,
)
from services.ai.config_store import _get_db, PROVIDER_PRESETS, CONFIG_KEYS
from services.ai.tools import (
    get_machine_status,
    get_machine_alarms,
    get_event_timeline,
    get_yield_stats,
    get_lot_info,
    get_recipe_info,
    TOOL_DEFINITIONS,
    TOOL_HANDLERS,
)


class _ConversationsMixin:
    """Dify conversation_id 映射与会话内存存储。"""

    def _conv_get(self, sid_key: str) -> Optional[str]:
        cid = self._dify_conv_map.get(sid_key)
        if cid:
            return cid
        try:
            db = _get_db()
            try:
                from models import AIConversation
                row = (db.query(AIConversation)
                       .filter(AIConversation.session_id == sid_key)
                       .order_by(AIConversation.updated_at.desc())
                       .first())
                if row and row.dify_conv_id:
                    self._dify_conv_map[sid_key] = row.dify_conv_id
                    print(f"[Dify] 会话映射已从DB恢复: {sid_key} -> {row.dify_conv_id}")
                    return row.dify_conv_id
            finally:
                db.close()
        except Exception as e:
            print(f"[Dify] 会话映射查库失败（降级纯内存）: {str(e)[:120]}")
        return None

    def _conv_put(self, sid_key: str, dify_cid, machine_id: str = None):
        self._dify_conv_map[sid_key] = str(dify_cid)
        try:
            db = _get_db()
            try:
                from models import AIConversation
                now = datetime.now().isoformat()
                row = (db.query(AIConversation)
                       .filter(AIConversation.session_id == sid_key)
                       .first())
                if row:
                    row.dify_conv_id = str(dify_cid)
                    row.updated_at = now
                    if machine_id:
                        row.machine_id = machine_id
                else:
                    db.add(AIConversation(
                        session_id=sid_key,
                        machine_id=machine_id or "",
                        dify_conv_id=str(dify_cid),
                        provider="dify",
                        created_at=now,
                        updated_at=now,
                    ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[Dify] 会话映射落库失败（仅内存）: {str(e)[:120]}")

    def _cleanup_old_conversations(self, days: int = 7):
        """清理超过 N 天未更新的会话映射（表未建/异常则跳过，不影响启动）"""
        try:
            db = _get_db()
            try:
                from models import AIConversation
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                n = (db.query(AIConversation)
                     .filter(AIConversation.updated_at < cutoff)
                     .delete(synchronize_session=False))
                db.commit()
                if n:
                    print(f"[AI] 已清理 {n} 条超过 {days} 天未更新的 Dify 会话映射")
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 会话映射清理跳过: {str(e)[:120]}")



    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        return self.sessions.get(session_id)

    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self, limit: int = 20, user_id: Optional[str] = None) -> List[Dict]:
        """列出会话（最近的）。传入 user_id 时只返回该用户的会话。"""
        sessions = list(self.sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.get("user_id") == user_id]
        return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)[:limit]


