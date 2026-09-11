"""
n8n F1~F10 分层自测脚本
=======================
目的：一条命令测完 10 个工具，输出一张可直接粘贴回传的结果表。

分层设计（关键）：
    L1 = 直连 db_proxy   http://10.30.5.216:8001/query/xxx
    L2 = 经过 n8n Webhook http://10.30.116.151:5678/webhook/xxx
  同一个工具两层都测。对比两层结果即可定位故障层：
    L1 PASS + L2 PASS  -> 全链路正常
    L1 PASS + L2 FAIL  -> n8n 层问题（Webhook 未激活/路径写错/Header 丢失/Respond 节点没配）
    L1 FAIL + L2 FAIL  -> db_proxy 或 Oracle 层问题（看 L1 的报错原文）
    L1 FAIL + L2 PASS  -> 两层配置指向了不同环境，需核对地址

用法（Windows PowerShell）：
    # 最常用：两层全测
    python tests\\test_n8n_f1_f10.py

    # 只测 n8n 层
    python tests\\test_n8n_f1_f10.py --layer n8n

    # 测合并版（Dify 工具从 10 个收敛为 2 个之后用这个）
    python tests\\test_n8n_f1_f10.py --merged

    # 地址/密钥不同时覆盖
    python tests\\test_n8n_f1_f10.py ^
        --n8n http://10.30.116.151:5678 ^
        --proxy http://10.30.5.216:8001 ^
        --api-key fabtwin-proxy-2026 ^
        --secret ""

    # 换测试机台/批号
    python tests\\test_n8n_f1_f10.py --machine OXE-51 --lot V47Q6

    # 结果落盘（把这个文件回传给我，比截图信息全）
    python tests\\test_n8n_f1_f10.py --json-out tests\\n8n_result.json

关于 --merged：
    Dify 会按 OpenAPI 里的 path 数量注册工具，原来 F1~F10 十个 path 一次性占满
    Agent 的工具位。收敛方案是只留 2 个 path，用 action 参数分发：
        fab_query  读类   <- F1 F2 F3 F4 F5 F6 F10
        fab_admin  管理类 <- F7 F8 F9
    加 --merged 后：
        L1 不变，仍直连 db_proxy 原来那 10 个端点（它们保留着，是稳定的对照基准）
        L2 改打 n8n 的 fab_query / fab_admin 两个 webhook，payload 里多带 action
    两层仍能一一对比（M1 对 F1、M3 对 F3…），所以四象限判读照常有效：
        L1 PASS + L2 FAIL 就说明问题出在「合并这一层」，而不是底层查询。
    最常见的合并版故障是 n8n 的 jsonBody 沿用了旧的逐字段白名单写法，
    把 action 丢掉了，此时 db_proxy 会回「缺少 action 参数」，answer 里看得到。

判读标准（脚本已自动断言，无需人工判断）：
    1. HTTP 200
    2. 响应是合法 JSON 且为 object
    3. 含 ok 字段；ok=true
    4. answer 为非空字符串
    5. table_data 为 null，或含 headers(list) + rows(list)
    6. table_data.rows 每行长度 == headers 长度
  以上任一不满足即 FAIL，并打印失败原因与响应原文前 300 字。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("缺少依赖，请先执行: pip install requests")
    sys.exit(2)


DEFAULT_N8N = "http://10.30.116.151:5678"
DEFAULT_PROXY = "http://10.30.5.216:8001"
DEFAULT_API_KEY = "fabtwin-proxy-2026"


# ========== 10 个工具的定义 ==========
# webhook: n8n Webhook path（对应 OpenAPI 的 operationId）
# proxy  : db_proxy 的 FastAPI 路由
# payload: 请求体构造函数，入参为运行时上下文
TOOLS: List[Dict[str, Any]] = [
    {
        "id": "F1", "name": "机台状态",
        "webhook": "get_machine_status", "proxy": "/query/machine_status",
        "payload": lambda c: {"machine_id": c["machine"]},
        "expect_rows": True,
    },
    {
        "id": "F1b", "name": "机台状态-全厂",
        "webhook": "get_machine_status", "proxy": "/query/machine_status",
        "payload": lambda c: {"machine_id": ""},
        "expect_rows": True,
    },
    {
        "id": "F2", "name": "批次信息",
        "webhook": "get_lot_info", "proxy": "/query/lot_info",
        "payload": lambda c: {"machine_id": c["machine"]},
        "expect_rows": False,
    },
    {
        "id": "F3", "name": "机台告警",
        "webhook": "get_machine_alarms", "proxy": "/query/machine_alarms",
        "payload": lambda c: {"machine_id": c["machine"], "severity": "", "days": 7},
        "expect_rows": False,
    },
    {
        "id": "F4", "name": "事件时间线",
        "webhook": "get_event_timeline", "proxy": "/query/event_timeline",
        "payload": lambda c: {"machine_id": c["machine"], "time_range": "last_7d"},
        "expect_rows": False,
    },
    {
        "id": "F5", "name": "产能统计",
        "webhook": "get_yield_stats", "proxy": "/query/yield_stats",
        "payload": lambda c: {"machine_id": c["machine"], "time_range": "today"},
        "expect_rows": False,
    },
    {
        "id": "F6", "name": "配方信息",
        "webhook": "get_recipe_info", "proxy": "/query/recipe_info",
        "payload": lambda c: {"machine_id": c["machine"]},
        "expect_rows": False,
    },
    {
        "id": "F7", "name": "MES批次",
        "webhook": "get_mes_lot_info", "proxy": "/query/mes_lot_info",
        "payload": lambda c: {"lot_id": c["lot"]},
        "expect_rows": False,
    },
    {
        "id": "F8", "name": "导出告警报表",
        "webhook": "export_alarm_report", "proxy": "/query/export_alarm_report",
        "payload": lambda c: {"machine_id": c["machine"], "days": 7},
        "expect_rows": False,
    },
    {
        "id": "F9", "name": "生成故障工单",
        "webhook": "generate_work_order", "proxy": "/query/generate_work_order",
        "payload": lambda c: {"machine_id": c["machine"],
                              "fault_type": "RF Reflect Power High",
                              "severity": "high"},
        "expect_rows": False,
    },
    {
        "id": "F10", "name": "能力清单",
        "webhook": "list_capabilities", "proxy": "/query/list_capabilities",
        "payload": lambda c: {},
        "expect_rows": False,
    },
]

# ========== 合并版工具定义（2 组 webhook，Dify 工具合并后替代上面 10 条） ==========
# 注意这个列表只用于 L2（n8n 层）测试。L1（直连 db_proxy）继续走 TOOLS。
# payload 里多了 action 参数，n8n 会原样透传给 db_proxy 分发端点。
MERGED_TOOLS: List[Dict[str, Any]] = [
    # --- fab_query（读类，合并 F1~F6 + F10）---
    {
        "id": "M1", "name": "机台状态",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "machine_status", "machine_id": c["machine"]},
        "expect_rows": True,
    },
    {
        "id": "M1b", "name": "机台状态-全厂",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "machine_status", "machine_id": ""},
        "expect_rows": True,
    },
    {
        "id": "M2", "name": "批次信息",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "lot_info", "machine_id": c["machine"]},
        "expect_rows": False,
    },
    {
        "id": "M3", "name": "机台告警",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "machine_alarms", "machine_id": c["machine"],
                              "severity": "", "days": 7},
        "expect_rows": False,
    },
    {
        "id": "M4", "name": "事件时间线",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "event_timeline", "machine_id": c["machine"],
                              "time_range": "last_7d"},
        "expect_rows": False,
    },
    {
        "id": "M5", "name": "产能统计",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "yield_stats", "machine_id": c["machine"],
                              "time_range": "today"},
        "expect_rows": False,
    },
    {
        "id": "M6", "name": "配方信息",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "recipe_info", "machine_id": c["machine"]},
        "expect_rows": False,
    },
    # --- fab_admin（管理类，合并 F7 F8 F9）---
    {
        "id": "M7", "name": "MES批次",
        "webhook": "fab_admin",
        "payload": lambda c: {"action": "mes_lot_info", "lot_id": c["lot"]},
        "expect_rows": False,
    },
    {
        "id": "M8", "name": "导出告警报表",
        "webhook": "fab_admin",
        "payload": lambda c: {"action": "export_alarm_report", "machine_id": c["machine"],
                              "days": 7},
        "expect_rows": False,
    },
    {
        "id": "M9", "name": "生成故障工单",
        "webhook": "fab_admin",
        "payload": lambda c: {"action": "generate_work_order", "machine_id": c["machine"],
                              "fault_type": "RF Reflect Power High", "severity": "high"},
        "expect_rows": False,
    },
    {
        "id": "M10", "name": "能力清单",
        "webhook": "fab_query",
        "payload": lambda c: {"action": "list_capabilities"},
        "expect_rows": False,
    },
]

# MERGED_TOOLS 与 TOOLS 是一一对应的（M1↔F1、M1b↔F1b、…、M10↔F10），
# 这里自动补一个 maps_to，让 --merged 模式下 L1(F*) 与 L2(M*) 仍能按同一个逻辑
# 工具配对，否则 print_diagnosis 拿 tool_id 做键会全部对不上，四象限诊断就废了。
for _t in MERGED_TOOLS:
    _t["maps_to"] = "F" + _t["id"][1:]


@dataclass
class Result:
    tool_id: str
    tool_name: str
    layer: str
    ok: bool = False
    http: int = 0
    ms: int = 0
    answer: str = ""
    rows: int = 0
    reason: str = ""
    raw: str = ""
    maps_to: str = ""


def _short(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _pad(s: str, width: int) -> str:
    """按显示宽度补齐（中文算 2 列），保证表格在等宽终端对齐。"""
    w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)
    return s + " " * max(0, width - w)


def check_contract(data: Any, expect_rows: bool) -> str:
    """返回空字符串表示通过，否则返回失败原因。"""
    if not isinstance(data, dict):
        return f"响应不是 JSON object，实际类型 {type(data).__name__}"
    if "ok" not in data:
        return "响应缺少 ok 字段（n8n Respond 节点可能没透传 db_proxy 的 body）"
    if data.get("ok") is not True:
        return f"ok=false，answer={_short(str(data.get('answer')), 120)}"
    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return "answer 为空或非字符串"
    td = data.get("table_data")
    if td is not None:
        if not isinstance(td, dict):
            return f"table_data 非 object，实际 {type(td).__name__}"
        headers, rows = td.get("headers"), td.get("rows")
        if not isinstance(headers, list) or not isinstance(rows, list):
            return "table_data 缺少 headers/rows 或类型不对"
        for i, r in enumerate(rows[:50]):
            if not isinstance(r, list):
                return f"table_data.rows[{i}] 不是数组"
            if len(r) != len(headers):
                return f"table_data.rows[{i}] 列数 {len(r)} != headers 列数 {len(headers)}"
    elif expect_rows:
        return "期望返回表格数据，但 table_data 为 null（多半是查不到数据，需确认库里有该机台）"
    return ""


def run_one(tool: Dict[str, Any], layer: str, url: str,
            headers: Dict[str, str], ctx: Dict[str, str], timeout: int) -> Result:
    r = Result(tool["id"], tool["name"], layer)
    r.maps_to = tool.get("maps_to", tool["id"])
    body = tool["payload"](ctx)
    t0 = time.perf_counter()
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=timeout)
    except requests.exceptions.ConnectTimeout:
        r.ms = int((time.perf_counter() - t0) * 1000)
        r.reason = "连接超时（服务未启动或防火墙拦截）"
        return r
    except requests.exceptions.ConnectionError as e:
        r.ms = int((time.perf_counter() - t0) * 1000)
        r.reason = f"连接失败：{_short(str(e), 100)}"
        return r
    except Exception as e:
        r.ms = int((time.perf_counter() - t0) * 1000)
        r.reason = f"请求异常：{_short(str(e), 100)}"
        return r

    r.ms = int((time.perf_counter() - t0) * 1000)
    r.http = resp.status_code
    r.raw = resp.text[:1000]

    if resp.status_code != 200:
        hint = ""
        if resp.status_code == 401:
            hint = "（API Key 不对，检查 X-API-Key）"
        elif resp.status_code == 404:
            hint = "（路径不存在：n8n Webhook 未激活，或 path 写错；n8n 测试模式的 webhook 只在点了 Execute 后 120 秒内有效，需点 Active 开关）"
        elif resp.status_code == 500:
            hint = "（服务端异常，看 raw 里的报错）"
        r.reason = f"HTTP {resp.status_code}{hint}: {_short(resp.text, 200)}"
        return r

    try:
        data = resp.json()
    except Exception:
        r.reason = f"响应不是合法 JSON: {_short(resp.text, 200)}"
        return r

    # n8n 有时会把 body 包一层数组 [{...}]
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
        r.reason = ""

    problem = check_contract(data, tool.get("expect_rows", False))
    if problem:
        r.reason = problem
        r.answer = _short(str(data.get("answer", "")) if isinstance(data, dict) else "", 60)
        return r

    r.ok = True
    r.answer = _short(data.get("answer", ""), 60)
    td = data.get("table_data")
    r.rows = len(td.get("rows", [])) if isinstance(td, dict) else 0
    return r


def print_table(results: List[Result], title: str) -> None:
    if not results:
        return
    print()
    print("=" * 108)
    print(f"  {title}")
    print("=" * 108)
    print(_pad("状态", 8) + _pad("工具", 8) + _pad("名称", 16) +
          _pad("HTTP", 6) + _pad("耗时", 8) + _pad("行数", 6) + "answer 摘要")
    print("-" * 108)
    for r in results:
        tag = "[PASS]" if r.ok else "[FAIL]"
        tail = r.answer if r.ok else r.reason
        print(_pad(tag, 8) + _pad(r.tool_id, 8) + _pad(r.tool_name, 16) +
              _pad(str(r.http or "-"), 6) + _pad(f"{r.ms}ms", 8) +
              _pad(str(r.rows), 6) + _short(tail, 46))
    passed = sum(1 for r in results if r.ok)
    print("-" * 108)
    print(f"  通过 {passed}/{len(results)}    总耗时 {sum(r.ms for r in results)/1000:.2f}s")


def print_diagnosis(l1: List[Result], l2: List[Result], merged: bool = False) -> None:
    """两层对比，直接给出故障定位结论。

    配对用 maps_to 而不是 tool_id：--merged 模式下 L1 是 F1/F2…，L2 是 M1/M2…，
    直接拿 tool_id 当键会一个都配不上。maps_to 统一归一到 F* 这套逻辑编号。
    """
    if not l1 or not l2:
        return
    m1 = {(r.maps_to or r.tool_id): r for r in l1}
    m2 = {(r.maps_to or r.tool_id): r for r in l2}
    both_ok, n8n_bad, proxy_bad, weird = [], [], [], []

    def _label(key: str) -> str:
        """L1/L2 编号不同时显示成 F3->M3，方便回头对照上面两张表。"""
        a_id, b_id = m1[key].tool_id, m2[key].tool_id
        return a_id if a_id == b_id else f"{a_id}->{b_id}"

    for tid in m1:
        if tid not in m2:
            continue
        a, b = m1[tid].ok, m2[tid].ok
        lab = _label(tid)
        if a and b:
            both_ok.append(lab)
        elif a and not b:
            n8n_bad.append(lab)
        elif not a and not b:
            proxy_bad.append(lab)
        else:
            weird.append(lab)

    print()
    print("=" * 108)
    print("  故障定位结论")
    print("=" * 108)
    if both_ok:
        print(f"  [正常]      全链路通过 ({len(both_ok)}): {', '.join(both_ok)}")
    if proxy_bad:
        print(f"  [db_proxy]  两层都失败 ({len(proxy_bad)}): {', '.join(proxy_bad)}")
        print("              -> 问题在 db_proxy 或 Oracle，与 n8n 无关。先看上面 L1 的失败原因。")
    if n8n_bad:
        print(f"  [n8n]       仅 n8n 层失败 ({len(n8n_bad)}): {', '.join(n8n_bad)}")
        print("              -> db_proxy 是好的，问题在 n8n。排查顺序：")
        if merged:
            print("                 1) FAB_QUERY / FAB_ADMIN 两个 workflow 是否都已点 Active")
            print("                 2) Webhook 节点 path 是否正好是 fab_query / fab_admin")
            print("                 3) HTTP Request 节点是否带 X-API-Key: fabtwin-proxy-2026")
            print("                 4) HTTP Request 的 URL 是否指向 /query/fab_query 或 /query/fab_admin")
            print("                 5) jsonBody 是否为整体透传 {{ JSON.stringify($json.body || {}) }}")
            print("                    —— 若沿用旧的逐字段白名单写法，action 会被丢掉，")
            print("                       db_proxy 会回「缺少 action 参数」，answer 里能看到")
        else:
            print("                 1) 该 workflow 是否已点 Active（不是 Execute Workflow 测试模式）")
            print("                 2) Webhook 节点 path 是否与上表工具名完全一致")
            print("                 3) HTTP Request 节点是否带 X-API-Key: fabtwin-proxy-2026")
            print("                 4) Respond to Webhook 节点是否设为 First Incoming Item / 透传 body")
    if weird:
        print(f"  [环境不一致] n8n 通过但直连失败 ({len(weird)}): {', '.join(weird)}")
        print("              -> 两层地址可能指向了不同环境，核对 --proxy 地址是否与 n8n 内配置一致。")


def check_health(proxy: str, timeout: int) -> None:
    print("-" * 108)
    try:
        resp = requests.get(f"{proxy}/health", timeout=timeout)
        try:
            d = resp.json()
        except Exception:
            d = {}
        if resp.status_code == 200 and d.get("db") == "connected":
            print(f"  [PASS] db_proxy /health  -> {d}")
        else:
            print(f"  [FAIL] db_proxy /health  -> HTTP {resp.status_code} {_short(resp.text, 200)}")
            print("         Oracle 未连上，后续 F1~F10 大概率全挂。先修这个。")
    except Exception as e:
        print(f"  [FAIL] db_proxy /health  -> 连不上: {_short(str(e), 150)}")
        print(f"         确认 db_proxy 已启动：cd services\\db_proxy && python main.py")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="n8n F1~F10 分层自测")
    ap.add_argument("--n8n", default=DEFAULT_N8N, help=f"n8n 地址，默认 {DEFAULT_N8N}")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help=f"db_proxy 地址，默认 {DEFAULT_PROXY}")
    ap.add_argument("--api-key", default=DEFAULT_API_KEY, help="db_proxy 的 X-API-Key")
    ap.add_argument("--secret", default="", help="n8n Webhook secret（配了才填）")
    ap.add_argument("--layer", default="both", choices=["both", "n8n", "proxy"], help="测哪一层")
    ap.add_argument("--machine", default="OXE-51", help="测试机台号")
    ap.add_argument("--lot", default="V47Q6", help="测试批号（F7 用）")
    ap.add_argument("--timeout", type=int, default=60, help="单次请求超时秒数")
    ap.add_argument("--merged", action="store_true",
                    help="n8n 层改测合并版 2 个 webhook（fab_query/fab_admin），"
                         "默认仍测原来 10 个独立 webhook")
    ap.add_argument("--json-out", default="", help="结果写入 JSON 文件，便于回传")
    args = ap.parse_args(argv)

    ctx = {"machine": args.machine, "lot": args.lot}
    n8n = args.n8n.rstrip("/")
    proxy = args.proxy.rstrip("/")

    print("=" * 108)
    print("  n8n F1~F10 分层自测" + ("（n8n 层：合并版 2 工具）" if args.merged else ""))
    print("=" * 108)
    print(f"  n8n     : {n8n}")
    print(f"  db_proxy: {proxy}")
    print(f"  机台    : {args.machine}    批号: {args.lot}")
    print(f"  层级    : {args.layer}")
    if args.merged:
        print(f"  n8n 层  : fab_query / fab_admin（action 分发，共 {len(MERGED_TOOLS)} 个用例）")

    l1: List[Result] = []
    l2: List[Result] = []

    if args.layer in ("both", "proxy"):
        check_health(proxy, args.timeout)
        h = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
        for t in TOOLS:
            l1.append(run_one(t, "L1-proxy", proxy + t["proxy"], h, ctx, args.timeout))
        print_table(l1, "L1 直连 db_proxy 结果")

    if args.layer in ("both", "n8n"):
        h = {"Content-Type": "application/json"}
        # L1 始终走原 10 个端点（它们在 db_proxy 里保留着，是稳定的对照基准）；
        # 只有 L2 按 --merged 切换，这样两层对比才能确认「合并层」本身有没有引入问题。
        n8n_tools = MERGED_TOOLS if args.merged else TOOLS
        for t in n8n_tools:
            url = f"{n8n}/webhook/{t['webhook']}"
            if args.secret:
                url += f"?secret={args.secret}"
            l2.append(run_one(t, "L2-n8n", url, h, ctx, args.timeout))
        title = "L2 经过 n8n Webhook 结果"
        if args.merged:
            title += "（合并版 fab_query / fab_admin）"
        print_table(l2, title)

    if args.layer == "both":
        print_diagnosis(l1, l2, merged=args.merged)

    fails = [r for r in (l1 + l2) if not r.ok]
    if fails:
        print()
        print("=" * 108)
        print(f"  失败明细（共 {len(fails)} 项，含响应原文，回传时请一并附上）")
        print("=" * 108)
        for r in fails:
            print(f"\n  [{r.layer}] {r.tool_id} {r.tool_name}")
            print(f"    原因: {r.reason}")
            if r.raw:
                print(f"    原文: {_short(r.raw, 400)}")

    if args.json_out:
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": {"n8n": n8n, "proxy": proxy,
                       "machine": args.machine, "lot": args.lot, "layer": args.layer,
                       "merged": args.merged},
            "results": [
                {"layer": r.layer, "tool_id": r.tool_id, "tool_name": r.tool_name,
                 "maps_to": r.maps_to,
                 "ok": r.ok, "http": r.http, "ms": r.ms, "rows": r.rows,
                 "answer": r.answer, "reason": r.reason, "raw": r.raw}
                for r in (l1 + l2)
            ],
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已写入: {args.json_out}")

    total = len(l1) + len(l2)
    print(f"\n  最终: 通过 {total - len(fails)}/{total}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
