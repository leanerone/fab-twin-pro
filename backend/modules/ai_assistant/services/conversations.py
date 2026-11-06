# -*- coding: utf-8 -*-
"""AI 会话管理：用户属主、Dify 映射与内存缓存一致隔离。"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from modules.ai_assistant.services.config_store import _get_db

logger = logging.getLogger("fabtwin.ai_middleware")


def _user_key(user_id) -> str:
    return str(user_id) if user_id is not None else ""


def _session_key(user_id, session_id: str) -> Tuple[str, str]:
    return _user_key(user_id), session_id


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _machine_conflict(first_machine_id, requested_machine_id) -> bool:
    return bool(
        first_machine_id and requested_machine_id
        and str(first_machine_id) != str(requested_machine_id)
    )


class _ConversationsMixin:
    """Dify conversation_id 映射与按用户隔离的会话存储。"""

    def _mapping(self, session_id: str):
        """数据库异常时失败关闭，不能把未知属主会话当成新会话。"""
        from models import AIConversation
        db = _get_db()
        try:
            return db.query(AIConversation).filter(
                AIConversation.session_id == session_id
            ).first()
        except Exception as exc:
            logger.warning("查询会话属主失败: %s", exc)
            raise PermissionError("会话不存在或无权访问") from exc
        finally:
            db.close()

    def _get_or_create_session(
        self, user_id, session_id: Optional[str] = None, machine_id: Optional[str] = None,
    ) -> Dict:
        user_id = _user_key(user_id)
        session_id = session_id or f"sess_{uuid.uuid4().hex[:16]}"
        key = _session_key(user_id, session_id)
        mapping = self._mapping(session_id) if user_id else None
        if mapping is not None:
            if not mapping.user_id or _user_key(mapping.user_id) != user_id:
                # 历史 NULL 只留审计，不允许首个访问者认领。
                raise PermissionError("会话不存在或无权访问")
            if _machine_conflict(mapping.machine_id, machine_id):
                raise ValueError("会话已绑定其他机台")

        for (owner_id, existing_sid), existing in self.sessions.items():
            if existing_sid == session_id and owner_id != user_id:
                raise PermissionError("会话不存在或无权访问")
            if existing_sid == session_id and _machine_conflict(
                existing.get("machine_id"), machine_id
            ):
                raise ValueError("会话已绑定其他机台")

        session = self.sessions.get(key)
        if session is None:
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "machine_id": machine_id or (mapping.machine_id if mapping else None),
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self.sessions[key] = session
        elif not session.get("machine_id") and machine_id:
            # 只允许首次绑定，不允许后续静默换绑。
            session["machine_id"] = machine_id
        return session

    def prepare_chat(
        self, session_id: Optional[str], user_id, machine_id: Optional[str], config_id: Optional[int],
    ) -> Tuple[str, Dict]:
        """在流式响应开始前固定属主、机台和模型配置上下文。"""
        session = self._get_or_create_session(user_id, session_id, machine_id)
        snapshot = self._resolve_chat_config(config_id)
        snapshot["_machine_id"] = session.get("machine_id")
        return session["session_id"], snapshot

    def list_sessions(self, limit: int = 20, user_id: Optional[str] = None) -> List[Dict]:
        """仅列出本人会话，其他用户及历史 NULL 映射不可见。"""
        user_id = _user_key(user_id)
        if not user_id:
            return []
        from models import AIConversation
        by_session: Dict[str, Dict] = {}
        db = _get_db()
        try:
            rows = db.query(AIConversation).filter(
                AIConversation.user_id == user_id
            ).all()
            for row in rows:
                by_session[row.session_id] = {
                    "session_id": row.session_id,
                    "user_id": user_id,
                    "machine_id": row.machine_id,
                    "messages": [],
                    "message_count": 0,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                }
        except Exception as exc:
            logger.warning("读取用户会话映射失败: %s", exc)
        finally:
            db.close()

        for (owner_id, session_id), session in self.sessions.items():
            if owner_id != user_id:
                continue
            item = by_session.get(session_id, {})
            item.update({
                "session_id": session_id,
                "user_id": user_id,
                "machine_id": session.get("machine_id"),
                "messages": session["messages"][-20:],
                "message_count": len(session["messages"]),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
            })
            by_session[session_id] = item
        sessions = sorted(
            by_session.values(), key=lambda item: item.get("updated_at") or "", reverse=True,
        )
        return sessions[:limit]

    def get_session(self, user_id, session_id: str) -> Optional[Dict]:
        """跨用户与 NULL 映射统一表现为不存在。"""
        user_id = _user_key(user_id)
        if not user_id:
            return None
        mapping = self._mapping(session_id)
        if mapping is not None and (
            not mapping.user_id or _user_key(mapping.user_id) != user_id
        ):
            return None
        key = _session_key(user_id, session_id)
        session = self.sessions.get(key)
        if session is not None:
            if _user_key(session.get("user_id")) != user_id:
                return None
            return {
                "session_id": session_id,
                "user_id": user_id,
                "machine_id": session.get("machine_id"),
                "messages": session["messages"],
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
            }
        if any(existing_sid == session_id for _, existing_sid in self.sessions):
            return None
        if mapping is not None:
            return {
                "session_id": session_id,
                "user_id": user_id,
                "machine_id": mapping.machine_id,
                "messages": [],
                "created_at": _iso(mapping.created_at),
                "updated_at": _iso(mapping.updated_at),
            }
        return None

    def _conv_get(self, user_id, session_id: str) -> Optional[str]:
        """按用户+会话获取 Dify ID，不读取或回填其他用户缓存。"""
        user_id = _user_key(user_id)
        if not user_id:
            return None
        key = _session_key(user_id, session_id)
        if key in self._dify_conv_map:
            return self._dify_conv_map[key]
        from models import AIConversation
        db = _get_db()
        try:
            row = db.query(AIConversation).filter(
                AIConversation.user_id == user_id,
                AIConversation.session_id == session_id,
            ).first()
            if row and row.dify_conv_id:
                self._dify_conv_map[key] = row.dify_conv_id
                return row.dify_conv_id
        except Exception as exc:
            logger.warning("查询 Dify 会话映射失败: %s", exc)
            raise PermissionError("会话不存在或无权访问") from exc
        finally:
            db.close()
        return None

    def _conv_put(
        self, user_id, session_id: str, dify_conv_id: str, machine_id: Optional[str] = None,
    ) -> None:
        """属主必填；NULL 不可认领，首次机台绑定后不可覆盖。"""
        user_id = _user_key(user_id)
        if not user_id:
            raise PermissionError("会话属主不能为空")
        key = _session_key(user_id, session_id)
        self._dify_conv_map[key] = str(dify_conv_id)
        from models import AIConversation
        db = _get_db()
        try:
            row = db.query(AIConversation).filter(
                AIConversation.session_id == session_id
            ).first()
            if row is not None and (
                not row.user_id or _user_key(row.user_id) != user_id
            ):
                raise PermissionError("会话不存在或无权访问")
            if row is not None and _machine_conflict(row.machine_id, machine_id):
                raise ValueError("会话已绑定其他机台")
            now = datetime.now().isoformat()
            if row is None:
                row = AIConversation(
                    session_id=session_id,
                    user_id=user_id,
                    machine_id=machine_id or "",
                    dify_conv_id=str(dify_conv_id),
                    provider="dify",
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.dify_conv_id = str(dify_conv_id)
                row.updated_at = now
                if not row.machine_id and machine_id:
                    row.machine_id = machine_id
            db.commit()
        except Exception:
            db.rollback()
            self._dify_conv_map.pop(key, None)
            raise
        finally:
            db.close()

    def clear_session(self, user_id, session_id: str) -> bool:
        """只清理本人内存、Dify 映射和缓存。"""
        user_id = _user_key(user_id)
        if not user_id or self.get_session(user_id, session_id) is None:
            return False
        from models import AIConversation
        db = _get_db()
        try:
            db.query(AIConversation).filter(
                AIConversation.user_id == user_id,
                AIConversation.session_id == session_id,
            ).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("删除 Dify 会话映射失败: %s", exc)
            return False
        finally:
            db.close()
        self.sessions.pop(_session_key(user_id, session_id), None)
        self._dify_conv_map.pop(_session_key(user_id, session_id), None)
        return True

    def _cleanup_old_conversations(self, days: int = 7, user_id: Optional[str] = None) -> int:
        """必须指定属主；禁止启动时无差别清理全部用户映射。"""
        user_id = _user_key(user_id)
        if not user_id:
            raise ValueError("清理会话必须指定用户")
        from models import AIConversation
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        db = _get_db()
        try:
            rows = db.query(AIConversation).filter(
                AIConversation.user_id == user_id,
                AIConversation.updated_at < cutoff,
            ).all()
            session_ids = {row.session_id for row in rows}
            for row in rows:
                db.delete(row)
            db.commit()
            for session_id in session_ids:
                self._dify_conv_map.pop(_session_key(user_id, session_id), None)
            return len(session_ids)
        except Exception as exc:
            db.rollback()
            logger.warning("清理过期会话失败: %s", exc)
            return 0
        finally:
            db.close()
