# -*- coding: utf-8 -*-
"""AI 用量统计与会话日志（批次2自 ai_middleware.py 拆出）。归属：AI 数据线（张亮）。"""
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


class _UsageMixin:
    """ai_usage_logs 写入与用量统计查询。"""

    def _log_usage(self, session_id: str, config_id: int, provider: str, model: str,
                   prompt_tokens: int, completion_tokens: int, total_tokens: int,
                   question_preview: str, success: bool, error_msg: str = None,
                   provider_name: str = None, answer_preview: str = None,
                   tool_calls: list = None, execution_log: list = None):
        """记录AI调用使用量和执行详情到DB"""
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                # 将列表转为 JSON 字符串存储
                tool_calls_json = json.dumps(tool_calls, ensure_ascii=False, default=str) if tool_calls else None
                execution_log_json = json.dumps(execution_log, ensure_ascii=False, default=str) if execution_log else None
                
                db.add(AIUsageLog(
                    session_id=session_id,
                    config_id=config_id,
                    provider=provider,
                    provider_name=provider_name,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    question_preview=question_preview,
                    answer_preview=answer_preview,
                    success=success,
                    error_msg=error_msg,
                    tool_calls=tool_calls_json,
                    execution_log=execution_log_json,
                    created_at=datetime.now().isoformat(),
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用量记录失败: {e}")
            import traceback
            traceback.print_exc()

    def get_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取使用量统计；CREATED_AT 为 ISO 字符串，按字符串边界和日期前缀统计。"""
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                from sqlalchemy import func
                from datetime import datetime, timedelta

                # Oracle 物理列为 VARCHAR2，禁止 TRUNC/日期隐式转换（ORA-01722）。
                start_date = (datetime.now() - timedelta(days=days)).date().isoformat()
                day_expr = func.substr(AIUsageLog.created_at, 1, 10)
                day_to_str = day_expr

                totals = db.query(
                    func.count(AIUsageLog.id).label("total_calls"),
                    func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0).label("total_prompt"),
                    func.coalesce(func.sum(AIUsageLog.completion_tokens), 0).label("total_completion"),
                    func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
                ).filter(AIUsageLog.created_at >= start_date).first()

                provider_stats = db.query(
                    AIUsageLog.provider,
                    func.count(AIUsageLog.id).label("calls"),
                    func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens"),
                ).filter(AIUsageLog.created_at >= start_date).group_by(AIUsageLog.provider).all()

                provider_breakdown = {}
                for p in provider_stats:
                    provider_breakdown[p.provider or "unknown"] = {
                        "calls": p.calls,
                        "tokens": int(p.tokens),
                    }

                # 按天统计（关键：day_expr 与 GROUP BY 使用同一个 Python 对象，避免绑定参数位置不等价）
                day_col = day_to_str.label("day")
                calls_col = func.count(AIUsageLog.id).label("calls")
                tokens_col = func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens")
                daily = db.query(day_col, calls_col, tokens_col) \
                    .filter(AIUsageLog.created_at >= start_date) \
                    .group_by(day_col) \
                    .order_by(day_col.asc()) \
                    .all()

                daily_stats = []
                for d in daily:
                    # 字符串日期前缀统一为 YYYY-MM-DD；保留历史 DATE 返回值兼容。
                    val = d.day
                    if isinstance(val, datetime):
                        day_str = val.strftime("%Y-%m-%d")
                    else:
                        day_str = str(val)[:10]
                    daily_stats.append({"date": day_str, "calls": d.calls, "tokens": int(d.tokens)})

                return {
                    "total_calls": int(totals.total_calls or 0),
                    "total_prompt_tokens": int(totals.total_prompt or 0),
                    "total_completion_tokens": int(totals.total_completion or 0),
                    "total_tokens": int(totals.total_tokens or 0),
                    "provider_breakdown": provider_breakdown,
                    "daily_stats": daily_stats,
                }
            finally:
                db.close()
        except Exception as e:
            import traceback
            print(f"[AI] 使用量统计失败: {e}")
            traceback.print_exc()
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "provider_breakdown": {},
                "daily_stats": [],
            }

    def get_usage_logs(self, limit: int = 100, offset: int = 0, include_details: bool = True,
                       start_date: str = None, end_date: str = None,
                       provider: str = None, success: bool = None) -> Tuple[List[Dict], int]:
        """获取使用日志列表（支持筛选 + 分页）

        Args:
            limit: 返回条数上限
            offset: 偏移量
            include_details: 是否包含详细执行日志（tool_calls, execution_log, answer）
            start_date: 起始日期 YYYY-MM-DD（包含）
            end_date: 结束日期 YYYY-MM-DD（包含，内部 +1 天）
            provider: Provider 名称精确匹配（local/openai/zhipu/dify/hybrid）
            success: True 只查成功，False 只查失败
        Returns:
            (logs_list, total_count)
        """
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                from sqlalchemy import func

                query = db.query(AIUsageLog)

                # 日期筛选（created_at 存储格式为 "YYYY-MM-DD HH:MM:SS"）
                if start_date:
                    query = query.filter(AIUsageLog.created_at >= start_date)
                if end_date:
                    # end_date + 1 天以包含当天全部
                    from datetime import datetime, timedelta
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    query = query.filter(AIUsageLog.created_at < end_dt.strftime("%Y-%m-%d"))

                # Provider 筛选
                if provider:
                    query = query.filter(AIUsageLog.provider == provider)

                # 成功/失败筛选
                if success is not None:
                    query = query.filter(AIUsageLog.success == success)

                # 总数
                total = query.count()

                # 分页 + 排序
                logs = query.order_by(AIUsageLog.created_at.desc()).offset(offset).limit(limit).all()

                result = []
                for log in logs:
                    item = {
                        "id": log.id,
                        "session_id": log.session_id,
                        "config_id": log.config_id,
                        "provider": log.provider,
                        "provider_name": log.provider_name,
                        "model": log.model,
                        "prompt_tokens": log.prompt_tokens,
                        "completion_tokens": log.completion_tokens,
                        "total_tokens": log.total_tokens,
                        "question_preview": log.question_preview,
                        "success": log.success,
                        "created_at": log.created_at,
                    }

                    # 解析 JSON 字段
                    if include_details:
                        item["answer_preview"] = log.answer_preview
                        item["error_msg"] = log.error_msg

                        # 解析 tool_calls
                        if log.tool_calls:
                            try:
                                item["tool_calls"] = json.loads(log.tool_calls)
                            except (json.JSONDecodeError, TypeError):
                                item["tool_calls"] = []
                        else:
                            item["tool_calls"] = []

                        # 解析 execution_log
                        if log.execution_log:
                            try:
                                item["execution_log"] = json.loads(log.execution_log)
                            except (json.JSONDecodeError, TypeError):
                                item["execution_log"] = []
                        else:
                            item["execution_log"] = []

                    result.append(item)

                return result, total
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用日志查询失败: {e}")
            import traceback
            traceback.print_exc()
            return [], 0

    def get_usage_log_by_id(self, log_id: int) -> Optional[Dict]:
        """获取单条使用日志详情（含全部字段）"""
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                log = db.query(AIUsageLog).filter(AIUsageLog.id == log_id).first()
                if not log:
                    return None

                # 解析 JSON 字段
                tool_calls_parsed = []
                if log.tool_calls:
                    try:
                        tool_calls_parsed = json.loads(log.tool_calls)
                    except (json.JSONDecodeError, TypeError):
                        tool_calls_parsed = []

                execution_log_parsed = []
                if log.execution_log:
                    try:
                        execution_log_parsed = json.loads(log.execution_log)
                    except (json.JSONDecodeError, TypeError):
                        execution_log_parsed = []

                return {
                    "id": log.id,
                    "session_id": log.session_id,
                    "config_id": log.config_id,
                    "provider": log.provider,
                    "provider_name": log.provider_name,
                    "model": log.model,
                    "prompt_tokens": log.prompt_tokens,
                    "completion_tokens": log.completion_tokens,
                    "total_tokens": log.total_tokens,
                    "question_preview": log.question_preview,
                    "success": log.success,
                    "error_msg": log.error_msg,
                    "answer_preview": log.answer_preview,
                    "tool_calls": tool_calls_parsed,
                    "execution_log": execution_log_parsed,
                    "created_at": log.created_at,
                }
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用日志详情查询失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ==================== Provider 多配置管理 ====================

