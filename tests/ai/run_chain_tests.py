# -*- coding: utf-8 -*-
"""
AI 链路端到端自动化测试
================================================================
用 tests/ai/mock_providers.py 作替身，对真实后端跑完整 AI 链路断言。
不需要 Dify 容器、不需要 LLM Key、不花钱、结果确定，可直接挂 CI。

运行（前提：mock 服务已在 8901 跑起来，见 run_chain_tests.py --help）：

    python tests/ai/run_chain_tests.py --backend http://127.0.0.1:8003 \
                                       --mock http://127.0.0.1:8901

若只跑 `python tests/ai/run_chain_tests.py`，脚本会自行拉起 mock 与后端（未实现，
当前版本要求外部已启动，便于复用正在运行的服务）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# ── 极简 HTTP 客户端（不引三方依赖，CI 上零安装）──────────────
DEFAULT_TIMEOUT = 60


def http(method: str, url: str, body: dict = None, token: str = None,
         timeout: float = DEFAULT_TIMEOUT, raw: bool = False):
    import gzip
    import io

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                payload = gzip.GzipFile(fileobj=io.BytesIO(payload)).read()
            ms = (time.perf_counter() - t0) * 1000
            if raw:
                return r.status, payload.decode("utf-8", "replace"), ms
            try:
                return r.status, json.loads(payload.decode("utf-8")), ms
            except Exception:
                return r.status, payload.decode("utf-8", "replace"), ms
    except urllib.error.HTTPError as e:
        payload = e.read()
        ms = (time.perf_counter() - t0) * 1000
        try:
            payload = json.loads(payload.decode("utf-8"))
        except Exception:
            payload = payload.decode("utf-8", "replace")
        return e.code, payload, ms
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return 0, f"ERR {type(e).__name__}: {e}", ms


class Results:
    def __init__(self):
        self.rows = []

    def add(self, name: str, ok: bool, detail: str = ""):
        self.rows.append((name, ok, detail))
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name}" + (f"  —— {detail}" if detail else ""))

    @property
    def failed(self):
        return [r for r in self.rows if not r[1]]

    def summary(self):
        total = len(self.rows)
        bad = len(self.failed)
        print("")
        print("=" * 62)
        print(f"  AI 链路端到端测试：{total - bad}/{total} 通过")
        if bad:
            print("  失败项：")
            for name, _, detail in self.failed:
                print(f"    - {name}: {detail}")
        print("=" * 62)
        return 1 if bad else 0


def clear_mock(mock: str):
    try:
        http("DELETE", f"{mock}/__records")
        http("POST", f"{mock}/__fault/clear", {})
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:8003")
    ap.add_argument("--mock", default="http://127.0.0.1:8901")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    a = ap.parse_args()

    BACKEND, MOCK = a.backend.rstrip("/"), a.mock.rstrip("/")
    R = Results()

    print(f"后端 {BACKEND} / 替身 {MOCK}")
    print("")

    # ── 0. 服务存活 ────────────────────────────────────────
    st, body, ms = http("GET", f"{BACKEND}/health")
    R.add("后端 /health", st == 200, f"HTTP {st} {ms:.0f}ms")
    st, mock_body, ms = http("GET", f"{MOCK}/__health")
    R.add("替身服务存活", st == 200, f"HTTP {st}")

    # ── 1. 鉴权前置 ────────────────────────────────────────
    st, body, ms = http("POST", f"{BACKEND}/api/auth/login-password",
                        {"username": a.user, "password": a.password})
    token = body.get("token") if isinstance(body, dict) else None
    R.add("登录获取 token", bool(token), f"HTTP {st}")
    if not token:
        print("  无法继续：登录失败", body if not isinstance(body, dict) else "")
        return 2

    st, body, ms = http("GET", f"{BACKEND}/api/ai/config")
    R.add("AI 配置需鉴权（无 token 应 401/403）", st in (401, 403), f"HTTP {st}")

    # ── 2. 把 AI 指向替身 ──────────────────────────────────
    cfg = {
        "provider": "custom",
        "base_url": f"{MOCK}/v1",
        "api_key": "mock-key",
        "model": "mock-model",
        "temperature": 0.2,
        "max_tokens": 512,
    }
    st, body, ms = http("PUT", f"{BACKEND}/api/ai/config", cfg, token=token)
    R.add("写入 AI 配置（指向替身）", st == 200, f"HTTP {st}")

    st, body, ms = http("GET", f"{BACKEND}/api/ai/config", token=token)
    ok_model = isinstance(body, dict) and body.get("model") == "mock-model"
    key_masked = isinstance(body, dict) and str(body.get("api_key", "")).count("*") > 0
    R.add("配置读回且 API Key 已脱敏", ok_model and key_masked,
          f"model={body.get('model') if isinstance(body, dict) else body}, key={body.get('api_key') if isinstance(body, dict) else '?'}")

    # ── 3. 非流式对话真的调用了替身 LLM ────────────────────
    clear_mock(MOCK)
    st, body, ms = http("POST", f"{BACKEND}/api/ai/chat",
                        {"question": "今天产量多少", "session_id": "sess_chain_test"},
                        token=token)
    ans = (body.get("answer") or body.get("content") or "") if isinstance(body, dict) else str(body)
    R.add("POST /api/ai/chat 返回 200", st == 200, f"HTTP {st} {ms:.0f}ms")
    R.add("答案来自替身 LLM（确定性 fixture）", "1,248" in ans, f"answer={ans[:60]!r}")

    st, rec, ms = http("GET", f"{MOCK}/__records?kind=openai")
    called = rec.get("count", 0) if isinstance(rec, dict) else 0
    R.add("替身确实收到了 chat/completions 请求", called >= 1, f"records={called}")

    # ── 4. 流式通道 ────────────────────────────────────────
    st, text, ms = http("POST", f"{BACKEND}/api/ai/chat/stream",
                        {"question": "当前有什么报警", "session_id": "sess_chain_stream"},
                        token=token, raw=True, timeout=90)
    has_sse = "data:" in text
    has_content = "PODOPENER-1" in text or "报警" in text or "2 条" in text
    R.add("/api/ai/chat/stream 返回 SSE", st == 200 and has_sse, f"HTTP {st} {ms:.0f}ms")
    R.add("SSE 内容含 fixture 答案片段", has_content, f"len={len(text)}")

    # ── 5. n8n 工作流触发 ──────────────────────────────────
    clear_mock(MOCK)
    st, body, ms = http("PUT", f"{BACKEND}/api/ai/config", {
        "n8n_enabled": True,
        "n8n_base_url": MOCK,
        "n8n_webhook_secret": "chain-secret",
    }, token=token)
    R.add("开启并指向 n8n 替身", st == 200, f"HTTP {st}")

    st, body, ms = http("POST", f"{BACKEND}/api/ai/chat",
                        {"question": "帮我导出报警报表", "session_id": "sess_chain_n8n"},
                        token=token)
    ans = (body.get("answer") or "") if isinstance(body, dict) else str(body)
    hit = "alarm_report_20261030" in ans or "生成" in ans or "完成" in ans
    st2, rec2, _ = http("GET", f"{MOCK}/__records?kind=n8n")
    n8n_calls = rec2.get("count", 0) if isinstance(rec2, dict) else 0
    wf_type = ""
    if isinstance(rec2, dict) and rec2.get("records"):
        wf_type = rec2["records"][0].get("meta", {}).get("workflow_type", "")
    R.add("n8n webhook 被真实触发", n8n_calls >= 1, f"calls={n8n_calls} workflow={wf_type}")
    R.add("n8n 工作流类型识别正确（export_alarm_report）", wf_type == "export_alarm_report", f"实际={wf_type}")

    # ── 6. Dify 路由 ───────────────────────────────────────
    clear_mock(MOCK)
    st, body, ms = http("PUT", f"{BACKEND}/api/ai/config", {
        "provider": "dify",
        "dify_enabled": True,
        "dify_base_url": MOCK,
        "dify_api_key": "mock-dify-key",
    }, token=token)
    R.add("切换 provider=dify 并指向替身", st == 200, f"HTTP {st}")

    st, body, ms = http("POST", f"{BACKEND}/api/ai/chat",
                        {"question": "机台现在运行状态如何", "session_id": "sess_chain_dify"},
                        token=token)
    ans = (body.get("answer") or "") if isinstance(body, dict) else str(body)
    st2, rec3, _ = http("GET", f"{MOCK}/__records?kind=dify")
    dify_calls = rec3.get("count", 0) if isinstance(rec3, dict) else 0
    R.add("Dify /v1/chat-messages 被真实调用", dify_calls >= 1, f"calls={dify_calls}")
    R.add("Dify 流式被聚合成完整答案", "RUN" in ans or "腔体" in ans, f"answer={ans[:60]!r}")

    conversation_continues = True
    st, body, ms = http("POST", f"{BACKEND}/api/ai/chat",
                        {"question": "再看一下产量", "session_id": "sess_chain_dify"},
                        token=token)
    st2, rec4, _ = http("GET", f"{MOCK}/__records?kind=dify")
    recs = rec4.get("records", []) if isinstance(rec4, dict) else []
    second_has_cid = len(recs) >= 2 and bool(recs[1].get("payload", {}).get("conversation_id"))
    R.add("多轮对话带上 Dify conversation_id（UUID）", second_has_cid,
          f"第二次 payload conversation_id={recs[1]['payload'].get('conversation_id') if len(recs) >= 2 else 'N/A'}")

    # ── 7. 故障降级 ────────────────────────────────────────
    # 回到 OpenAI 兼容面，注入 500，后端必须优雅降级而不是崩/挂死
    http("PUT", f"{BACKEND}/api/ai/config", {
        "provider": "custom", "base_url": f"{MOCK}/v1",
        "api_key": "mock-key", "model": "mock-model",
    }, token=token)
    http("POST", f"{MOCK}/__fault", {"mode": "500"})
    st, body, ms = http("POST", f"{BACKEND}/api/ai/chat",
                        {"question": "产量", "session_id": "sess_chain_fault"},
                        token=token, timeout=120)
    R.add("上游 500 时后端优雅降级（不 500、不挂死）", st == 200 and ms < 120000,
          f"HTTP {st} {ms:.0f}ms")
    http("POST", f"{MOCK}/__fault/clear", {})

    # ── 8. 会话隔离 ────────────────────────────────────────
    st, body, ms = http("GET", f"{BACKEND}/api/ai/sessions", token=token)
    ok_sessions = st == 200 and isinstance(body, dict)
    R.add("GET /api/ai/sessions 鉴权后可访问", ok_sessions, f"HTTP {st}")

    return R.summary()


if __name__ == "__main__":
    sys.exit(main())
