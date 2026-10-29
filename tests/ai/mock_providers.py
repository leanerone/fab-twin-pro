# -*- coding: utf-8 -*-
"""
AI 链路测试替身服务（mock providers）
================================================================
为什么需要它：
    真正部署一套 Dify 要 8+ 个容器（postgres/redis/weaviate/sandbox/
    plugin-daemon/nginx…），几 GB 镜像 + 大量内存，且部署完仍要有 LLM
    凭据才能应答。拿它做回归测试，结果既不确定又要花钱——它是产品集成
    目标，不是测试工具。

因此这里用**协议兼容替身**替代：实现 `ai_middleware` 实际对接的三个面，
由 fixture 决定返回内容。好处是确定性、离线、免费、秒级，可直接挂 CI。

    python tests/ai/mock_providers.py --port 8901

实现的对接面（与 ai_middleware 实际请求严格对齐）：
    1. OpenAI 兼容   POST /v1/chat/completions         （非流 + SSE 流）
                    ai_middleware._build_chat_url 会自动补 /v1 前缀
    2. Dify         POST /v1/chat-messages             （streaming SSE）
                    必须返回 conversation_id(UUID) / message_id / event
    3. n8n webhook  POST /webhook/{workflow_type}      （JSON，含 secret 校验）

    4. 记录面       GET  /__records       查看被捕获的请求
                    DELETE /__records     清空
                    POST /__fault         注入故障：{"mode":"500"|"slow"|"hang", "seconds":3}
                    POST /__fault/clear   清除故障
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="FabTwin AI Mock Providers", version="1.0")

# ── 捕获到的请求（供断言）──────────────────────────────────
_RECORDS: List[Dict[str, Any]] = []
_FAULT: Dict[str, Any] = {"mode": None, "seconds": 0.0}


def _record(kind: str, payload: Dict[str, Any], meta: Dict[str, Any] = None) -> None:
    _RECORDS.append(
        {
            "ts": time.time(),
            "kind": kind,
            "payload": payload,
            "meta": meta or {},
        }
    )


async def _maybe_fault():
    """故障注入：模拟 500 / 慢响应 / 挂起"""
    mode = _FAULT.get("mode")
    secs = float(_FAULT.get("seconds") or 0.0)
    if not mode:
        return None
    if mode == "500":
        return JSONResponse(status_code=500, content={"error": {"message": "mock injected failure"}})
    if mode == "hang":
        time.sleep(secs if secs else 300)
    elif mode == "slow":
        time.sleep(secs if secs else 3.0)
    return None


# ── fixture 驱动的应答脚本 ──────────────────────────────────
# 关键字 → 应答。命中第一条包含该关键字的用户消息。
SCRIPTED = [
    {
        "match": ["产量", "今天做了多少"],
        "answer": "本机台今日产量为 1,248 片（截至当前）。",
    },
    {
        "match": ["报警", "告警", "alarm"],
        "answer": "当前存在 2 条未处理报警：PODOPENER-1 门超时、OXE-1 真空度低。",
    },
    {
        "match": ["状态", "运行"],
        "answer": "机台当前处于 RUN 状态，腔体温度 62.4℃。",
    },
]

DEFAULT_ANSWER = "（mock）已收到你的问题，这是确定性应答。"


def _pick_answer(question: str) -> str:
    q = question or ""
    for item in SCRIPTED:
        for kw in item["match"]:
            if kw in q:
                return item["answer"]
    return DEFAULT_ANSWER


def _last_user_content(body: Dict[str, Any]) -> str:
    msgs = body.get("messages") or []
    for m in reversed(msgs):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):
                c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
            return str(c or "")
    return str(body.get("prompt") or "")


def _usage(model: str) -> Dict[str, int]:
    return {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def _now() -> int:
    return int(time.time())


# ── 1) OpenAI 兼容面 ────────────────────────────────────────
def _openai_payload(model: str, content: str, delta_mode: bool = False) -> Dict[str, Any]:
    key = "delta" if delta_mode else "message"
    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk" if delta_mode else "chat.completion",
        "created": _now(),
        "model": model,
        "choices": [
            {"index": 0, key: {"role": "assistant", "content": content}, "finish_reason": None}
        ],
    }


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    body = await request.json()
    if isinstance(body, str) and body:
        try:
            body = json.loads(body)
        except Exception:
            body = {}
    body = body or {}

    model = body.get("model") or "mock-model"
    question = _last_user_content(body)
    _record(
        "openai",
        {
            "model": model,
            "stream": bool(body.get("stream")),
            "tools": body.get("tools"),
            "messages": body.get("messages"),
        },
        {"auth": request.headers.get("authorization", ""),
         "question": question,
         "url": str(request.url)},
    )

    faulted = await _maybe_fault()
    if faulted is not None:
        return faulted

    answer = _pick_answer(question)

    # 非流式
    if not body.get("stream"):
        return {
            "id": f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": _now(),
            "model": model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": answer},
                 "finish_reason": "stop"}
            ],
            "usage": _usage(model),
        }

    # 流式 SSE
    def gen():
        chunks = [answer[i:i + 6] for i in range(0, len(answer), 6)] or [""]
        for piece in chunks:
            obj = _openai_payload(model, piece, delta_mode=True)
            yield f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
        stop = {
            "id": f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": _now(),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": _usage(model),
        }
        yield f"data: {json.dumps(stop, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/models")
@app.get("/v1/models")
async def openai_models():
    return {"object": "list", "data": [{"id": "mock-model", "object": "model", "owned_by": "fabtwin-test"}]}


# ── 2) Dify 面 ──────────────────────────────────────────────
# ai_middleware._call_dify 固定用 response_mode=streaming，
# 由 _consume_dify_stream 在本地聚合 SSE。
@app.post("/chat-messages")
@app.post("/v1/chat-messages")
async def dify_chat_messages(request: Request):
    body = await request.json() or {}
    _record(
        "dify",
        body,
        {"auth": request.headers.get("authorization", ""), "url": str(request.url)},
    )

    faulted = await _maybe_fault()
    if faulted is not None:
        return faulted

    cid = body.get("conversation_id") or str(uuid.uuid4())
    answer = _pick_answer(body.get("query") or "")

    def gen():
        # Dify streaming 事件序列
        workflow_started = {
            "event": "workflow_started",
            "task_id": uuid.uuid4().hex,
            "data": {"id": uuid.uuid4().hex, "workflow_id": uuid.uuid4().hex, "sequence_number": 1},
        }
        yield f"data: {json.dumps(workflow_started, ensure_ascii=False)}\n\n"

        pieces = [answer[i:i + 6] for i in range(0, len(answer), 6)] or [""]
        for piece in pieces:
            ev = {
                "event": "message",
                "conversation_id": cid,
                "message_id": str(uuid.uuid4()),
                "answer": piece,
            }
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        end = {
            "event": "message_end",
            "conversation_id": cid,
            "message_id": str(uuid.uuid4()),
            "metadata": {"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}},
        }
        yield f"data: {json.dumps(end, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/parameters")
@app.get("/v1/parameters")
async def dify_parameters():
    return {"user_input_form": [], "opening_statement": "（mock）你好"}


# ── 3) n8n webhook 面 ──────────────────────────────────────
@app.post("/webhook/{wf_type}")
async def n8n_webhook(wf_type: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body or {}
    secret = request.query_params.get("secret")
    if secret == "WRONG_SECRET":
        _record("n8n", body, {"workflow_type": wf_type, "rejected": True})
        return JSONResponse(status_code=401, content={"message": "invalid secret"})

    _record("n8n", body, {"workflow_type": wf_type, "secret": secret})

    faulted = await _maybe_fault()
    if faulted is not None:
        return faulted

    answer_map = {
        "export_alarm_report": "报警报表已生成：alarm_report_20261030.xlsx",
        "generate_work_order": "故障工单已创建：WO-20261030-001",
        "export_machine_data": "设备数据导出完成，共 3,481 条记录。",
        "push_daily_report": "产线日报已推送至 3 个订阅人。",
    }
    return {
        "answer": answer_map.get(wf_type, "工作流已触发，请稍候查看结果。"),
        "workflow_type": wf_type,
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }


@app.get("/healthz")
async def n8n_healthz():
    return {"status": "ok"}


# ── 4) 控制面 ───────────────────────────────────────────────
@app.get("/__records")
async def list_records(kind: str = None):
    rows = _RECORDS if not kind else [r for r in _RECORDS if r["kind"] == kind]
    return {"count": len(rows), "records": rows}


@app.delete("/__records")
async def clear_records():
    _RECORDS.clear()
    return {"cleared": True}


@app.post("/__fault")
async def inject_fault(request: Request):
    body = await request.json() or {}
    _FAULT["mode"] = body.get("mode")
    _FAULT["seconds"] = float(body.get("seconds") or 0.0)
    return {"fault": dict(_FAULT)}


@app.post("/__fault/clear")
async def clear_fault():
    _FAULT["mode"] = None
    _FAULT["seconds"] = 0.0
    return {"fault": dict(_FAULT)}


@app.get("/__health")
async def health():
    return {"status": "ok", "records": len(_RECORDS), "fault": _FAULT.get("mode")}


def main():
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8901)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
