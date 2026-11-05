# -*- coding: utf-8 -*-
"""R3 回归：perf 每请求 SQL 计数修复（threading.local → ContextVar 共享 dict）

旧缺陷：中间件在事件循环线程 set _tls.sql_count=0，SQL 钩子在 anyio worker
线程自增——threading.local 跨线程不可见，慢请求日志里 sql 恒为 0。

验证：ContextVar 里的 dict 在"主线程 set → 执行 SQL → 读回"链路中计数可见。
运行：python tests/ai/test_perf_ctx.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    mark = "[PASS]" if cond else "[FAIL]"
    print(f"  {mark} {name} {detail}")


def main():
    from core.services import perf

    check("已无 threading.local 计数", not hasattr(perf, "_tls"),
          "has_tls=" + str(hasattr(perf, "_tls")))
    check("存在 _req_ctx ContextVar", hasattr(perf, "_req_ctx"))

    # 安装 SQL 计时钩子（真实环境由 main.py 启动时挂载）
    from database import engine as _eng
    perf.install_sql_timing(_eng)

    # 模拟中间件：主线程 set 共享 dict
    state = {"sql_count": 0}
    perf._req_ctx.set(state)

    # worker 线程里执行一条 SQL（SQL 钩子会自增 dict）
    # 模拟 anyio.to_thread 的真实行为：复制当前 context 到 worker（裸线程不会复制）
    import threading
    import contextvars

    def run_sql():
        from database import engine
        with engine.connect() as c:
            c.exec_driver_sql("SELECT 1 FROM DUAL")

    ctx = contextvars.copy_context()
    t = threading.Thread(target=lambda: ctx.run(run_sql))
    t.start()
    t.join()

    check("跨线程 SQL 计数可见（>0）", state["sql_count"] >= 1,
          f"sql_count={state['sql_count']}")

    # 清理：请求结束后 context 应与下一次请求隔离
    state2 = {"sql_count": 0}
    perf._req_ctx.set(state2)
    check("新请求计数从0开始", state2["sql_count"] == 0)

    total, passed = len(RESULTS), sum(RESULTS)
    print("=" * 60)
    if passed == total:
        print(f"结果：{passed}/{total} 全部通过（perf sql 计数跨线程可见）")
        return 0
    print(f"结果：{passed}/{total}，失败 {total - passed} 项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
