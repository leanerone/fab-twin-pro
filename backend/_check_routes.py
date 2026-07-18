"""检查路由和lot数据"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except Exception as e:
        return None, str(e)

# 1. 获取OpenAPI规范，看所有路由
print("=== 1. 所有API路由 ===")
code, data = get("/openapi.json")
if code == 200:
    paths = data.get("paths", {})
    for path in sorted(paths.keys()):
        methods = list(paths[path].keys())
        print(f"  {methods} {path}")

# 2. 检查lot详情
print("\n=== 2. Lot详情 ===")
code, data = get("/api/lots?limit=5")
if isinstance(data, list):
    for lot in data[:3]:
        print(f"  Lot: {json.dumps(lot, ensure_ascii=False)}")

# 3. 检查PODOPENER-1的lot（用正确字段名）
print("\n=== 3. PODOPENER-1的Lot (machine_id过滤) ===")
code, data = get("/api/lots?machine_id=PODOPENER-1&limit=10")
if isinstance(data, list):
    print(f"数量: {len(data)}")
    for lot in data[:5]:
        print(f"  {json.dumps(lot, ensure_ascii=False)}")
else:
    print(f"返回: {data}")

# 4. 检查历史事件中的lot_id字段
print("\n=== 4. 历史事件中的lot_id ===")
code, data = get("/api/history/PODOPENER-1?limit=20")
if code == 200:
    for e in data.get("events", [])[:20]:
        print(f"  {e['event_name']:30s} lot_id={e.get('lot_id'):10s} cassette={e.get('cassette_id')}")

# 5. 直接查DB中PODOPENER-1的lot
print("\n=== 5. DB中PODOPENER-1的Lot ===")
from database import engine
from sqlalchemy import text
with engine.connect() as conn:
    r = conn.execute(text("SELECT * FROM LOTS WHERE MACHINE_ID = 'PODOPENER-1' AND ROWNUM <= 5"))
    rows = r.fetchall()
    print(f"DB中PODOPENER-1的Lot数量: {len(rows)}")
    if rows:
        cols = [d[0].lower() for d in r.cursor.description]
        print(f"列名: {cols}")
        for row in rows:
            print(f"  {dict(zip(cols, row))}")
    else:
        print("  没有PODOPENER-1的Lot记录")
        # 检查所有lot的machine_id
        r2 = conn.execute(text("SELECT DISTINCT MACHINE_ID FROM LOTS WHERE ROWNUM <= 20"))
        print("  DB中Lot的MACHINE_ID列表:")
        for row in r2:
            print(f"    {row[0]}")
