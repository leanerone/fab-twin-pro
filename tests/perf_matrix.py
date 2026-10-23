# -*- coding: utf-8 -*-
"""千万级性能矩阵：全端点冷/暖态耗时直测。

注意：urllib 在 Windows 下即使禁代理也有 ~2s/请求的固定客户端噪声，
本脚本用于横向对比与回归；**权威计时请用 curl.exe 直测**，如：
  curl.exe -s -o NUL -w "time=%{time_total}s" http://localhost:8002/api/machines

环境变量：FAB_BASE（默认 http://localhost:8002）、FAB_TOOL（默认 OXE-51）。
结果写本目录 perf_matrix.json。
"""
import urllib.request, urllib.error, json, time, datetime, os

BASE = os.getenv("FAB_BASE", "http://localhost:8002")
TOOL = os.getenv("FAB_TOOL", "OXE-51")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perf_matrix.json")
# 禁代理，消除环境噪声
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

today = datetime.date.today().strftime("%Y-%m-%d")
d1 = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
d7 = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

CASES = [
    ("machines_cold",  f"{BASE}/api/machines", True, 2),
    ("machines_warm",  f"{BASE}/api/machines", False, 3),
    ("machine_stats",  f"{BASE}/api/machines/stats", False, 3),
    ("floors",         f"{BASE}/api/floors", False, 3),
    ("machine_detail", f"{BASE}/api/machines/{TOOL}", False, 3),
    ("hist_realtime",  f"{BASE}/api/history/{TOOL}?limit=200", False, 3),
    ("hist_today",     f"{BASE}/api/history/{TOOL}?start_time={today}T00:00:00&end_time={today}T23:59:59&limit=500", False, 3),
    ("hist_crossday",  f"{BASE}/api/history/{TOOL}?start_time={d1}T00:00:00&end_time={today}T23:59:59&limit=2000", False, 3),
    ("hist_7day",      f"{BASE}/api/history/{TOOL}?start_time={d7}T00:00:00&end_time={today}T23:59:59&limit=2000", False, 3),
    ("events_page",    f"{BASE}/api/events/{TOOL}?page=1&page_size=20", False, 3),
    ("alarms",         f"{BASE}/api/alarms?limit=100", False, 3),
]

def hit(url):
    t0 = time.time()
    try:
        with opener.open(url, timeout=300) as r:
            data = r.read()
            return r.status, (time.time() - t0) * 1000, len(data)
    except urllib.error.HTTPError as e:
        return e.code, (time.time() - t0) * 1000, 0
    except Exception as e:
        return -1, (time.time() - t0) * 1000, str(e)[:100]

results = {}
for name, url, cold, n in CASES:
    times, codes, size = [], [], 0
    for i in range(n):
        if cold:
            time.sleep(62)  # 等 machine_state 缓存(60s)过期
        code, ms, info = hit(url)
        codes.append(code)
        if code == 200:
            times.append(ms)
            size = info
        else:
            size = info
    avg = sum(times) / len(times) if times else -1
    results[name] = {"codes": codes, "avg_ms": round(avg, 1),
                     "min_ms": round(min(times), 1) if times else -1,
                     "max_ms": round(max(times), 1) if times else -1,
                     "resp_bytes": size if isinstance(size, int) else 0,
                     "note": "" if isinstance(size, int) else size}
    print(f"{name}: avg={avg:.0f}ms codes={codes}", flush=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print(f"MATRIX_DONE -> {OUT}")
