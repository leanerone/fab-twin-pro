"""读路径：机台列表 / 统计 / 详情（derive_machines_state + 60s 缓存）与告警统计。"""
import time

from sqlalchemy import text

from conftest import record


def test_machines_list_matches_db(client, db):
    r = client.get("/api/machines")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    n_db = db.execute(text("SELECT COUNT(*) FROM MACHINES")).scalar()
    assert len(body) == n_db, f"API 返回 {len(body)} 台，库里有 {n_db} 台"
    m = body[0]
    for key in ("id", "name", "state"):
        assert key in m or any(key in str(k).lower() for k in m), f"机台字段缺失: {list(m.keys())[:12]}"


def test_machines_list_cold_vs_warm(client, reset_caches):
    t0 = time.perf_counter()
    r1 = client.get("/api/machines")
    cold = time.perf_counter() - t0
    assert r1.status_code == 200

    t0 = time.perf_counter()
    r2 = client.get("/api/machines")
    warm = time.perf_counter() - t0
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert warm <= cold, "暖态不应慢于冷态"
    record("/api/machines 冷态（57台×当日聚合）", cold, "千万级 DT_EVENT_RAW")
    record("/api/machines 暖态（60s TTL）", warm)


def test_machines_stats(client):
    r = client.get("/api/machines/stats")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert any(k in body for k in ("total", "machines", "counts")), f"未知结构: {list(body.keys())}"


def test_machine_detail_and_404(client, dense):
    r = client.get(f"/api/machines/{dense['tool']}")
    assert r.status_code == 200, r.text[:300]

    r404 = client.get("/api/machines/__NO_SUCH_MACHINE__")
    assert r404.status_code == 404, f"不存在的机台应 404，实际 {r404.status_code}"


def test_alarm_history_endpoint(client, dense, reset_caches):
    """/api/history/{tool}/alarms：结构可用（本库该日告警可能为 0，只验证不炸+形状）。"""
    r = client.get(
        f"/api/history/{dense['tool']}/alarms",
        params={
            "start_time": f"{dense['date']}T00:00:00",
            "end_time": f"{dense['date']}T23:59:59",
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert isinstance(body, (list, dict))


def test_alarms_stats_endpoint(client):
    """平台告警表统计（ALARMS 表，独立于 DT_EVENT_RAW）。"""
    r = client.get("/api/alarms/stats", params={"date": "2026-10-16"})
    assert r.status_code == 200, r.text[:300]
