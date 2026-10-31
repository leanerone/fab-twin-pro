import requests
try:
    r = requests.get('http://localhost:8000/api/history/OXE-61',
                     params={'start_time': '2026-08-08T00:00:00',
                             'end_time': '2026-08-08T23:59:59.999',
                             'limit': 5000},
                     timeout=5)
    print(f'status={r.status_code}')
    data = r.json()
    print(f'total={data.get("total")} events={len(data.get("events", []))}')
    if data.get('events'):
        ev = data['events'][0]
        print(f'first: ts={ev["timestamp"]} name={ev["event_name"]}')
        print(f'  payload keys: {list(ev.get("payload", {}).keys())[:10]}')
        print(f'  slot in payload: {ev.get("payload", {}).get("slot")}')
except Exception as e:
    print(f'ERROR: {e}')
