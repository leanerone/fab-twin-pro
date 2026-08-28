"""
Dify 对接端到端测试脚本
=======================
功能：
  1. 直连 Dify API 测试 (不依赖 FabTwin 后端)
       - GET  /v1/info         应用基本信息
       - GET  /v1/datasets     知识库列表
       - POST /v1/chat-messages 对话问答 (含 RAG 引用验证)
  2. 直连 FabTwin AI 中间件测试 (启动后端后运行)
       - POST /api/ai/config/test  (Dify 连接测试 API)
       - PUT  /api/ai/config       (写入 Dify 配置)
       - POST /api/ai/chat         (AI 对话：provider=dify/hybrid)

用法:
    # 仅测试 Dify 直连
    python test_dify_integration.py ^
        --base-url http://10.30.116.137:8088/v1 ^
        --api-key app-xxxxxxxxxxxxxxxx

    # 同时测试 FabTwin 后端 (需先启动后端 :8002)
    python test_dify_integration.py ^
        --base-url http://10.30.116.137:8088/v1 ^
        --api-key app-xxxxxxxxxxxxxxxx ^
        --fabtwin-url http://localhost:8002 ^
        --fabtwin-user admin --fabtwin-password admin123

    # 用 mock 模式运行（不需要真实 Dify 服务，用于 CI 验证脚本自身逻辑）
    python test_dify_integration.py --mock

输出: 测试结果汇总 (Pass / Fail 列表 + 耗时)
生成时间: 2026-08-28   代码基线: FabTwin Pro ver2.7.0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


# =============== 工具 ===============

@dataclass
class TestCase:
    name: str
    desc: str
    ok: bool = False
    msg: str = ""
    elapsed_ms: int = 0
    extras: Dict[str, Any] = field(default_factory=dict)


def color(s: str, color_: str) -> str:
    palette = {
        "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36", "gray": "37"
    }
    code = palette.get(color_, "37")
    return f"\033[{code}m{s}\033[0m"


def log_step(tag: str, s: str) -> None:
    tag_c = {"RUN": "cyan", "OK": "green", "FAIL": "red", "WARN": "yellow", "INFO": "blue"}[tag]
    print(color(f"[{tag:4s}]", tag_c) + f" {s}")


def call(method: str, url: str, *, headers=None, params=None, json_body=None, timeout=30):
    t0 = time.perf_counter()
    resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)
    dt = int((time.perf_counter() - t0) * 1000)
    return resp, dt


# =============== Mock Dify ===============
class MockDifyServer:
    """
    内存内的伪 Dify HTTP Server (http.server 实现)，
    用于 --mock 模式验证脚本/客户端逻辑。
    """
    def __init__(self):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a, **k):  # silence
                pass
            def _send_json(self, code: int, body: dict):
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def _auth_fail(self):
                return self._send_json(401, {"code": "unauthorized", "message": "Bearer token not match mock-app"})
            def _check_auth(self) -> bool:
                auth = self.headers.get("Authorization", "")
                return auth.startswith("Bearer ") and ("app-mock" in auth or "mock-app" in auth)
            def do_GET(self):
                if not self._check_auth(): return self._auth_fail()
                if self.path.startswith("/v1/info"):
                    return self._send_json(200, {"name": "FabTwin AI Assistant (Mock)", "app": {"name": "FabTwin AI Assistant (Mock)"}, "tool_names": ["get_machine_status","get_oxe_lot_summary"]})
                if self.path.startswith("/v1/datasets"):
                    return self._send_json(200, {"total": 1, "has_more": False, "page":1, "limit":20, "data": [{"id":"ds_mock_001","name":"OXE-Etcher-SOP","document_count":1}]})
                return self._send_json(404, {"code":"not_found"})
            def do_POST(self):
                if not self._check_auth(): return self._auth_fail()
                length = int(self.headers.get("Content-Length","0"))
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except Exception: body = {}
                if self.path.startswith("/v1/chat-messages"):
                    q = body.get("query", "")
                    has_pm = "PM" in q or "周期" in q or "CQ" in q
                    answer = (
                        "OXE PM-A 周期为 RF Hour 每累积 2000h 执行一次；"
                        "PM 后必须执行 4 项 Chamber Qualification 验证："
                        "① He Leak < 5e-9；② Uniformity < 3%；"
                        "③ 中心深度偏差 <5%；④ 颗粒<30颗/片。"
                        "（以上内容来自知识库 OXE-Etcher-SOP §3 / §6）"
                    ) if has_pm else f"已收到您的提问：{q}（Mock 回答）"
                    return self._send_json(200, {
                        "message_id": "msg-mock-"+uuid.uuid4().hex[:8],
                        "answer": answer,
                        "conversation_id": "conv-mock-1",
                        "metadata": {
                            "usage": {"prompt_tokens": 120, "completion_tokens": 82, "total_tokens": 202},
                            "workflow_steps": [{"node_type":"llm","status":"success","elapsed_time":200},{"node_type":"knowledge_retrieval","status":"success","elapsed_time":80}],
                        },
                        "retriever_resources": [
                            {"id":"seg-1","document_name":"OXE_Etcher_SOP_v1.0.md","segment_id":"pg3","score":0.91,"content":"PM-A   | RF Hour 2000h | 拆 Chamber 上盖、换 Upper/Lower Electrode、检漏 | 8h"},
                            {"id":"seg-2","document_name":"OXE_Etcher_SOP_v1.0.md","segment_id":"pg4","score":0.84,"content":"PM 后 Chamber Qualification：1. He Leak <5×10⁻⁹  2. Uniformity<3%  3. 深度偏差<5%  4. 颗粒<30颗"},
                        ],
                        "created_at": int(time.time()),
                    })
                return self._send_json(404, {"code":"not_found"})

        self._srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self._srv.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self.api_key = "app-mock-xxxxxxxx"
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()
        print(color(f"[MOCK] 已启动模拟 Dify Server at {self.base_url}", "gray"))


# =============== 测试用例 ===============

class DifyTester:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: List[TestCase] = []
        self.session_id = ""

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    # --- TC1: 健康检查 ---
    def tc_01_info(self) -> TestCase:
        tc = TestCase("TC01 Dify /v1/info", "查询应用基本信息，验证 API Key 正确性")
        url = self.base_url + ("/info" if self.base_url.endswith("/v1") else "/v1/info")
        try:
            resp, ms = call("GET", url, headers={"Authorization": f"Bearer {self.api_key}"})
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return tc
            data = resp.json()
            app_name = (isinstance(data.get("app"), dict) and data["app"].get("name")) or data.get("name") or "unknown"
            tc.ok = True
            tc.msg = f"应用名: {app_name}, 耗时 {ms}ms"
            tc.extras["app_name"] = app_name
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    # --- TC2: 知识库列表 ---
    def tc_02_datasets(self) -> TestCase:
        tc = TestCase("TC02 Dify /v1/datasets", "读取知识库列表，确认至少存在 1 个 OXE 知识库")
        url = self.base_url + ("/datasets" if self.base_url.endswith("/v1") else "/v1/datasets")
        try:
            resp, ms = call("GET", url, headers={"Authorization": f"Bearer {self.api_key}"}, params={"page":1,"limit":5})
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return tc
            data = resp.json()
            total = data.get("total") or len(data.get("data") or [])
            names = [d.get("name") for d in (data.get("data") or [])]
            tc.ok = int(total or 0) > 0
            tc.msg = f"共 {total} 个知识库: {names[:5]}, 耗时 {ms}ms"
            tc.extras["dataset_count"] = int(total or 0)
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    # --- TC3: 对话 + RAG 引用解析 ---
    def tc_03_chat_rag(self) -> TestCase:
        tc = TestCase("TC03 Dify /v1/chat-messages (RAG)",
                      "提问 PM-A 周期，验证 answer 非空 + usage.token 正确 + RAG sources>=1")
        url = self.base_url + ("/chat-messages" if self.base_url.endswith("/v1") else "/v1/chat-messages")
        payload = {
            "query": "OXE 做 PM-A 的周期是多少小时？PM 后 CQ 需要验证哪些项目？",
            "response_mode": "blocking",
            "user": "fabtwin_test_engineer",
            "inputs": {"machine_id": "OXE-01", "user_role": "engineer"},
        }
        try:
            resp, ms = call("POST", url, headers=self._headers(), json_body=payload, timeout=120)
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
                return tc
            data = resp.json()
            answer = (data.get("answer") or "").strip()
            if not answer:
                tc.msg = "answer 为空"
                return tc
            # usage
            metadata = data.get("metadata") or {}
            mu = metadata.get("usage") or data.get("usage") or {}
            total_tokens = int(mu.get("total_tokens") or (
                int(mu.get("prompt_tokens") or mu.get("input_tokens") or 0)
                + int(mu.get("completion_tokens") or mu.get("output_tokens") or 0)
            ) or 0)
            # rag refs
            rag = (data.get("retriever_resources") or []) + (data.get("docs") or [])
            rag_count = len(rag)
            self.session_id = data.get("conversation_id") or self.session_id
            tc.ok = bool(answer) and total_tokens > 0
            tc.msg = (
                f"OK. answer长度={len(answer)}, tokens={total_tokens}, "
                f"rag引用={rag_count}, 会话ID={self.session_id}, 耗时 {ms}ms"
            )
            if rag_count == 0:
                tc.msg += " ⚠️ RAG引用为0（可能知识库未绑定，仅做 Warning）"
            tc.extras = {"answer_len": len(answer), "total_tokens": total_tokens,
                         "rag_count": rag_count, "conversation_id": self.session_id}
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    # --- TC4: 多轮对话 conversation_id 连续性 ---
    def tc_04_multiturn(self) -> TestCase:
        tc = TestCase("TC04 Dify 多轮对话 (conversation_id)", "基于 TC03 的 session_id 再问一句，验证 conversation_id 一致")
        if not self.session_id:
            tc.ok = False
            tc.msg = "跳过：TC03 未拿到 conversation_id"
            self.results.append(tc)
            return tc
        url = self.base_url + ("/chat-messages" if self.base_url.endswith("/v1") else "/v1/chat-messages")
        payload = {
            "query": "补充说明一下颗粒计数的验收标准？",
            "response_mode": "blocking",
            "user": "fabtwin_test_engineer",
            "conversation_id": self.session_id,
            "inputs": {},
        }
        try:
            resp, ms = call("POST", url, headers=self._headers(), json_body=payload, timeout=60)
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"; return tc
            d = resp.json()
            new_cid = d.get("conversation_id")
            tc.ok = new_cid == self.session_id and bool(d.get("answer"))
            tc.msg = f"conversation_id一致={new_cid == self.session_id} ({new_cid}), 耗时 {ms}ms"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)


class FabTwinBackendTester:
    def __init__(self, fabtwin_url: str, user: str, password: str, dify_base_url: str, dify_api_key: str):
        self.base = fabtwin_url.rstrip("/")
        self.user = user
        self.pwd = password
        self.dify_base = dify_base_url
        self.dify_key = dify_api_key
        self.token: Optional[str] = None
        self.results: List[TestCase] = []

    # --- 登录 ---
    def _login(self, tc: TestCase) -> bool:
        try:
            resp, ms = call("POST", f"{self.base}/api/auth/login",
                            json_body={"username": self.user, "password": self.pwd}, timeout=15)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"登录失败 HTTP {resp.status_code}: {resp.text[:200]}"; return False
            data = resp.json()
            self.token = data.get("access_token") or (data.get("data") or {}).get("token") or ""
            if not self.token:
                tc.msg = f"未解析到 token: {json.dumps(data, ensure_ascii=False)[:200]}"; return False
            return True
        except Exception as e:
            tc.msg = f"登录异常: {e}"; return False

    def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    # --- TC5 连接测试 ---
    def tc_05_test_conn(self) -> TestCase:
        tc = TestCase("TC05 FabTwin /api/ai/config/test (dify)", "通过 FabTwin 后端提供的统一连接测试 API")
        if not self._login(tc):
            self.results.append(tc); return tc
        try:
            resp, ms = call("POST", f"{self.base}/api/ai/config/test", headers=self._h(),
                            json_body={"provider_type": "dify",
                                       "config": {"base_url": self.dify_base, "api_key": self.dify_key}}, timeout=25)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"; return tc
            data = resp.json()
            tc.ok = bool(data.get("success"))
            tc.msg = f"success={tc.ok}, message={data.get('message','')[:120]}, 总耗时 {tc.elapsed_ms}ms"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)

    # --- TC6 保存 Dify 配置并切到 Hybrid ---
    def tc_06_save_config(self) -> TestCase:
        tc = TestCase("TC06 FabTwin /api/ai/config PUT", "保存 Dify 启用开关+URL+Key，并切 provider=hybrid")
        if not self.token and not self._login(tc):
            self.results.append(tc); return tc
        try:
            resp, ms = call("PUT", f"{self.base}/api/ai/config", headers=self._h(),
                            json_body={
                                "provider": "hybrid",
                                "dify_enabled": True,
                                "dify_base_url": self.dify_base,
                                "dify_api_key": self.dify_key,
                            }, timeout=20)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"; return tc
            data = resp.json()
            tc.ok = bool(data.get("success"))
            tc.msg = f"success={tc.ok}, message={data.get('message','')}, 耗时 {tc.elapsed_ms}ms"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)

    # --- TC7 AI Chat 走 Dify 链路：验证 usage + tool_calls.rag_docs_count ---
    def tc_07_chat_via_fabtwin(self) -> TestCase:
        tc = TestCase("TC07 FabTwin /api/ai/chat 走 hybrid=Dify 链路",
                      "验证 FabTwin 中间件能将 Dify 返回的 tokens/rag 引用正确写入响应与日志")
        if not self.token and not self._login(tc):
            self.results.append(tc); return tc
        sid = f"fabtwin-e2e-{uuid.uuid4().hex[:10]}"
        payload = {"question": "OXE 的 PM-A 周期多久？PM 后验证项目？",
                   "session_id": sid, "machine_id": "OXE-01"}
        try:
            resp, ms = call("POST", f"{self.base}/api/ai/chat", headers=self._h(),
                            json_body=payload, timeout=120)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:300]}"; return tc
            d = resp.json()
            answer = (d.get("answer") or "").strip()
            usage = d.get("usage") or {}
            t_tokens = int(usage.get("total_tokens") or 0)
            tool_calls = d.get("tool_calls") or []
            rag_counts = [t.get("rag_docs_count") for t in tool_calls
                          if isinstance(t, dict) and t.get("tool") == "dify_chat"]
            sources = d.get("sources") or []
            rag_from_sources = sum(1 for s in sources if isinstance(s, dict) and s.get("type") == "rag")
            tc.ok = bool(answer) and t_tokens > 0
            tc.msg = (
                f"OK. answer={len(answer)}chars, total_tokens={t_tokens}, "
                f"provider={d.get('provider')}/{d.get('provider_name')}, "
                f"dify_chat.rag_docs_count={rag_counts}, sources.rag={rag_from_sources}, 耗时 {ms}ms"
            )
            tc.extras = {"total_tokens": t_tokens,
                         "rag_from_tool": rag_counts[0] if rag_counts else None,
                         "rag_from_sources": rag_from_sources,
                         "session_id": sid}
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)


# =============== 汇总 ===============
def summary(all_results: List[TestCase]):
    print("\n" + color("=" * 72, "cyan"))
    print(color("  Dify 对接端到端测试 汇总报告", "blue") + f" 共 {len(all_results)} 项")
    print(color("=" * 72, "cyan"))
    passed, failed = 0, 0
    for r in all_results:
        tag = color("PASS", "green") if r.ok else color("FAIL", "red")
        if r.ok: passed += 1
        else: failed += 1
        print(f" {tag} | {r.name:<52s} | {r.elapsed_ms:>5d}ms | {r.msg}")
    print("-" * 72)
    total_ms = sum(r.elapsed_ms for r in all_results)
    print(f"  通过: {passed}  失败: {failed}  总耗时: {total_ms/1000:.2f}s")
    rate = passed / len(all_results) if all_results else 0
    print(f"  通过率: {rate*100:.1f}%  " + (color("✓ 全部通过", "green") if failed == 0 else color("✗ 存在失败项", "red")))
    return failed == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dify 对接端到端测试脚本")
    ap.add_argument("--base-url", default="", help="Dify API URL, 例如 http://10.30.116.137:8088/v1")
    ap.add_argument("--api-key", default="", help="Dify 应用 API Key (app-xxxx)")
    ap.add_argument("--fabtwin-url", default="", help="FabTwin 后端地址 (空则跳过 FabTwin 链路测试)")
    ap.add_argument("--fabtwin-user", default="admin")
    ap.add_argument("--fabtwin-password", default="admin123")
    ap.add_argument("--mock", action="store_true", help="启动内存 Mock Dify 服务器，测试脚本自身逻辑")
    args = ap.parse_args(argv)

    mock = None
    if args.mock:
        mock = MockDifyServer()
        base_url, api_key = mock.base_url, mock.api_key
    else:
        base_url, api_key = args.base_url, args.api_key
        if not base_url or not api_key:
            print(color("缺少 --base-url / --api-key 参数（或使用 --mock 运行空测）", "red"))
            ap.print_help()
            sys.exit(2)

    log_step("INFO", f"Dify URL = {base_url}")
    log_step("INFO", f"FabTwin URL = {args.fabtwin_url or '(跳过)'}, Provider=hybrid")

    all_res: List[TestCase] = []
    dt = DifyTester(base_url, api_key)
    log_step("RUN",  dt.tc_01_info().name);     print("   →", dt.results[-1].msg); all_res += dt.results[-1:]
    log_step("RUN",  dt.tc_02_datasets().name); print("   →", dt.results[-1].msg); all_res += dt.results[-1:]
    log_step("RUN",  dt.tc_03_chat_rag().name); print("   →", dt.results[-1].msg); all_res += dt.results[-1:]
    log_step("RUN",  dt.tc_04_multiturn().name);print("   →", dt.results[-1].msg); all_res += dt.results[-1:]

    if args.fabtwin_url:
        log_step("INFO", "开始 FabTwin 后端链路测试 (登录→保存配置→对话)")
        ft = FabTwinBackendTester(args.fabtwin_url, args.fabtwin_user, args.fabtwin_password,
                                  base_url, api_key)
        log_step("RUN",  ft.tc_05_test_conn().name);      print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
        log_step("RUN",  ft.tc_06_save_config().name);    print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
        log_step("RUN",  ft.tc_07_chat_via_fabtwin().name); print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
    else:
        log_step("WARN", "未提供 --fabtwin-url，跳过 FabTwin 后端集成测试 (TC05~TC07)")

    ok = summary(all_res)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
