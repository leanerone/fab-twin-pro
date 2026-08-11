"""查看 OXE 事件 payload 实际结构"""
import sys, json
sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from models import DT_EVENT_RAW


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
# 查看不同 event_type 的事件样本
rows = db.query(DT_EVENT_RAW).filter(
    DT_EVENT_RAW.tool_id == 'OXE-61',
    DT_EVENT_RAW.parse_status == 'PARSED'
).order_by(DT_EVENT_RAW.raw_id.desc()).limit(8).all()

print('=== OXE-61 payload samples (top 8) ===')
for i, r in enumerate(rows, 1):
    p = safe_payload(r.payload_json)
    print(f'\n--- [{i}] raw_id={r.raw_id} ---')
    print(f'  received_ts_utc={r.received_ts_utc}')
    print(f'  event_ts_utc={r.event_ts_utc}')
    print(f'  payload keys: {list(p.keys())}')
    print(f'  payload: {json.dumps(p, ensure_ascii=False, indent=2)[:600]}')

db.close()
