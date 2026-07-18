import urllib.request
import json

url = 'http://localhost:8002/api/history/PODOPENER-1?limit=10'
resp = urllib.request.urlopen(url)
data = json.loads(resp.read())
events = data.get('events', [])
print(f'事件数: {len(events)}')
for i, e in enumerate(events):
    print(f'\n--- 事件 {i+1} ---')
    print(f'  event_name: {e.get("event_name")}')
    print(f'  tool_id: {e.get("tool_id")}')
    print(f'  timestamp: {e.get("timestamp")}')
    print(f'  event_ts_utc: {e.get("event_ts_utc")}')
    payload = e.get('payload_json')
    if payload:
        if isinstance(payload, str):
            try:
                p = json.loads(payload)
                print(f'  payload.event_name: {p.get("event_name")}')
                print(f'  payload.event_type: {p.get("event_type")}')
            except:
                pass
        elif isinstance(payload, dict):
            print(f'  payload.event_name: {payload.get("event_name")}')
            print(f'  payload.event_type: {payload.get("event_type")}')
    print(f'  keys: {list(e.keys())}')
