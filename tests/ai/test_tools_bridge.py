# -*- coding: utf-8 -*-
"""T4 回归：AI 工具桥 REST 暴露（2026-11-06）

验证：
  1. GET  /api/ai/tools         工具清单 12 个（10 固定 + 2 SQL）
  2. POST /api/ai/tools/{name}  固定工具与 SQL 工具可执行、结果为 dict
  3. SQL 工具安全边界：DELETE/非白名单表被 sql guard 拒（200+executed=false，按工具设计）
  4. 未知工具 404；未登录 401
  5. GET /api/ai/tools/openapi.json  Dify 可导入规范（openapi 3.x + 全部 path）

运行（前提：后端已带本路由启动，替身不必）：
  python tests/ai/test_tools_bridge.py --backend http://127.0.0.1:8003
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


def http(method, path, data=None, token=None, timeout=30):
    req = urllib.request.Request(BACKEND + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def main():
    global BACKEND
    BACKEND = "http://127.0.0.1:8003"
    for i, a in enumerate(sys.argv):
        if a == "--backend" and i + 1 < len(sys.argv):
            BACKEND = sys.argv[i + 1]

    # 登录
    st, body = http("POST", "/api/auth/login-password",
                    {"username": "admin", "password": "admin123"})
    token = body.get("token", "") if isinstance(body, dict) else ""
    check("登录获取 token", st == 200 and token, f"HTTP {st}")

    # ── 1. 工具清单 ────────────────────────────────────────
    st, body = http("GET", "/api/ai/tools", token=token)
    tools = body.get("tools", []) if isinstance(body, dict) else []
    names = {t.get("name") for t in tools}
    check("GET /tools 200 且 12 个工具", st == 200 and len(tools) == 12,
          f"HTTP {st} count={len(tools)}")
    check("SQL 工具在列", {"describe_fab_table", "query_fab_data"} <= names)
    check("OXE 专用工具在列", "get_wafer_flow" in names and "get_chamber_status" in names)

    # ── 2. 执行固定工具 ────────────────────────────────────
    st, body = http("POST", "/api/ai/tools/get_machine_status", {}, token=token)
    check("get_machine_status 200 且含 answer", st == 200 and isinstance(body.get("answer"), str),
          f"HTTP {st} ans={(body.get('answer') or '')[:30]!r}")

    st, body = http("POST", "/api/ai/tools/get_machine_status",
                    {"machine_id": ""}, token=token)
    check("machine_id 空串可兜底不报错", st == 200, f"HTTP {st}")

    # SQL 工具（真实执行）
    st, body = http("POST", "/api/ai/tools/query_fab_data",
                    {"sql": "SELECT COUNT(*) AS cnt FROM machines"}, token=token)
    check("query_fab_data 真实执行", st == 200 and isinstance(body.get("rows"), list),
          f"HTTP {st} rows={len(body.get('rows', []))}")
    check("query_fab_data 的 sql 字段保持原样（真实执行项）",
          st == 200 and not str(body.get("sql", "")).startswith("-- 参考查询"))

    st, body = http("POST", "/api/ai/tools/describe_fab_table",
                    {"table_name": "machines"}, token=token)
    check("describe_fab_table 200", st == 200, f"HTTP {st}")

    # ── 3. SQL 安全边界（工具按设计返回 200+executed=false，把拒因回给模型改写）──
    st, body = http("POST", "/api/ai/tools/query_fab_data",
                    {"sql": "DELETE FROM machines"}, token=token)
    err1 = str(body.get("error") or "")[:40]
    check("DELETE 被拒（executed=false+error）", st == 200 and body.get("executed") is False,
          f"HTTP {st} err={err1}")

    st, body = http("POST", "/api/ai/tools/query_fab_data",
                    {"sql": "SELECT * FROM hosts"}, token=token)
    err2 = str(body.get("error") or "")[:40]
    check("非白名单表被拒（executed=false）", st == 200 and body.get("executed") is False,
          f"HTTP {st} err={err2}")

    # ── 4. 边界 ────────────────────────────────────────────
    st, body = http("POST", "/api/ai/tools/not_exist_tool", {}, token=token)
    check("未知工具 404", st == 404, f"HTTP {st}")

    req = urllib.request.Request(BACKEND + "/api/ai/tools", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            st_anon = r.status
    except urllib.error.HTTPError as e:
        st_anon = e.code
    check("未登录访问 401", st_anon == 401, f"HTTP {st_anon}")

    # ── 5. OpenAPI 规范 ────────────────────────────────────
    st, spec = http("GET", "/api/ai/tools/openapi.json", token=token)
    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
    check("openapi 3.x", st == 200 and str(spec.get("openapi", "")).startswith("3."),
          f"HTTP {st} openapi={spec.get('openapi')}")
    check("全部12个工具都有 path", len(paths) == 12, f"paths={len(paths)}")
    ok_schema = all(
        isinstance(p.get("post", {}).get("requestBody", {})
                   .get("content", {}).get("application/json", {}).get("schema"), dict)
        for p in paths.values()
    )
    check("每个 path 带参数 schema", ok_schema)
    check("带 Bearer 安全定义", "bearerAuth" in (spec.get("components", {}).get("securitySchemes", {}) or {}))
    check("servers 指向后端", bool(spec.get("servers")), f"servers={spec.get('servers')}")

    # ── 汇总 ──────────────────────────────────────────────
    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（工具桥 REST 暴露符合预期）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
