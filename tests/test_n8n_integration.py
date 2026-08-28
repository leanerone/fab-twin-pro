"""
n8n 对接端到端测试脚本
=======================
功能：
  1. 直连 n8n API 测试 (不依赖 FabTwin 后端)
       - GET  /healthz               健康检查
       - GET  /api/v1/workflows      工作流列表
       - POST /webhook/{wf_type}     5 种工作流 Webhook 触发
  2. 直连 FabTwin AI 中间件测试
       - POST /api/ai/config/test    (n8n 连接测试 API)
       - PUT  /api/ai/config         (写入 n8n 配置)
       - POST /api/ai/chat           (AI 对话：触发 n8n workflow)

用法:
    # 仅测试 n8n 直连
    python test_n8n_integration.py ^
        --base-url http://10.30.116.137:5678 ^
        --user admin --password FabTwin#2026!N8n

    # 同时测试 FabTwin 后端
    python test_n8n_integration.py ^
        --base-url http://10.30.116.137:5678 ^
        --user admin --password FabTwin#2026!N8n ^
        --fabtwin-url http://localhost:8002 ^
        --fabtwin-user admin --fabtwin-password admin123

    # Mock 模式（无需真实 n8n）
    python test_n8n_integration.py --mock
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


@dataclass
class TestCase:
    name: str
    desc: str
    ok: bool = False
    msg: str = ""
    elapsed_ms: int = 0
    extras: Dict[str, Any] = field(default_factory=dict)


def color(s: str, c: str) -> str:
    palette = {"red":"31","green":"32","yellow":"33","blue":"34","cyan":"36","gray":"37"}
    return f"\033[{palette.get(c,'37')}m{s}\033[0m"

def log_step(tag, s):
    tc = {"RUN":"cyan","OK":"green","FAIL":"red","WARN":"yellow","INFO":"blue"}[tag]
    print(color(f"[{tag:4s}]", tc) + f" {s}")

def call(method, url, *, headers=None, params=None, json_body=None, timeout=30):
    t0 = time.perf_counter()
    resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)
    dt = int((time.perf_counter() - t0) * 1000)
    return resp, dt


# =============== Mock n8n Server ===============
class MockN8nServer:
    def __init__(self):
        import http.server, threading
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a, **k): pass
            def _send_json(self, code, body):
                data = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path.startswith("/healthz") or self.path.startswith("/health"):
                    return self._send_json(200, {"status":"ok","timestamp":int(time.time())})
                if self.path.startswith("/api/v1/workflows"):
                    return self._send_json(200, {
                        "count":5,
                        "data":[
                            {"id":"wf-1","name":"FabTwin - 导出告警报表","active":True},
                            {"id":"wf-2","name":"FabTwin - 生成故障工单","active":True},
                            {"id":"wf-3","name":"FabTwin - 批量导出设备数据","active":True},
                            {"id":"wf-4","name":"FabTwin - 产线日报自动推送","active":True},
                            {"id":"wf-5","name":"FabTwin - 通用查询","active":True},
                        ]
                    })
                return self._send_json(404, {"code":"not_found"})
            def do_POST(self):
                length = int(self.headers.get("Content-Length","0"))
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except: body = {}
                if self.path.startswith("/webhook/export_alarm_report"):
                    return self._send_json(200, {
                        "answer":"已导出告警报表，共 23 条报警记录。",
                        "data":[
                            {"timestamp":"2026-08-28 08:30:15","machine_id":"OXE-01","alarm_code":"E201","severity":"high","description":"RF Reflect Power High"},
                            {"timestamp":"2026-08-28 09:15:42","machine_id":"OXE-02","alarm_code":"E130","severity":"medium","description":"Double Slot Map Fail"},
                        ],
                        "executionId":"exec-mock-001","duration":1500,
                        "usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
                    })
                if self.path.startswith("/webhook/generate_work_order"):
                    return self._send_json(200, {
                        "answer":"故障工单已生成，工单号：WO-2026-0828-001。",
                        "executionId":"exec-mock-002","duration":800
                    })
                if self.path.startswith("/webhook/export_machine_data"):
                    return self._send_json(200, {
                        "answer":"设备数据已导出，共 500 条事件记录。",
                        "data":[{"machine_id":"OXE-01","event":"WaferLoaded","count":120}],
                        "executionId":"exec-mock-003","duration":2000
                    })
                if self.path.startswith("/webhook/push_daily_report"):
                    return self._send_json(200, {
                        "answer":"产线日报已推送到钉钉群。",
                        "executionId":"exec-mock-004","duration":500
                    })
                if self.path.startswith("/webhook/general_query"):
                    return self._send_json(200, {
                        "answer":"通用查询完成：OXE-01 当前状态为 Idle，3 个 Chamber 均空闲。",
                        "executionId":"exec-mock-005","duration":300
                    })
                # ping/test 请求（连接测试时发送）
                if "ping" in str(body).lower() or "test" in str(body).lower():
                    return self._send_json(200, {"answer":"pong"})
                return self._send_json(404, {"code":"not_found"})
        self._srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self._srv.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.user = "admin"
        self.password = "mock-pass"
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()
        print(color(f"[MOCK] 已启动模拟 n8n Server at {self.base_url}", "gray"))


# =============== n8n 直连测试 ===============
class N8nTester:
    def __init__(self, base_url: str, user: str, password: str, webhook_secret: str = ""):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.webhook_secret = webhook_secret
        self.results: List[TestCase] = []

    def _auth_header(self) -> Dict[str, str]:
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    # TC01: 健康检查
    def tc_01_healthz(self) -> TestCase:
        tc = TestCase("TC01 n8n /healthz", "健康检查，验证 n8n 服务是否在线")
        try:
            resp, ms = call("GET", f"{self.base_url}/healthz", timeout=10)
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return tc
            data = resp.json() if resp.headers.get("content-type","").startswith("application/json") else {}
            tc.ok = True
            tc.msg = f"OK. status={data.get('status','ok')}, 耗时 {ms}ms"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    # TC02: 工作流列表
    def tc_02_workflows(self) -> TestCase:
        tc = TestCase("TC02 n8n /api/v1/workflows", "获取工作流列表，确认 5 个 FabTwin 模板已导入")
        try:
            resp, ms = call("GET", f"{self.base_url}/api/v1/workflows?limit=20",
                            headers=self._auth_header(), timeout=15)
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return tc
            data = resp.json() or {}
            count = data.get("count") or len(data.get("data") or [])
            names = [w.get("name") for w in (data.get("data") or [])]
            tc.ok = count >= 5
            tc.msg = f"OK. 共 {count} 个工作流: {names[:6]}, 耗时 {ms}ms"
            tc.extras["workflow_count"] = count
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    # TC03~07: 5 种工作流 Webhook 测试
    def _tc_webhook(self, wf_name: str, wf_path: str, question: str, expect_data: bool = False) -> TestCase:
        tc = TestCase(f"TC n8n /webhook/{wf_path}", f"触发 {wf_name} 工作流")
        url = f"{self.base_url}/webhook/{wf_path}"
        if self.webhook_secret:
            url += f"?secret={self.webhook_secret}"
        payload = {
            "question": question,
            "machine_id": "OXE-01",
            "user_role": "admin",
            "workflow_type": wf_path,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            resp, ms = call("POST", url, json_body=payload, timeout=60)
            tc.elapsed_ms = ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return tc
            data = resp.json()
            answer = data.get("answer", data.get("message", ""))
            exec_id = data.get("executionId") or data.get("execution_id")
            has_data = isinstance(data.get("data"), list) and len(data.get("data")) > 0
            tc.ok = bool(answer)
            tc.msg = (f"OK. answer长度={len(answer)}, exec_id={exec_id}, "
                     f"data_rows={len(data.get('data',[])) if isinstance(data.get('data'),list) else 0}, "
                     f"耗时 {ms}ms")
            if expect_data and not has_data:
                tc.msg += " ⚠️ 期望返回 data 列表但未找到"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"
            return tc
        finally:
            self.results.append(tc)

    def tc_03_export_alarm(self):
        return self._tc_webhook("导出告警报表", "export_alarm_report",
                               "导出OXE-01今天的告警报表", expect_data=True)
    def tc_04_work_order(self):
        return self._tc_webhook("生成故障工单", "generate_work_order",
                               "给OXE-01生成故障工单")
    def tc_05_export_data(self):
        return self._tc_webhook("导出设备数据", "export_machine_data",
                               "导出OXE-01最近24h设备数据", expect_data=True)
    def tc_06_push_report(self):
        return self._tc_webhook("日报推送", "push_daily_report",
                               "推送今天的产线日报")
    def tc_07_general_query(self):
        return self._tc_webhook("通用查询", "general_query",
                               "查询OXE-01当前状态")


# =============== FabTwin 后端测试 ===============
class FabTwinBackendTester:
    def __init__(self, fabtwin_url, user, password, n8n_url, n8n_user, n8n_password):
        self.base = fabtwin_url.rstrip("/")
        self.user = user
        self.pwd = password
        self.n8n_url = n8n_url
        self.n8n_user = n8n_user
        self.n8n_password = n8n_password
        self.token: Optional[str] = None
        self.results: List[TestCase] = []

    def _login(self, tc) -> bool:
        try:
            resp, ms = call("POST", f"{self.base}/api/auth/login",
                           json_body={"username": self.user, "password": self.pwd}, timeout=15)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"登录失败 HTTP {resp.status_code}: {resp.text[:200]}"; return False
            data = resp.json()
            self.token = data.get("access_token") or (data.get("data") or {}).get("token") or ""
            return bool(self.token)
        except Exception as e:
            tc.msg = f"登录异常: {e}"; return False

    def _h(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    # TC08: 连接测试
    def tc_08_test_conn(self):
        tc = TestCase("TC08 FabTwin /api/ai/config/test (n8n)",
                      "通过 FabTwin 后端测试 n8n 连接，应返回工作流数和 Webhook 激活状态")
        if not self._login(tc):
            self.results.append(tc); return tc
        try:
            resp, ms = call("POST", f"{self.base}/api/ai/config/test", headers=self._h(),
                           json_body={"provider_type":"n8n",
                                       "config":{"base_url": self.n8n_url,
                                                 "api_key": self.n8n_password}},
                           timeout=30)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:200]}"; return tc
            data = resp.json()
            tc.ok = bool(data.get("success"))
            tc.msg = f"success={tc.ok}, message={data.get('message','')[:120]}, 耗时 {tc.elapsed_ms}ms"
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)

    # TC09: 保存 n8n 配置
    def tc_09_save_config(self):
        tc = TestCase("TC09 FabTwin /api/ai/config PUT (n8n)",
                      "保存 n8n 启用开关 + URL + Webhook Secret")
        if not self.token and not self._login(tc):
            self.results.append(tc); return tc
        try:
            resp, ms = call("PUT", f"{self.base}/api/ai/config", headers=self._h(),
                           json_body={
                               "n8n_enabled": True,
                               "n8n_base_url": self.n8n_url,
                               "n8n_webhook_secret": "",
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

    # TC10: AI Chat 触发 n8n 工作流
    def tc_10_chat_n8n(self):
        tc = TestCase("TC10 FabTwin /api/ai/chat (触发 n8n workflow)",
                      "通过 AI 对话'导出OXE-01今天的告警报表'，验证 n8n workflow 被触发并返回 tool_calls")
        if not self.token and not self._login(tc):
            self.results.append(tc); return tc
        sid = f"n8n-e2e-{uuid.uuid4().hex[:10]}"
        payload = {"question":"导出OXE-01今天的告警报表","session_id":sid,"machine_id":"OXE-01"}
        try:
            resp, ms = call("POST", f"{self.base}/api/ai/chat", headers=self._h(),
                           json_body=payload, timeout=120)
            tc.elapsed_ms += ms
            if resp.status_code != 200:
                tc.msg = f"HTTP {resp.status_code}: {resp.text[:300]}"; return tc
            d = resp.json()
            answer = (d.get("answer") or "").strip()
            tool_calls = d.get("tool_calls") or []
            n8n_calls = [t for t in tool_calls if isinstance(t, dict) and "n8n" in (t.get("tool") or "")]
            has_table = bool(d.get("table_data"))
            sources = d.get("sources") or []
            n8n_sources = [s for s in sources if isinstance(s, dict) and s.get("type") == "n8n"]
            tc.ok = bool(answer) and len(n8n_calls) > 0
            tc.msg = (f"OK. answer={len(answer)}chars, n8n_tool_calls={len(n8n_calls)}, "
                     f"table={has_table}, n8n_sources={len(n8n_sources)}, 耗时 {ms}ms")
            tc.extras = {"n8n_tool_count": len(n8n_calls),
                        "workflow": n8n_calls[0].get("tool") if n8n_calls else None,
                        "has_table": has_table}
            return tc
        except Exception as e:
            tc.msg = f"异常: {e}"; return tc
        finally:
            self.results.append(tc)


# =============== 汇总 ===============
def summary(all_results):
    print("\n" + color("="*72, "cyan"))
    print(color("  n8n 对接端到端测试 汇总报告", "blue") + f" 共 {len(all_results)} 项")
    print(color("="*72, "cyan"))
    passed, failed = 0, 0
    for r in all_results:
        tag = color("PASS","green") if r.ok else color("FAIL","red")
        if r.ok: passed += 1
        else: failed += 1
        print(f" {tag} | {r.name:<54s} | {r.elapsed_ms:>5d}ms | {r.msg}")
    print("-"*72)
    total_ms = sum(r.elapsed_ms for r in all_results)
    rate = passed / len(all_results) if all_results else 0
    print(f"  通过: {passed}  失败: {failed}  总耗时: {total_ms/1000:.2f}s  通过率: {rate*100:.1f}%")
    return failed == 0

def main(argv=None):
    ap = argparse.ArgumentParser(description="n8n 对接端到端测试脚本")
    ap.add_argument("--base-url", default="", help="n8n 服务地址, 如 http://10.30.116.137:5678")
    ap.add_argument("--user", default="admin", help="n8n 账号")
    ap.add_argument("--password", default="", help="n8n 密码")
    ap.add_argument("--webhook-secret", default="", help="n8n Webhook 密钥")
    ap.add_argument("--fabtwin-url", default="", help="FabTwin 后端地址")
    ap.add_argument("--fabtwin-user", default="admin")
    ap.add_argument("--fabtwin-password", default="admin123")
    ap.add_argument("--mock", action="store_true", help="启动 Mock n8n Server")
    args = ap.parse_args(argv)

    mock = None
    if args.mock:
        mock = MockN8nServer()
        base_url = mock.base_url
        user, password = mock.user, mock.password
    else:
        base_url = args.base_url
        user, password = args.user, args.password
        if not base_url:
            print(color("缺少 --base-url 参数（或使用 --mock）", "red"))
            ap.print_help(); sys.exit(2)

    log_step("INFO", f"n8n URL = {base_url}")
    log_step("INFO", f"FabTwin URL = {args.fabtwin_url or '(跳过)'}")

    all_res = []
    nt = N8nTester(base_url, user, password, args.webhook_secret)
    log_step("RUN",  nt.tc_01_healthz().name);       print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_02_workflows().name);     print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_03_export_alarm().name);  print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_04_work_order().name);    print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_05_export_data().name);   print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_06_push_report().name);   print("   →", nt.results[-1].msg); all_res += nt.results[-1:]
    log_step("RUN",  nt.tc_07_general_query().name);print("   →", nt.results[-1].msg); all_res += nt.results[-1:]

    if args.fabtwin_url:
        log_step("INFO", "开始 FabTwin 后端链路测试 (登录→保存配置→AI chat)")
        ft = FabTwinBackendTester(args.fabtwin_url, args.fabtwin_user, args.fabtwin_password,
                                  base_url, user, password)
        log_step("RUN",  ft.tc_08_test_conn().name);   print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
        log_step("RUN",  ft.tc_09_save_config().name); print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
        log_step("RUN",  ft.tc_10_chat_n8n().name);    print("   →", ft.results[-1].msg); all_res += ft.results[-1:]
    else:
        log_step("WARN", "未提供 --fabtwin-url，跳过 FabTwin 后端集成测试 (TC08~TC10)")

    ok = summary(all_res)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
