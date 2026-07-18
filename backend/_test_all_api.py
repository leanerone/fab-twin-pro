"""测试所有前端调用的API"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, "OK"
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return None, str(e)

apis = [
    "/api/machines",
    "/api/machines/PODOPENER-1",
    "/api/machines/stats",
    "/api/floors",
    "/api/models",
    "/api/lots?machine_id=PODOPENER-1&date=2026-07-18",
    "/api/alarms?machine_id=PODOPENER-1&date=2026-07-18",
    "/api/alarms/stats?machine_id=PODOPENER-1&date=2026-07-18",
    "/api/events/PODOPENER-1/latest?limit=60",
    "/api/history/PODOPENER-1?limit=60",
    "/api/history/PODOPENER-1/timeline",
    "/api/history/PODOPENER-1/alarms?limit=100",
    "/health",
]

print("API测试结果:")
for path in apis:
    code, msg = get(path)
    status = "✅" if code == 200 else "❌"
    print(f"  {status} [{code}] {path}")
