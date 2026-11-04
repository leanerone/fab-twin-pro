"""性能观测层：请求耗时 + SQL 耗时统计（性能模型的度量基础）

建立它的原因：此前所有性能结论都来自"手工 curl + 肉眼看时间"或离线报表，
既没有 P95，也无法回答"这次改动到底快了还是慢了"。性能模型必须有可复现的度量口径。

提供三件事：
1. `install(app)` —— HTTP 中间件：按路由记录耗时分布（count/p50/p95/p99/max）
2. `install_sql_timing(engine)` —— SQLAlchemy 事件钩子：记录慢查询与每请求 SQL 次数
3. `router` —— `GET /api/metrics/perf` 输出快照，`POST /api/metrics/perf/reset` 清零

设计约束：
- 统计在内存里做，不写库、不依赖 Redis，冷启动即可用
- 每个路由只保留最近 N 条样本，内存有界
- 统计本身的开销控制在微秒级，不能为了观测拖慢被观测对象
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import APIRouter

logger = logging.getLogger("fabtwin.perf")

SAMPLE_LIMIT = int(os.getenv("FABTWIN_PERF_SAMPLES", "200"))
SLOW_REQUEST_MS = float(os.getenv("FABTWIN_PERF_SLOW_MS", "1000"))
SLOW_SQL_MS = float(os.getenv("FABTWIN_PERF_SLOW_SQL_MS", "500"))
ENABLED = os.getenv("FABTWIN_PERF", "1").strip().lower() not in ("0", "false", "no")

_lock = threading.Lock()
# route -> 最近 N 条耗时样本（ms）
_samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=SAMPLE_LIMIT))
# route -> 累计计数 / 错误数 / 最近一次
_meta: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "errors": 0, "last_ms": 0.0})
# 慢查询最近 20 条
_slow_sql: Deque[Dict] = deque(maxlen=20)
# 每请求 SQL 计数（线程本地，中间件与 SQL 钩子共享）
_tls = threading.local()

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _percentile(values, pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def record(route: str, ms: float, status: int = 200) -> None:
    with _lock:
        _samples[route].append(ms)
        m = _meta[route]
        m["count"] += 1
        m["last_ms"] = ms
        if status >= 500:
            m["errors"] += 1


def snapshot() -> dict:
    with _lock:
        routes = {}
        for route, samples in _samples.items():
            vals = list(samples)
            m = _meta[route]
            routes[route] = {
                "count": int(m["count"]),
                "errors": int(m["errors"]),
                "last_ms": round(m["last_ms"], 1),
                "p50_ms": round(_percentile(vals, 0.50), 1),
                "p95_ms": round(_percentile(vals, 0.95), 1),
                "p99_ms": round(_percentile(vals, 0.99), 1),
                "max_ms": round(max(vals), 1) if vals else 0.0,
                "samples": len(vals),
            }
        return {
            "enabled": ENABLED,
            "slow_request_ms": SLOW_REQUEST_MS,
            "slow_sql_ms": SLOW_SQL_MS,
            "routes": dict(sorted(routes.items(), key=lambda kv: -kv[1]["p95_ms"])),
            "slow_sql": list(_slow_sql),
        }


def reset() -> None:
    with _lock:
        _samples.clear()
        _meta.clear()
        _slow_sql.clear()


def install(app) -> None:
    """挂载 HTTP 耗时中间件"""
    if not ENABLED:
        logger.info("[perf] 性能观测已关闭（FABTWIN_PERF=0）")
        return

    @app.middleware("http")
    async def _perf_middleware(request, call_next):
        start = time.perf_counter()
        _tls.sql_count = 0
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000.0
            route = request.scope.get("route")
            key = f"{request.method} {getattr(route, 'path', request.url.path)}"
            record(key, ms, status)
            if ms >= SLOW_REQUEST_MS:
                logger.warning(
                    "[perf] 慢请求 %s %.0fms (status=%s, sql=%d)",
                    key, ms, status, getattr(_tls, "sql_count", 0),
                )


def install_sql_timing(engine) -> None:
    """挂载 SQL 计时钩子：统计每请求 SQL 数量与慢查询"""
    if not ENABLED:
        return
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start", []).append(time.perf_counter())
        _tls.sql_count = getattr(_tls, "sql_count", 0) + 1

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        starts = conn.info.get("query_start")
        if not starts:
            return
        start = starts.pop()
        ms = (time.perf_counter() - start) * 1000.0
        if ms >= SLOW_SQL_MS:
            snippet = " ".join(statement.split())[:200]
            with _lock:
                _slow_sql.append({"sql": snippet, "ms": round(ms, 1)})
            logger.warning("[perf] 慢查询 %.0fms: %s", ms, snippet)


@router.get("/perf")
def get_perf():
    """性能快照：按 P95 倒序"""
    return snapshot()


@router.post("/perf/reset")
def reset_perf():
    reset()
    return {"ok": True}
