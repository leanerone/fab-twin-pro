# -*- coding: utf-8 -*-
"""Dify Provider（批次2自 ai_middleware.py 拆出）：同步调用 + 异步 SSE 流。
归属：AI 应用线（朱明钊）。"""
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


class _DifyMixin:
    """Dify chat-messages 调用与 SSE 流消费。"""

    def _consume_dify_stream(self, resp) -> Dict[str, Any]:
        """把 Dify streaming(SSE) 响应聚合成与 blocking 相同结构的 dict。

        因为在【Agent 智能体应用】下 Dify 只支持 streaming，后端统一改用 streaming；
        此方法在本地把 SSE 的分片 answer 拼接完整，并提取 conversation_id / usage / RAG引用。

        Dify streaming 事件摘要：
          - message / agent_message : {event, answer(分片), conversation_id, ...}  ← 聚合 answer
          - message_end             : {event, metadata:{usage:{...}}, conversation_id} ← 用 token 用量
          - retriever_resources     : {event, records:[...]}                         ← RAG 引用
          - workflow_finished       : 工作流类应用结果放在 data.outputs
          每个事件以 'data: ' 开头，最后一行是 'data: [DONE]'。
        返回值字段与旧 blocking 的 resp.json() 一致：answer / conversation_id / metadata / retriever_resources，
        以便 _call_dify() 后续处理逻辑（usage 计费 / RAG sources / <FABTWIN> 提取）原样复用。
        """
        import json as _j
        answer_chunks = []
        conv_id = None
        usage = None
        rag_records = []
        workflow_outputs = None
        try:
            for raw in resp.iter_lines():
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
                line = (line or "").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                else:
                    data_str = line
                try:
                    evt = _j.loads(data_str)
                except Exception:
                    continue
                if not isinstance(evt, dict):
                    continue
                event = evt.get("event")
                # chat/chatflow/agent 类应用：answer 分片来自 message / agent_message / message_replace
                if event in ("message", "agent_message", "message_replace"):
                    chunk = evt.get("answer")
                    if isinstance(chunk, str):
                        answer_chunks.append(chunk)
                    if not conv_id:
                        conv_id = evt.get("conversation_id")
                elif event == "message_end":
                    meta = evt.get("metadata") or {}
                    if isinstance(meta.get("usage"), dict):
                        usage = meta.get("usage")
                    if not conv_id:
                        conv_id = evt.get("conversation_id")
                elif event == "retriever_resources":
                    records = evt.get("records") or []
                    for r in records:
                        if isinstance(r, dict):
                            rag_records.append(r)
                elif event == "workflow_finished":
                    wdata = evt.get("data") or {}
                    wouts = wdata.get("outputs")
                    if isinstance(wouts, dict):
                        workflow_outputs = wouts
        except Exception as e:
            print(f"[Dify] SSE 解析异常: {type(e).__name__}: {e}")

        answer = "".join(answer_chunks)
        # 兜底：若为工作流类应用，流里没有 message/agent_message 事件 → 尝试从 workflow_finished.outputs 取文本
        if not answer and isinstance(workflow_outputs, dict):
            for key in ("text", "answer", "output", "result"):
                if key in workflow_outputs and isinstance(workflow_outputs[key], str):
                    answer = workflow_outputs[key]
                    break

        metadata = {}
        if usage is not None:
            metadata["usage"] = usage
        return {
            "answer": answer,
            "conversation_id": conv_id,
            "metadata": metadata,
            "retriever_resources": rag_records,
        }

    async def _stream_dify(self, question: str, session_id: str, machine_id: str = None,
                           user_role: str = "user", stream_result: Dict = None,
                           dify_cfg: Dict = None):
        """异步流式调用 Dify，逐事件 yield（透传帧，dict 形态）。

        与 _call_dify 的差异：
        - 不在本地聚合等待完整答案，而是逐 SSE 事件 yield 给 chat_stream 透传前端
        - 正文分片（message/agent_message/message_replace）经 <FABTWIN> lookahead 过滤：
          标记块内的结构化 JSON 不下发，累积到 stream_result["fab_text"] 供收尾解析
        - 聚合结果写入调用方传入的 stream_result（并发安全，不用实例属性）：
          answer / conversation_id / usage / rag_records / fab_text / thoughts_count

        请求构造、conversation_id 映射、4xx inputs 回退重试与 _call_dify 一致。
        """
        if stream_result is None:
            stream_result = {}
        stream_result.update({
            "answer": "", "conversation_id": None, "usage": None,
            "rag_records": [], "fab_text": "", "thoughts_count": 0,
        })

        # test31：请求级配置（机台专属 Dify 传入 dify_cfg；未传时读全局单例）
        cfg = dify_cfg or {
            "enabled": self.dify_enabled,
            "base_url": self.dify_base_url,
            "api_key": self.dify_api_key,
        }
        if not cfg.get("enabled") or not cfg.get("base_url") or not cfg.get("api_key"):
            raise RuntimeError(
                "Dify 未启用或缺少配置（dify_base_url/dify_api_key 为空），未做本地兜底。"
                "请检查全局 Dify 配置或机台专属 Dify 配置。"
            )

        base = cfg["base_url"].rstrip('/')
        url = f"{base}/chat-messages" if base.endswith('/v1') else f"{base}/v1/chat-messages"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        }
        meta = self._get_machine_metadata(machine_id)
        inputs = {
            "machine_id": machine_id or "",
            "user_role": user_role or "user",
        }
        if meta.get("machine_model"):
            inputs["machine_model"] = meta["machine_model"]
        if meta.get("chambers"):
            inputs["chambers"] = int(meta["chambers"])
        payload = {
            "inputs": inputs,
            "query": question,
            "response_mode": "streaming",
            "user": f"fabtwin_{user_role}" if user_role else "fabtwin_user",
        }
        # conversation_id 规则同 _call_dify：必须是 Dify 返回的 UUID，首次不传
        sid_key = str(session_id).strip() if session_id else ""
        dify_cid = self._conv_get(sid_key) if sid_key else None
        if dify_cid:
            payload["conversation_id"] = dify_cid

        conv_info = f"session={sid_key or '(none)'}" + (
            f" → dify_cid={dify_cid}" if dify_cid else " → 首次请求(无conversation_id)"
        )
        print(f"[Dify-stream] → POST {url}, {conv_info}, query_len={len(question)}")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = None
            retry_resp = None
            try:
                resp = await client.send(
                    client.build_request("POST", url, json=payload, headers=headers),
                    stream=True,
                )
                # ---------- 4xx inputs 回退重试（与 _call_dify 同逻辑） ----------
                body_txt = ""
                body_json = {}
                if 400 <= resp.status_code < 500:
                    body_txt = (await resp.aread()).decode("utf-8", "replace")
                    try:
                        body_json = json.loads(body_txt) if body_txt else {}
                    except Exception:
                        body_json = {}
                    msg = body_json.get("message") or body_json.get("error") or body_txt[:500]
                    print(f"[Dify-stream] × HTTP {resp.status_code}（首次请求，尝试兼容回退）: {str(msg)[:300]}")
                    if (("inputs" in str(msg).lower() or "field" in str(msg).lower() or "param" in str(msg).lower())
                            and payload.get("inputs") != {}):
                        payload2 = dict(payload)
                        payload2["inputs"] = {}
                        print(f"[Dify-stream] ↻ 回退重试：清空 inputs")
                        await resp.aclose()
                        retry_resp = await client.send(
                            client.build_request("POST", url, json=payload2, headers=headers),
                            stream=True,
                        )
                        if retry_resp.status_code < 400:
                            resp = retry_resp
                            retry_resp = None
                            print(f"[Dify-stream] [OK] 回退重试成功 HTTP {resp.status_code}")
                    if resp.status_code >= 400:
                        dify_msg = (body_json.get("message") or body_json.get("error")
                                    or body_json.get("detail") or "")
                        if isinstance(dify_msg, list):
                            dify_msg = "; ".join(str(x) for x in dify_msg)
                        raise RuntimeError(
                            f"Dify HTTP {resp.status_code}: "
                            f"{dify_msg or ('无 message 字段，原始body: ' + (body_txt or '')[:400])}"
                        )
                resp.raise_for_status()

                # ---------- 逐事件透传 + FABTWIN 过滤 ----------
                fab_tag = self._FAB_TAG
                keep = len(fab_tag) - 1   # lookahead：保留末尾 8 字符防标记跨 chunk
                pending = ""              # 正文 lookahead 缓冲
                fab_mode = False          # 已进入 <FABTWIN> 块（后续内容全部吞掉）
                answer_parts = []
                fab_parts = []

                def _filter_text(text):
                    """正文分片经 FABTWIN 过滤，返回可下发的文本段列表"""
                    nonlocal pending, fab_mode
                    out = []
                    if fab_mode:
                        fab_parts.append(text)
                        return out
                    pending += text
                    idx = pending.find(fab_tag)
                    if idx >= 0:
                        if idx > 0:
                            out.append(pending[:idx])
                        fab_parts.append(pending[idx:])
                        pending = ""
                        fab_mode = True
                    elif len(pending) > keep:
                        out.append(pending[:-keep])
                        pending = pending[-keep:]
                    return out

                async for line in resp.aiter_lines():
                    line = (line or "").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                    else:
                        data_str = line
                    try:
                        evt = json.loads(data_str)
                    except Exception:
                        continue
                    if not isinstance(evt, dict):
                        continue
                    event = evt.get("event")
                    if event in ("message", "agent_message", "message_replace"):
                        chunk = evt.get("answer")
                        if isinstance(chunk, str) and chunk:
                            for vis in _filter_text(chunk):
                                answer_parts.append(vis)
                                fwd = dict(evt)
                                fwd["answer"] = vis
                                yield fwd
                        if not stream_result["conversation_id"]:
                            stream_result["conversation_id"] = evt.get("conversation_id")
                    elif event == "message_end":
                        mmeta = evt.get("metadata") or {}
                        if isinstance(mmeta.get("usage"), dict):
                            stream_result["usage"] = mmeta["usage"]
                        if not stream_result["conversation_id"]:
                            stream_result["conversation_id"] = evt.get("conversation_id")
                        yield evt
                    elif event == "agent_thought":
                        stream_result["thoughts_count"] += 1
                        yield evt
                    elif event == "retriever_resources":
                        for r in (evt.get("records") or []):
                            if isinstance(r, dict):
                                stream_result["rag_records"].append(r)
                        yield evt
                    else:
                        # workflow_started / workflow_finished 等其他事件原样透传
                        yield evt
            finally:
                # 正常结束、上游异常、下游取消及重试失败均释放连接。
                for closing_resp in (retry_resp, resp):
                    if closing_resp is not None:
                        try:
                            await closing_resp.aclose()
                        except Exception:
                            pass

            # 冲刷 lookahead 残余（全程未出现 FABTWIN 时 pending 里的尾巴）
            if pending and not fab_mode:
                answer_parts.append(pending)
                yield {"event": "agent_message", "answer": pending}

            stream_result["answer"] = "".join(answer_parts)
            stream_result["fab_text"] = "".join(fab_parts)
            print(f"[Dify-stream] [DONE] 流结束: answer_len={len(stream_result['answer'])}, "
                  f"fab={'有' if fab_mode else '无'}, thoughts={stream_result['thoughts_count']}")

    def _call_dify(self, question: str, session_id: str, machine_id: str = None,
                   user_role: str = "user",
                   usage_tracker: Dict = None,
                   tool_calls_recorder: List = None,
                   dify_cfg: Dict = None) -> Dict[str, Any]:
        """调用Dify应用
        - 解析 Dify 返回的 metadata.usage 写回 usage_tracker（用于日志计费）
        - 解析 retriever_resources（RAG 知识库引用片段）放入 sources 字段
        - 支持 workflow 模式、chatbot 模式、agent 智能体模式
        - 统一使用 streaming(SSE) 模式（Agent 应用不支持 blocking）
        """
        # test31：请求级配置（机台专属 Dify 传入 dify_cfg；未传时读全局单例）
        cfg = dify_cfg or {
            "enabled": self.dify_enabled,
            "base_url": self.dify_base_url,
            "api_key": self.dify_api_key,
        }
        if not cfg.get("enabled") or not cfg.get("base_url") or not cfg.get("api_key"):
            # 纯 Dify 模式：不做本地规则兜底，直接抛错以便调试真实 Dify 链路
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat", "status": "error",
                    "error": "Dify未启用或缺少配置（dify_base_url/dify_api_key 为空）",
                })
            raise RuntimeError(
                "Dify 未启用或缺少配置（dify_base_url/dify_api_key 为空），未做本地兜底。"
                "请检查全局 Dify 配置或机台专属 Dify 配置。"
            )

        try:
            base = cfg["base_url"].rstrip('/')
            # 若用户填写的是 /v4 结尾的 URL，自动保留版本前缀不重复
            url = f"{base}/chat-messages" if base.endswith('/v1') else f"{base}/v1/chat-messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
            }
            # ============ Dify payload 兼容构造 ============
            # 1) conversation_id: 只在"有效非空"时发送，空串省略（Dify 对空串 conversation_id 经常 400）
            # 2) files: 空数组通常不会错，但某些 Dify 版本校验严格 → 省略
            # 3) user: 必须非空字符串；user_role 空时回退 "fabtwin_user"
            # 4) inputs: 若用户 Dify 应用未定义 machine_id/user_role 变量，传进去也会 400，
            #    这里用 "宽松策略"：先按有 inputs 发送；若返回 400 且错误信息包含 "inputs"，
            #    再自动重试 inputs={}（下方 HTTPError 处理块做回退）
            # 5) inputs.machine_model / inputs.chambers：机台元数据（Q2 要求的"自带机台内容"）
            #    让 Dify Start 节点就看到 "当前型号=OXE / Chambers=3" 这种上下文，
            #    机台专属 Dify 可依此走专用 Prompt/工具；全局 Dify 也能更精确分类。
            meta = self._get_machine_metadata(machine_id)
            inputs = {
                "machine_id": machine_id or "",
                "user_role": user_role or "user",
            }
            if meta.get("machine_model"):
                inputs["machine_model"] = meta["machine_model"]
            if meta.get("chambers"):
                inputs["chambers"] = int(meta["chambers"])
            # ⚠️ 为什么用 streaming 而不是 blocking？
            # Dify 的【Agent 智能体应用】只支持 streaming（流式）模式，不支持 blocking（一次性返回）。
            # 若用 blocking，agent 类型 Dify 会返回 400：“Agent Chat App does not support blocking mode”。
            # streaming 同时兼容：Agent / Chatbot / Chatflow / Workflow 全部应用类型，
            # 因此这里统一走 streaming，由 _consume_dify_stream() 在本地把 SSE 分片聚合成完整 answer。
            payload = {
                "inputs": inputs,
                "query": question,
                "response_mode": "streaming",
                "user": f"fabtwin_{user_role}" if user_role else "fabtwin_user",
            }
            # ========== conversation_id 正确规则 ==========
            # Dify 对 conversation_id 要求:
            #   1. 必须是 UUID 格式（不能是前端的 sess_xxx）
            #   2. 首次请求不能传（由 Dify 返回）
            #   3. 后续请求必须传 Dify 返回的 UUID
            # 因此维护一个映射: session_id → dify_conv_id (UUID)
            sid_key = str(session_id).strip() if session_id else ""
            dify_cid = self._conv_get(sid_key) if sid_key else None
            if dify_cid:
                payload["conversation_id"] = dify_cid  # 非首次 → 传 Dify 返回的 UUID
            # 注意: 首次请求不传 conversation_id（若传了 sess_xxx 这种非 UUID 会 400）

            # 诊断日志（避免打印 API Key）
            conv_info = f"session={sid_key or '(none)'}" + (
                f" → dify_cid={dify_cid}" if dify_cid else " → 首次请求(无conversation_id)"
            )
            # 额外安全提示: 若 base_url 明显指向 n8n（端口 5678 或含 n8n 字样），打印警告
            base_host = ""
            try:
                from urllib.parse import urlparse
                base_host = urlparse(base).netloc or ""
            except Exception:
                pass
            if ":5678" in base_host or "n8n" in base.lower():
                print(f"[Dify] ⚠ 警告: dify_base_url={base!r} 看起来是 n8n 地址（不是 Dify 地址）！"
                      f"请修正为 Dify API 地址（如 http://10.30.116.68）")
            print(f"[Dify] → POST {url}, {conv_info}, payload keys={list(payload.keys())}, "
                  f"inputs keys={list(payload['inputs'].keys())}, "
                  f"query_len={len(question)}, user={payload['user']}")
            resp = requests.post(url, json=payload, headers=headers, timeout=120, stream=True)
            # ---------- 4xx 自动回退重试（兼容 Dify 不同应用类型） ----------
            if resp.status_code >= 400 and resp.status_code < 500:
                body_txt = ""
                try:
                    body_txt = resp.text
                    body_json = resp.json() if body_txt else {}
                except Exception:
                    body_json = {}
                msg = body_json.get("message") or body_json.get("error") or body_txt[:500]
                print(f"[Dify] × HTTP {resp.status_code}（首次请求，尝试兼容回退）: {msg[:300]}")
                # 若错误提示和 inputs 有关（如"unknown inputs"、"inputs do not match"），
                # 重试：发送 inputs={}（Chatbot 未配置变量的场景）
                already_bare = payload.get("inputs") == {}
                if (("inputs" in str(msg).lower() or "field" in str(msg).lower() or "param" in str(msg).lower())
                        and not already_bare):
                    payload2 = dict(payload)
                    payload2["inputs"] = {}
                    print(f"[Dify] ↻ 回退重试：清空 inputs，keys={list(payload2.keys())}")
                    resp2 = requests.post(url, json=payload2, headers=headers, timeout=120, stream=True)
                    if resp2.status_code < 400:
                        resp = resp2  # 用回退成功的响应继续处理
                        print(f"[Dify] ✓ 回退重试成功 HTTP {resp.status_code}")
                    else:
                        # 再次失败也保留"原始第一次的 resp"做错误抛出（消息更准确）
                        print(f"[Dify] × 回退重试仍失败 HTTP {resp2.status_code}: {(resp2.text or '')[:300]}")
                # 无论是否重试过，若最终仍是 4xx，把 Dify 完整响应体拼进错误信息再 raise
                if resp.status_code >= 400:
                    body_txt = ""
                    body_json = {}
                    try:
                        body_txt = resp.text
                        body_json = resp.json() if body_txt else {}
                    except Exception:
                        pass
                    dify_msg = (body_json.get("message")
                                or body_json.get("error")
                                or body_json.get("detail")
                                or "")
                    if isinstance(dify_msg, list):
                        try: dify_msg = "; ".join(str(x) for x in dify_msg)
                        except Exception: dify_msg = str(dify_msg)
                    other_fields = {k: v for k, v in body_json.items()
                                    if k not in ("message", "error", "detail") and not k.startswith("_")}
                    extra = ""
                    if other_fields:
                        import json as _json
                        extra = " | " + _json.dumps(other_fields, ensure_ascii=False)[:500]
                    raise RuntimeError(
                        f"Dify HTTP {resp.status_code}: "
                        f"{dify_msg or ('无 message 字段，原始body: '+body_txt[:400])}"
                        f"{extra}"
                    )
            resp.raise_for_status()
            # streaming 模式：把 SSE 流聚合成与 blocking 相同结构的 dict（answer/conversation_id/metadata/...）
            data = self._consume_dify_stream(resp)

            answer = data.get("answer", "")
            # 去复述：Dify Agent 模型有时会先把用户问题原样回显在回答开头（如单独一行“今天产量”）。
            # 只在"回答的第一行完全等于用户问题"时才删除该行（避免误删“今天产量：报告”这类正常回答）。
            q_norm = (question or "").strip()
            if q_norm and answer:
                a_norm = answer.strip()
                first_line = a_norm.split("\n")[0].strip() if a_norm else ""
                if first_line == q_norm:
                    rest = a_norm[len(first_line):].lstrip("\n").strip()
                    if len(rest) >= 2:
                        answer = rest
            dify_returned_cid = data.get("conversation_id")
            # 保存 session_id → dify_conv_id 映射（若 Dify 返回了 UUID，后续请求用它）
            if sid_key and dify_returned_cid:
                self._conv_put(sid_key, dify_returned_cid, machine_id=machine_id)
                print(f"[Dify] ✓ 会话映射已保存: {sid_key} → {dify_returned_cid}")
            conversation_id = dify_returned_cid or session_id

            # 解析 usage token（Dify 返回字段通常在 metadata.usage）
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            metadata = data.get("metadata") or {}
            if isinstance(metadata, dict):
                mu = metadata.get("usage") or {}
                prompt_tokens = int(mu.get("prompt_tokens") or mu.get("input_tokens") or 0)
                completion_tokens = int(mu.get("completion_tokens") or mu.get("output_tokens") or 0)
                total_tokens = int(mu.get("total_tokens") or 0)
                if total_tokens == 0:
                    total_tokens = prompt_tokens + completion_tokens

            # 兼容 dify workflow 顶层 usage 字段
            if total_tokens == 0 and isinstance(data.get("usage"), dict):
                u = data["usage"]
                prompt_tokens = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
                completion_tokens = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
                total_tokens = prompt_tokens + completion_tokens

            # 回写 token 用量给日志记录层
            if usage_tracker is not None:
                usage_tracker["prompt_tokens"] = prompt_tokens
                usage_tracker["completion_tokens"] = completion_tokens
                usage_tracker["total_tokens"] = total_tokens

            # 解析 RAG 知识库引用（retriever_resources）
            sources = [{"type": "dify", "app_id": self.dify_app_id}]
            rag_refs = data.get("retriever_resources") or []
            if not rag_refs:
                # Dify 0.10+ 可能改名为 docs
                rag_refs = data.get("docs") or []
            for i, doc in enumerate(rag_refs[:10]):
                if isinstance(doc, dict):
                    score = doc.get("score") or doc.get("rerank_score")
                    sources.append({
                        "type": "rag",
                        "doc_id": doc.get("id") or doc.get("document_id") or doc.get("segment_id") or f"rag_{i}",
                        "doc_name": doc.get("name") or doc.get("document_name") or doc.get("title") or f"文档{i+1}",
                        "content": (doc.get("content") or doc.get("text") or doc.get("segment_content") or "")[:500],
                        "page": doc.get("page") or doc.get("page_number"),
                        "score": float(score) if score is not None else None,
                    })

            # 记录 Dify 工具调用（Dify 返回的 agent_thoughts 或 workflow_steps）
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat",
                    "status": "success",
                    "conversation_id": conversation_id,
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "rag_docs_count": max(0, len(sources) - 1),
                })
                # workflow 步骤
                steps = (metadata.get("workflow_steps")
                         or metadata.get("workflow_run")
                         or data.get("workflow_steps")
                         or [])
                if isinstance(steps, list) and len(steps) > 0:
                    for s in steps:
                        if isinstance(s, dict):
                            tool_calls_recorder.append({
                                "tool": f"dify_workflow_{s.get('node_type') or s.get('type') or 'step'}",
                                "status": s.get("status") or "success",
                                "node_id": s.get("node_id"),
                                "elapsed": s.get("elapsed_time") or s.get("execution_time"),
                            })

            # ============ 提取 <FABTWIN> 结构化块（Dify+n8n 新链路的约定）============
            # 新约定：Dify 最终 answer 末尾必包 <FABTWIN>{table_data,jump_timestamp,jump_machine_id,sources}</FABTWIN>
            # 若未找到该块，再回退旧的 [JUMP]/[MACHINE] 标记（保证过渡期兼容）
            import json as _json_fab
            jump_ts = None
            jump_mid = None
            table_data = None
            extra_sources = None
            fab_found = False
            fab_match = re.search(r'<FABTWIN>\s*(\{.*?\})\s*</FABTWIN>', answer, re.DOTALL)
            if fab_match:
                fab_found = True
                try:
                    block = _json_fab.loads(fab_match.group(1))
                    if isinstance(block, dict):
                        if "table_data" in block:
                            td = block["table_data"]
                            # 合法性校验：table_data 必须是 null 或 {headers:list, rows:list}
                            if td is None:
                                table_data = None
                            elif isinstance(td, dict) and isinstance(td.get("headers"), list) and isinstance(td.get("rows"), list):
                                table_data = td
                            else:
                                if tool_calls_recorder is not None:
                                    tool_calls_recorder.append({
                                        "tool": "fabtwin_structured_parse", "status": "warn",
                                        "warn": f"table_data 格式不合法，丢弃: {str(td)[:200]}",
                                    })
                        if block.get("jump_timestamp"):
                            jump_ts = str(block["jump_timestamp"]).strip() or None
                        if block.get("jump_machine_id"):
                            jump_mid = str(block["jump_machine_id"]).strip() or None
                        extra_sources = block.get("sources")
                except Exception as parse_e:
                    if tool_calls_recorder is not None:
                        tool_calls_recorder.append({
                            "tool": "fabtwin_structured_parse", "status": "error",
                            "error": f"<FABTWIN> JSON 解析失败: {str(parse_e)[:200]}",
                            "raw": fab_match.group(1)[:300],
                        })
                # 无论解析成功与否，都从 answer 中移除 <FABTWIN> 整段（用户不应看到结构化数据）
                answer = (answer[:fab_match.start()] + answer[fab_match.end():]).strip()

            # 兼容：若没找到 FABTWIN，再尝试旧版 [JUMP]/[MACHINE] 标记（过渡期兜底）
            if not fab_found:
                jump_match = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
                if jump_match:
                    jump_ts = jump_match.group(1).strip()
                    answer = re.sub(r'\[JUMP:\s*[^\]]+\]', '', answer).strip()
                mid_match = re.search(r'\[MACHINE:\s*([^\]]+)\]', answer)
                if mid_match:
                    jump_mid = mid_match.group(1).strip()
                    answer = re.sub(r'\[MACHINE:\s*[^\]]+\]', '', answer).strip()

            # sources 合并：FABTWIN 里的工具来源 + 原本 RAG/知识库引用来源
            final_sources = list(sources)
            if isinstance(extra_sources, list) and extra_sources:
                final_sources.extend([s for s in extra_sources if isinstance(s, dict)])

            # jump_machine_id 兜底：若 block 没写、JUMP 标记也没写，就用调用时传的 machine_id
            final_jump_mid = jump_mid or machine_id

            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "fabtwin_structured_parse",
                    "status": "ok" if fab_found else "fallback_jump_mark",
                    "has_table": table_data is not None,
                    "has_jump_ts": jump_ts is not None,
                })

            return {
                "answer": answer,
                "sql": "",   # 按用户要求：网页永远不执行 SQL、永远不展示 SQL
                "jump_timestamp": jump_ts,
                "jump_machine_id": final_jump_mid,
                "table_data": table_data,
                "sources": final_sources,
                "conversation_id": conversation_id,
            }
        except requests.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"[AI] Dify调用失败 HTTP {e.response.status_code}: {body}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat", "status": "error",
                    "error": f"HTTP {e.response.status_code}: {body[:200]}",
                })
            raise
        except Exception as e:
            print(f"[AI] Dify调用失败: {e}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat", "status": "error",
                    "error": str(e)[:200],
                })
            raise

    # ==================== N8N 工作流联动 ====================

