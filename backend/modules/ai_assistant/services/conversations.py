# -*- coding: utf-8 -*-
"""AI 会话管理（批次2自 middleware.py 拆出）。归属：AI 应用线。"""
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
from modules.ai_assistant.services.config_store import _get_db, PROVIDER_PRESETS, CONFIG_KEYS
from modules.ai_assistant.services.tools import (
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
    """Dify conversation_id 映射与会话存储（内存 LRU + DB 持久化）。

    T3 2026-11-06 之前：消息只存 self.sessions 内存字典——后端重启前端"失忆"，
    且字典无淘汰长运行无界增长。现在：
      - 内存字典 = LRU 缓存（上限 MAX_MEMORY_SESSIONS，按 created_at 淘汰最旧）
      - 每轮对话落库 ai_chat_sessions（messages JSON），重启后从 DB 恢复
      - _dify_conv_map 运行时上限 500（DB 侧已有 7 天清理兜底）
    """

    MAX_MEMORY_SESSIONS = 200
    MAX_DIFY_CONV_MAP = 500

    # ---------- 内存会话（LRU + DB 恢复） ----------

    def _get_or_create_session(self, session_id: str, machine_id: str = None) -> Dict:
        """取会话：内存命中 → 直接用；未命中 → 先试 DB 恢复，再不行新建空会话"""
        s = self.sessions.get(session_id)
        if s is not None:
            return s
        restored = self._load_session_from_db(session_id)
        if restored is not None:
            print(f"[AI] 会话已从 DB 恢复: {session_id}（{len(restored.get('messages', []))} 条消息）")
            self.sessions[session_id] = restored
            self._evict_memory_sessions()
            return restored
        s = {
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "machine_id": machine_id,
        }
        self.sessions[session_id] = s
        self._evict_memory_sessions()
        return s

    def _load_session_from_db(self, session_id: str) -> Optional[Dict]:
        try:
            db = _get_db()
            try:
                from models import AIChatSession
                row = (db.query(AIChatSession)
                       .filter(AIChatSession.session_id == session_id)
                       .first())
                if row and row.messages:
                    data = json.loads(row.messages)
                    if isinstance(data, list) and data:
                        return {
                            "messages": data,
                            "created_at": row.created_at or datetime.now().isoformat(),
                            "machine_id": row.machine_id or None,
                            "restored_from_db": True,
                        }
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 会话从DB恢复失败（降级新建）: {str(e)[:120]}")
        return None

    def _evict_memory_sessions(self):
        """内存会话超上限时按 created_at 淘汰最旧（DB 里仍有，可再恢复）"""
        over = len(self.sessions) - self.MAX_MEMORY_SESSIONS
        if over <= 0:
            return
        items = sorted(self.sessions.items(), key=lambda kv: kv[1].get("created_at", ""))
        for sid, _s in items[:over]:
            self.sessions.pop(sid, None)
            print(f"[AI] 内存会话超上限，淘汰: {sid}")

    def _persist_session(self, session_id: str, session: Dict):
        """每轮对话后落库。失败仅打印——持久化不允许影响主链路。"""
        try:
            db = _get_db()
            try:
                from models import AIChatSession
                now = datetime.now().isoformat()
                msgs = session.get("messages", [])
                payload = json.dumps(msgs, ensure_ascii=False, default=str)
                row = db.query(AIChatSession).filter(AIChatSession.session_id == session_id).first()
                if row:
                    row.messages = payload
                    row.message_count = len(msgs)
                    if session.get("machine_id"):
                        row.machine_id = session["machine_id"]
                    row.updated_at = now
                else:
                    db.add(AIChatSession(
                        session_id=session_id,
                        machine_id=session.get("machine_id") or "",
                        messages=payload,
                        message_count=len(msgs),
                        created_at=session.get("created_at") or now,
                        updated_at=now,
                    ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 会话落库失败（仅内存）: {str(e)[:120]}")

    def _cleanup_old_chat_sessions(self, days: int = 30):
        """清理超过 N 天未更新的聊天会话（表未建则跳过）"""
        try:
            db = _get_db()
            try:
                from models import AIChatSession
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                n = (db.query(AIChatSession)
                     .filter(AIChatSession.updated_at < cutoff)
                     .delete(synchronize_session=False))
                db.commit()
                if n:
                    print(f"[AI] 已清理 {n} 条超过 {days} 天未更新的聊天会话")
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 聊天会话清理跳过: {str(e)[:120]}")

    # ---------- Dify conversation_id 映射 ----------

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
        # T3：运行时上限（dict 保持插入序，FIFO 淘汰最早的映射；DB 侧仍有 7 天清理兜底）
        if len(self._dify_conv_map) > self.MAX_DIFY_CONV_MAP:
            for k in list(self._dify_conv_map.keys())[:len(self._dify_conv_map) - self.MAX_DIFY_CONV_MAP]:
                self._dify_conv_map.pop(k, None)
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
        """清除会话（内存 + DB 落库记录一并清，T3 2026-11-06）"""
        existed = session_id in self.sessions
        if existed:
            del self.sessions[session_id]
        db_deleted = False
        try:
            db = _get_db()
            try:
                from models import AIChatSession
                n = (db.query(AIChatSession)
                     .filter(AIChatSession.session_id == session_id)
                     .delete(synchronize_session=False))
                db.commit()
                db_deleted = n > 0
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 会话DB删除失败（内存已清）: {str(e)[:120]}")
        return existed or db_deleted

    def list_sessions(self, limit: int = 20, user_id: Optional[str] = None) -> List[Dict]:
        """列出会话（最近的）。传入 user_id 时只返回该用户的会话。"""
        sessions = list(self.sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.get("user_id") == user_id]
        return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)[:limit]


