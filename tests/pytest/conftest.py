"""数据读写测试公共夹具。

针对本地千万级 DT_EVENT_RAW（Oracle 19c, ORCLPDB）做真实读写测试：
- client：session 级 TestClient（startup 会跑 init_db + db_poller，poller 保持运行供 WS 端到端用）
- db：函数级 SQLAlchemy 会话（直接查库断言）
- clean_test_rows：autouse，清理本套件写入的测试行（tool_id LIKE 'TEST-RW-%' / raw_id LIKE 'TIDZ.TEST%'）
- reset_caches：清空 history/timeline/machine_state/kpi 的 TTL 缓存，保证冷态计时
- dense：自动挑选数据最密的 tool+date 组合（默认 PODOPENER-5@2026-10-16，查不到再全表聚合兜底）
- PERF：性能计时收集，会话结束写 .perf_report.json 并打印

注意 raw_id 前缀约定：测试写入用 TIDZ. 前缀 —— 字符串排序在 TID. 之上，
保证 db_poller 的「最新 100 行」窗口（raw_id desc）一定能看到测试行。
"""
import json
import sys
import threading
import time
import queue
from datetime import datetime
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import config  # noqa: E402

# 读写测试不需要模拟器噪音；db_poller 保持默认开启（WS 端到端依赖它）
assert config.SIMULATION_ENABLED is False, "SIMULATION_ENABLED 必须为 False"

from main import app as fastapi_app  # noqa: E402
from database import SessionLocal  # noqa: E402
from routers.history import _history_ttl, _timeline_ttl  # noqa: E402
from services.cache import machine_state_ttl, kpi_stats_ttl  # noqa: E402

TEST_TOOL_PREFIX = "TEST-RW-"
TEST_RAW_PREFIX = "TIDZ.TEST."

PERF = {}
_REPORT_PATH = Path(__file__).parent / ".perf_report.json"


def record(name: str, seconds: float, note: str = ""):
    PERF[name] = {"seconds": round(seconds, 3), "note": note}


@pytest.fixture(scope="session", autouse=True)
def _perf_report():
    yield
    # 合并历史记录：定向 -k 重跑不丢全量跑的数字
    merged = {}
    if _REPORT_PATH.exists():
        try:
            merged.update(json.loads(_REPORT_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    merged.update(PERF)
    _REPORT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== 性能计时汇总（已写入 %s）=====" % _REPORT_PATH.name)
    for name, item in sorted(merged.items(), key=lambda kv: -kv[1]["seconds"]):
        print("  %8.3fs  %s%s" % (item["seconds"], name, ("  # " + item["note"]) if item["note"] else ""))


@pytest.fixture(scope="session")
def client():
    # raise_server_exceptions=False：让 500（如 raw_id 主键冲突）以响应形式返回，
    # 测试可以断言真实状态码，而不是测试进程直接抛异常
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
        s.rollback()
    finally:
        s.close()


def _cleanup_test_rows(session):
    for table in ("DT_EVENT_RAW", "DT_EVENT_RAW_CUR"):
        session.execute(
            text(f"DELETE FROM {table} WHERE tool_id LIKE :p OR raw_id LIKE :r"),
            {"p": TEST_TOOL_PREFIX + "%", "r": TEST_RAW_PREFIX + "%"},
        )
    session.commit()


@pytest.fixture(autouse=True)
def clean_test_rows(db):
    _cleanup_test_rows(db)
    yield
    _cleanup_test_rows(db)


@pytest.fixture()
def reset_caches():
    _history_ttl.invalidate()
    _timeline_ttl.invalidate()
    machine_state_ttl.invalidate()
    kpi_stats_ttl.invalidate()
    yield


@pytest.fixture(scope="session")
def dense():
    """挑选数据最密的 (tool_id, date, count)。优先用已知组合（索引查询，秒回），
    查不到再退回全表 GROUP BY（千万行，一次性成本可接受）。"""
    s = SessionLocal()
    try:
        tool, date = "PODOPENER-5", "2026-10-16"
        cnt = s.execute(
            text("SELECT COUNT(*) FROM DT_EVENT_RAW WHERE tool_id = :t AND received_ts_utc LIKE :d"),
            {"t": tool, "d": date + "%"},
        ).scalar() or 0
        if cnt == 0:
            row = s.execute(
                text(
                    "SELECT tool_id, SUBSTR(received_ts_utc,1,10) d, COUNT(*) c "
                    "FROM DT_EVENT_RAW GROUP BY tool_id, SUBSTR(received_ts_utc,1,10) "
                    "ORDER BY c DESC FETCH FIRST 1 ROWS ONLY"
                )
            ).fetchone()
            tool, date, cnt = row[0], row[1], row[2]
        return {"tool": tool, "date": date, "count": cnt}
    finally:
        s.close()


class WsReader:
    """带超时的 WS 消息读取器：daemon 线程阻塞收，主线程按 deadline 消费。"""

    def __init__(self, ws):
        self.ws = ws
        self.q = queue.Queue()
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while True:
            try:
                self.q.put(self.ws.receive_json())
            except Exception as e:  # 连接关闭等
                self.q.put({"__closed__": str(e)})
                return

    def next(self, timeout=2.0):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


def make_rv_payload(tool_id: str, event_name: str = "POD_PLACED", lot_id: str = "TESTLOT-K9") -> str:
    return json.dumps(
        {
            "tool_id": tool_id,
            "msg_id": "TID.TEST",
            "lot_id": lot_id,
            "event_type": "HOST",
            "event_name": event_name,
            "event_value": event_name,
            "machine_state": event_name,
            "machine_mode": "PACKING",
            "alarm_code": "",
        },
        ensure_ascii=False,
    )


def now_iso() -> str:
    return datetime.now().isoformat()
