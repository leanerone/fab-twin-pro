"""FabTwin 性能基准套件

把"性能"从"手工 curl + 肉眼看时间"变成可复现、可比对、可拦截的自动化检查。

做什么：
1. 登录拿 token
2. 对预算表里的每个端点打 N 次（先冷态 1 次，再热态 N-1 次）
3. 从后端 /api/metrics/perf 取服务端口径的 P50/P95/P99
4. 与 budget.json 比对，超预算即退出码 1

用法：
    python tests/perf/benchmark.py                          # 默认 local 档
    python tests/perf/benchmark.py --profile prod           # 量产档
    python tests/perf/benchmark.py --rounds 20 --machine PODOPENER-1
    python tests/perf/benchmark.py --json-out tests/perf/last_run.json

退出码：0 全部达标 / 1 有超预算 / 2 用法或连接错误
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGET_PATH = os.path.join(HERE, "budget.json")

DEFAULT_USER = os.getenv("FABTWIN_PERF_USER", "admin")
DEFAULT_PASS = os.getenv("FABTWIN_PERF_PASS", "admin123")


def http(method: str, url: str, body: dict = None, token: str = None,
         timeout: int = 60) -> tuple[int, dict | str, float]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", (time.perf_counter() - start) * 1000
    ms = (time.perf_counter() - start) * 1000
    try:
        return status, json.loads(raw), ms
    except Exception:
        return status, raw, ms


def login(base: str, user: str, password: str) -> str:
    status, body, _ = http("POST", f"{base}/api/auth/login-password",
                           {"username": user, "password": password})
    if status != 200 or not isinstance(body, dict) or "token" not in body:
        print(f"[ERROR] 登录失败: HTTP {status} {str(body)[:200]}")
        sys.exit(2)
    return body["token"]


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] * (1 - (idx - lo)) + ordered[hi] * (idx - lo)


def run(base: str, token: str, endpoints: List[str], rounds: int,
        machine: str) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    for ep in endpoints:
        # 预算表的键形如 "GET /api/history/{tool_id}"，需要拆出方法与路径
        parts = ep.split(" ", 1)
        method, path = (parts[0], parts[1]) if len(parts) == 2 else ("GET", parts[0])
        url = base + path.replace("{tool_id}", machine)
        samples: List[float] = []
        errors = 0
        for i in range(rounds):
            status, _, ms = http(method, url, token=token)
            if status != 200:
                errors += 1
            samples.append(ms)
            if i == 0:
                cold = ms
        results[ep] = {
            "cold_ms": round(samples[0], 1),
            "p50_ms": round(percentile(samples, 0.50), 1),
            "p95_ms": round(percentile(samples, 0.95), 1),
            "p99_ms": round(percentile(samples, 0.99), 1),
            "max_ms": round(max(samples), 1),
            "rounds": rounds,
            "errors": errors,
        }
        print(f"  {ep:<42} 冷 {samples[0]:7.1f}ms  "
              f"P50 {results[ep]['p50_ms']:7.1f}  P95 {results[ep]['p95_ms']:7.1f}  "
              f"err={errors}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="FabTwin 性能基准")
    ap.add_argument("--base", default=os.getenv("FABTWIN_BASE", "http://localhost:8002"))
    ap.add_argument("--profile", default="local", choices=["local", "prod"])
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--machine", default="PODOPENER-1")
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    with open(BUDGET_PATH, "r", encoding="utf-8") as f:
        budget = json.load(f)
    profile = budget["profiles"][args.profile]
    budgets = profile["budgets"]
    endpoints = list(budgets.keys())

    print(f"=== FabTwin 性能基准 ===")
    print(f"  目标   : {args.base}")
    print(f"  档位   : {args.profile} — {profile['desc']}")
    print(f"  轮次   : {args.rounds}   机台: {args.machine}")
    print(f"  端点数 : {len(endpoints)}")
    print()

    token = login(args.base, args.user, args.password)
    print("登录成功\n")

    # 清零后端统计，保证本轮结果不被历史请求污染
    http("POST", f"{args.base}/api/metrics/perf/reset", token=token)
    results = run(args.base, token, endpoints, args.rounds, args.machine)

    print("\n=== 预算比对（客户端口径）===")
    failed = []
    for ep, r in results.items():
        limit = budgets[ep]["p95_ms"]
        ok = r["p95_ms"] <= limit
        flag = "OK " if ok else "超预算"
        print(f"  [{flag}] {ep:<42} P95 {r['p95_ms']:8.1f}ms / 预算 {limit}ms")
        if not ok:
            failed.append(ep)

    # 顺带取服务端口径做交叉验证
    _, perf, _ = http("GET", f"{args.base}/api/metrics/perf", token=token)
    if isinstance(perf, dict):
        print("\n=== 服务端口径（/api/metrics/perf，前 5 慢）===")
        for route, s in list(perf.get("routes", {}).items())[:5]:
            print(f"  {route:<42} n={s['count']:<3} P95 {s['p95_ms']:8.1f}ms  max {s['max_ms']:8.1f}ms")
        print("\n=== 慢查询（服务端捕获）===")
        slow = perf.get("slow_sql", [])
        if slow:
            for s in slow[:5]:
                print(f"  {s['ms']:8.1f}ms  {s['sql'][:90]}")
        else:
            print("  无（阈值 %sms）" % perf.get("slow_sql_ms"))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"profile": args.profile, "results": results,
                       "server": perf if isinstance(perf, dict) else None},
                      f, ensure_ascii=False, indent=2)
        print(f"\n已写入 {args.json_out}")

    print()
    if failed:
        print(f"结果: 失败 —— {len(failed)} 个端点超出预算: {failed}")
        return 1
    print("结果: 全部达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
