"""OXE 事件类型分布统计（仅供测试）"""
import sys, json
sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from models import DT_EVENT_RAW
from collections import Counter


def safe_payload(p):
    if p is None:
        return {}
    if hasattr(p, 'read'):
        p = p.read()
    if isinstance(p, str):
        try:
            return json.loads(p)
        except Exception:
            return {'_raw': p[:200]}
    return {}


db = SessionLocal()
rows = db.query(DT_EVENT_RAW).filter(
    DT_EVENT_RAW.tool_id.like('OXE%'),
    DT_EVENT_RAW.parse_status == 'PARSED'
).all()

cnt = Counter()
for r in rows:
    p = safe_payload(r.payload_json)
    n = str(p.get('event_name', '')).upper()
    cnt[n] += 1

print(f'Total OXE PARSED events: {len(rows)}')
print('Event name distribution (OXE):')
for k, v in cnt.most_common():
    print(f'  {k or "(empty)"}: {v}')

# OXE-61 单独统计
rows61 = db.query(DT_EVENT_RAW).filter(
    DT_EVENT_RAW.tool_id == 'OXE-61',
    DT_EVENT_RAW.parse_status == 'PARSED'
).all()
c61 = Counter()
for r in rows61:
    p = safe_payload(r.payload_json)
    n = str(p.get('event_name', '')).upper()
    c61[n] += 1
print(f'\nOXE-61 events: {len(rows61)}')
for k, v in c61.most_common():
    print(f'  {k or "(empty)"}: {v}')

# 检查 OXE-51 是否有 POD_PLACED 等关键事件
rows51 = db.query(DT_EVENT_RAW).filter(
    DT_EVENT_RAW.tool_id == 'OXE-51',
    DT_EVENT_RAW.parse_status == 'PARSED'
).all()
c51 = Counter()
for r in rows51:
    p = safe_payload(r.payload_json)
    n = str(p.get('event_name', '')).upper()
    c51[n] += 1
print(f'\nOXE-51 events: {len(rows51)}')
for k, v in c51.most_common():
    print(f'  {k or "(empty)"}: {v}')

db.close()
