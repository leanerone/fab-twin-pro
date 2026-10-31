import asyncio
import inspect
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.dialects import oracle
from sqlalchemy.orm import Query, Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ORACLE_SERVICE", "XEPDB1")

import services.ai_middleware as ai_middleware_module
from services.ai_middleware import AIMiddleware


def _chat_middleware(provider):
    middleware = AIMiddleware.__new__(AIMiddleware)
    middleware.provider = provider
    middleware.provider_name = "test-provider"
    middleware.base_url = "https://llm.example.com"
    middleware.api_key = "test-key"
    middleware.model = "test-model"
    middleware.current_config_id = 1
    middleware.sessions = {}
    middleware._build_system_prompt = Mock(return_value="system")
    middleware._log_usage = Mock()
    middleware._trigger_n8n_workflow = Mock(return_value={"answer": "n8n done"})
    middleware._call_openai_compatible = Mock(return_value={"answer": "llm done"})
    middleware._local_rule_engine = Mock(return_value={"answer": "local done"})
    return middleware


@pytest.mark.parametrize("provider", ["custom", "openai", "local"])
def test_admin_n8n_command_preempts_provider_exactly_once(provider):
    middleware = _chat_middleware(provider)

    result = middleware.chat("导出报警报表", session_id="n8n-test", user_role="admin")

    assert result["answer"] == "n8n done"
    assert middleware._trigger_n8n_workflow.call_count == 1
    middleware._call_openai_compatible.assert_not_called()
    middleware._local_rule_engine.assert_not_called()


def test_non_admin_n8n_keywords_keep_openai_route():
    middleware = _chat_middleware("custom")

    result = middleware.chat("导出报警报表", session_id="llm-test", user_role="user")

    assert result["answer"] == "llm done"
    middleware._trigger_n8n_workflow.assert_not_called()
    assert middleware._call_openai_compatible.call_count == 1


def _dify_middleware():
    middleware = AIMiddleware.__new__(AIMiddleware)
    middleware.dify_enabled = True
    middleware.dify_base_url = "https://dify.example.com/v1"
    middleware.dify_api_key = "dify-key"
    middleware._get_machine_metadata = Mock(return_value={})
    middleware._conv_get = Mock(return_value=None)
    return middleware


class TrackingStream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error

    async def aclose(self):
        self.closed = True


def _install_mock_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ai_middleware_module.httpx, "AsyncClient", client_factory)


def _collect_dify(middleware, stream_result):
    async def collect():
        return [
            event
            async for event in middleware._stream_dify(
                "hello", "session-1", stream_result=stream_result
            )
        ]

    return asyncio.run(collect())


def test_dify_stream_is_async_and_closes_response(monkeypatch):
    assert inspect.isasyncgenfunction(AIMiddleware.chat_stream)
    assert inspect.isasyncgenfunction(AIMiddleware._stream_dify)
    stream = TrackingStream([
        b'data: {"event":"agent_message","answer":"hello world","conversation_id":"cid-1"}\n\n',
        b'data: {"event":"message_end","conversation_id":"cid-1","metadata":{"usage":{"total_tokens":3}}}\n\n',
        b'data: [DONE]\n\n',
    ])
    _install_mock_transport(
        monkeypatch, lambda request: httpx.Response(200, stream=stream)
    )
    stream_result = {}

    events = _collect_dify(_dify_middleware(), stream_result)

    assert "".join(event.get("answer", "") for event in events) == "hello world"
    assert stream_result["answer"] == "hello world"
    assert stream_result["conversation_id"] == "cid-1"
    assert stream_result["usage"]["total_tokens"] == 3
    assert stream.closed


def test_dify_stream_propagates_error_and_closes_response(monkeypatch):
    stream = TrackingStream(
        [b'data: {"event":"agent_message","answer":"hello world"}\n\n'],
        error=httpx.ReadError("stream failed"),
    )
    _install_mock_transport(
        monkeypatch, lambda request: httpx.Response(200, stream=stream)
    )

    with pytest.raises(httpx.ReadError, match="stream failed"):
        _collect_dify(_dify_middleware(), {})

    assert stream.closed


def test_dify_inputs_retry_closes_both_responses(monkeypatch):
    first_stream = TrackingStream([b'{"message":"unknown inputs"}'])
    second_stream = TrackingStream([
        b'data: {"event":"agent_message","answer":"hello world"}\n\n',
        b'data: [DONE]\n\n',
    ])
    requests_seen = []

    def handler(request):
        requests_seen.append(json.loads(request.content))
        if len(requests_seen) == 1:
            return httpx.Response(400, stream=first_stream)
        assert first_stream.closed
        return httpx.Response(200, stream=second_stream)

    _install_mock_transport(monkeypatch, handler)
    stream_result = {}

    events = _collect_dify(_dify_middleware(), stream_result)

    assert len(requests_seen) == 2
    assert requests_seen[0]["inputs"] != {}
    assert requests_seen[1]["inputs"] == {}
    assert "".join(event.get("answer", "") for event in events) == "hello world"
    assert first_stream.closed
    assert second_stream.closed


class QueryDouble:
    def __init__(self, entities, captured, totals, result_sets):
        self.query = Query(entities, session=Session())
        self.captured = captured
        self.totals = totals
        self.result_sets = result_sets

    def filter(self, *args, **kwargs):
        self.query = self.query.filter(*args, **kwargs)
        return self

    def group_by(self, *args, **kwargs):
        self.query = self.query.group_by(*args, **kwargs)
        return self

    def order_by(self, *args, **kwargs):
        self.query = self.query.order_by(*args, **kwargs)
        return self

    def first(self):
        self.captured.append(self.query)
        return self.totals

    def all(self):
        self.captured.append(self.query)
        return self.result_sets[len(self.captured) - 2]


def test_usage_stats_compile_oracle_substr_and_iso_string_bounds(monkeypatch):
    totals = SimpleNamespace(
        total_calls=1, total_prompt=2, total_completion=3, total_tokens=5
    )
    result_sets = [
        [],
        [SimpleNamespace(day="2026-10-30", calls=1, tokens=5)],
    ]
    captured = []

    class FakeDB:
        def query(self, *entities):
            return QueryDouble(entities, captured, totals, result_sets)

        def close(self):
            pass

    # 批次2拆包后 get_usage_stats 在 services.ai.usage，_get_db 需补丁到实现的命名空间
    from services.ai import usage as ai_usage_module
    monkeypatch.setattr(ai_usage_module, "_get_db", lambda: FakeDB())
    middleware = AIMiddleware.__new__(AIMiddleware)

    stats = middleware.get_usage_stats(days=7)

    assert len(captured) == 3
    compiled = [
        query.statement.compile(dialect=oracle.dialect()) for query in captured
    ]
    all_sql = "\n".join(str(statement) for statement in compiled).upper()
    assert "TRUNC" not in all_sql
    assert "SUBSTR" in str(compiled[2]).upper()
    for statement in compiled:
        date_bounds = [
            value
            for name, value in statement.params.items()
            if name.startswith("created_at")
        ]
        assert len(date_bounds) == 1
        assert isinstance(date_bounds[0], str)
        datetime.strptime(date_bounds[0], "%Y-%m-%d")
    assert stats["daily_stats"] == [
        {"date": "2026-10-30", "calls": 1, "tokens": 5}
    ]
