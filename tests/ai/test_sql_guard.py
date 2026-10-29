# -*- coding: utf-8 -*-
"""ai_sql 安全围栏单测——不连数据库，纯语法层「红队」验证。

运行：cd backend && python ../tests/ai/test_sql_guard.py
退出码 0 = 全部符合预期（该放行的放行，该拦的拦住）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

from services.ai_sql import SqlSafetyError, validate_and_normalize, check_tables  # noqa: E402

# (用例名, SQL, 期望: "pass"=应放行 / "block"=应拦截)
CASES = [
    ("基础查询", "SELECT * FROM machines", "pass"),
    ("带 schema 前缀", "SELECT * FROM fabtwin.machines", "pass"),
    ("聚合统计", "SELECT COUNT(*) AS cnt FROM dt_event_raw WHERE tool_id='RTM01-OXE-01'", "pass"),
    ("JOIN 白名单表", "SELECT m.id, e.event_name FROM machines m JOIN dt_event_raw e ON m.id=e.tool_id", "pass"),
    ("CTE 分层查询", "WITH recent AS (SELECT * FROM dt_event_raw) SELECT * FROM recent", "pass"),
    ("多 CTE", "WITH a AS (SELECT * FROM machines), b AS (SELECT * FROM lots) SELECT * FROM a, b", "pass"),
    ("LIMIT 方言改写", "SELECT * FROM machines LIMIT 10", "pass"),
    ("已有 FETCH FIRST", "SELECT * FROM machines FETCH FIRST 5 ROWS ONLY", "pass"),
    ("字符串时间过滤", "SELECT COUNT(*) FROM dt_event_raw WHERE received_ts_utc >= '2026-10-29T00:00:00'", "pass"),

    ("DELETE", "DELETE FROM machines WHERE 1=1", "block"),
    ("DROP", "DROP TABLE machines", "block"),
    ("UPDATE", "UPDATE machines SET status='DOWN'", "block"),
    ("INSERT", "INSERT INTO machines (id) VALUES ('x')", "block"),
    ("TRUNCATE", "TRUNCATE TABLE dt_event_raw", "block"),
    ("GRANT", "GRANT SELECT ON machines TO public", "block"),
    ("越权表 users", "SELECT * FROM users", "block"),
    ("越权表含密钥", "SELECT * FROM ai_provider_configs", "block"),
    ("逗号写法绕过", "SELECT * FROM machines, users WHERE machines.id=users.id", "block"),
    ("多语句注入", "SELECT * FROM machines; DROP TABLE machines", "block"),
    ("UNION 拖库", "SELECT id FROM machines UNION SELECT username FROM users", "block"),
    ("注释藏写操作", "SELECT * FROM machines /* DELETE FROM machines */", "block"),
    ("行注释拼接", "SELECT * FROM machines WHERE 1=1 -- \n DELETE FROM machines", "block"),
    ("CTE 夹带越权表", "WITH x AS (SELECT * FROM users) SELECT * FROM x", "block"),
    ("FROM 后无表", "SELECT 1", "block"),
    ("空语句", "", "block"),
    ("纯注释", "-- nothing here", "block"),
]

def main() -> int:
    failed = []
    print("=" * 72)
    print("ai_sql 安全围栏测试")
    print("=" * 72)
    for name, sql, expect in CASES:
        try:
            out = validate_and_normalize(sql)
            actual = "pass"
            detail = out if len(out) < 110 else out[:107] + "..."
        except SqlSafetyError as exc:
            actual = "block"
            detail = str(exc)[:110]
        ok = actual == expect
        mark = "OK " if ok else "FAIL"
        print(f"  [{mark}] {name:<16} 期望={expect:<5} 实际={actual:<5} | {detail}")
        if not ok:
            failed.append(name)

    print("-" * 72)
    # 额外：方言改写断言
    checks = []
    s = validate_and_normalize("SELECT * FROM machines LIMIT 10")
    checks.append(("LIMIT→FETCH 改写", "FETCH FIRST 10 ROWS ONLY" in s, s))
    s = validate_and_normalize("SELECT * FROM machines")
    checks.append(("ROWNUM 围栏注入", s.startswith("SELECT * FROM (") and "ROWNUM <= 200" in s, s))
    s = validate_and_normalize("WITH t AS (SELECT * FROM machines) SELECT * FROM t")
    checks.append(("CTE 不被包裹", s.upper().startswith("WITH T AS"), s))
    for name, ok, detail in checks:
        print(f"  [{'OK ' if ok else 'FAIL'}] {name:<16} | {detail[:100]}")
        if not ok:
            failed.append(name)

    print("=" * 72)
    if failed:
        print(f"结果：{len(failed)} 项未达预期 -> {failed}")
        return 1
    print(f"结果：{len(CASES) + len(checks)} 项全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
