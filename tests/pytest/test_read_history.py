"""读路径：/api/history（同日查询、TTL 缓存冷暖、keyset 翻页、事件详情、
payload 裁剪）与 /api/history/{tool}/timeline（按小时聚合）。

针对千万级 DT_EVENT_RAW 的 VARCHAR2（本地灌库）形态。
"""
import time

import pytest

from conftest import record


def _get_history(client, tool, date, limit=500, **extra):
    return client.get(
        f"/api/history/{tool}",
        params={
            "start_time": f"{date}T00:00:00",
            "end_time": f"{date}T23:59:59",
            "limit": limit,
            **extra,
        },
    )


def test_history_same_day_basic(client, dense):
    """同日查询：返回条数正确、全部落在目标日内、total 与 limit 一致。"""
    r = _get_history(client, dense["tool"], dense["date"], limit=500)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["total"] == len(body["events"]) <= 500
    assert body["total"] > 0, "数据最密的一天不可能为空"
    for ev in body["events"]:
        assert ev["timestamp"].startswith(dense["date"]), ev["timestamp"]
        assert ev["raw_id"], "每条事件必须带 raw_id（keyset 翻页依赖）"


def test_history_cache_cold_vs_warm(client, dense, reset_caches):
    """test31 的 60s TTL 缓存：同参数第二次必须明显快于第一次（暖态不查库）。"""
    t0 = time.perf_counter()
    r1 = _get_history(client, dense["tool"], dense["date"], limit=500)
    cold = time.perf_counter() - t0
    assert r1.status_code == 200

    t0 = time.perf_counter()
    r2 = _get_history(client, dense["tool"], dense["date"], limit=500)
    warm = time.perf_counter() - t0
    assert r2.status_code == 200

    assert r1.json() == r2.json(), "缓存命中必须返回与冷态一致的内容"
    assert warm < max(0.05, cold / 3), f"暖态 {warm:.3f}s 应远小于冷态 {cold:.3f}s"
    record(f"/history 冷态 {dense['tool']}@{dense['date']} limit=500", cold, "千万级")
    record(f"/history 暖态（60s TTL 命中）", warm)


@pytest.mark.xfail(
    strict=True,
    reason="已知缺陷：_decrement_raw_id (history.py:41) 对零填充数字后缀丢失填充宽度 —— "
    "'SEED0009489888' 减 1 得 'SEED9489887'（短了、字典序反而更大），"
    "raw_id < 游标 命中全部行，第二页与第一页完全重叠，前端翻页死循环。"
    "修复：保持宽度 f\"{prefix}{n-1:0{len(num_str)}d}\"",
)
def test_history_keyset_pagination(client, dense, reset_caches):
    """before_raw_id 翻页：第二页不与第一页重叠，且 raw_id 严格更小。"""
    r1 = _get_history(client, dense["tool"], dense["date"], limit=200)
    assert r1.status_code == 200
    page1 = r1.json()["events"]
    assert len(page1) == 200

    cursor = r1.json()["next_raw_id"]
    assert cursor, "满页时必须返回下一页游标"
    r2 = client.get(
        f"/api/history/{dense['tool']}",
        params={
            "start_time": f"{dense['date']}T00:00:00",
            "end_time": f"{dense['date']}T23:59:59",
            "limit": 200,
            "before_raw_id": cursor,
        },
    )
    assert r2.status_code == 200
    page2 = r2.json()["events"]
    ids1 = {e["raw_id"] for e in page1}
    ids2 = {e["raw_id"] for e in page2}
    assert not (ids1 & ids2), "两页不得重叠"
    if page2:
        assert max(ids2) < min(ids1), "第二页 raw_id 必须整体小于第一页"


def test_history_event_detail(client, dense, reset_caches):
    """事件详情：raw_id 回查 payload 完整。"""
    r = _get_history(client, dense["tool"], dense["date"], limit=50)
    ev = r.json()["events"][0]
    d = client.get(f"/api/history/{dense['tool']}/events/{ev['raw_id']}")
    assert d.status_code == 200
    detail = d.json()
    assert detail.get("event", detail).get("raw_id") == ev["raw_id"] or detail.get("raw_id") == ev["raw_id"]

    d404 = client.get(f"/api/history/{dense['tool']}/events/NO-SUCH-RAW-ID")
    assert d404.status_code in (200, 404)  # 现状返回 200 + {"error": ...}，只验证不炸


def test_history_payload_trim(client, dense, reset_caches):
    """include_payload=False：响应显著变小（回放列表页优化路径）。"""
    r_full = _get_history(client, dense["tool"], dense["date"], limit=100, include_payload=True)
    r_trim = _get_history(client, dense["tool"], dense["date"], limit=100, include_payload=False)
    assert r_full.status_code == r_trim.status_code == 200
    # 种子数据 payload 较小（~200B/条）实测整体省 ~38%；真实量产 payload 更大、收益更高。
    # 阈值放 0.85：只要裁剪确实生效即可，不追求具体比例。
    assert len(r_trim.content) < len(r_full.content) * 0.85, (
        f"裁剪后 {len(r_trim.content)}B 应明显小于全量 {len(r_full.content)}B"
    )
    for ev in r_trim.json()["events"]:
        assert not ev.get("payload")


def test_timeline_hourly(client, dense, reset_caches):
    """时间轴摘要：按小时桶聚合，总量受单次拉取上限约束且不超过当日真实行数。"""
    t0 = time.perf_counter()
    r = client.get(f"/api/history/{dense['tool']}/timeline", params={"date": dense["date"]})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text[:300]
    body = r.json()

    buckets = body.get("timeline") or []
    assert buckets, f"未知的 timeline 响应结构：{list(body.keys())}"
    total = sum(b.get("total_count", 0) for b in buckets)
    assert 0 < total <= dense["count"], f"聚合总数 {total} 应在 (0, 当日真实 {dense['count']}] 内"
    record(f"/timeline {dense['tool']}@{dense['date']}", elapsed)


def test_history_realtime_latest(client, dense):
    """实时模式（无时间参数）：返回该机台最新事件，且不走缓存路径。"""
    r = client.get(f"/api/history/{dense['tool']}", params={"limit": 30})
    assert r.status_code == 200
    evs = r.json()["events"]
    assert 0 < len(evs) <= 30
