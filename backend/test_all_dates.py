"""验证OXE-61所有9天历史数据(8-6至8-14)API返回正常"""
import requests

DATES = ['2026-08-06', '2026-08-07', '2026-08-08', '2026-08-09', '2026-08-10',
         '2026-08-11', '2026-08-12', '2026-08-13', '2026-08-14']

print('=== OXE-61 所有日期历史数据验证 ===')
total_events = 0
for d in DATES:
    try:
        r = requests.get('http://localhost:8002/api/history/OXE-61',
                         params={'start_time': f'{d}T00:00:00',
                                 'end_time': f'{d}T23:59:59.999',
                                 'limit': 5000},
                         timeout=5)
        data = r.json()
        events = data.get('events', [])
        count = len(events)
        total_events += count
        first_ev = events[0] if events else {}
        last_ev = events[-1] if events else {}
        print(f'{d}: status={r.status_code} count={count} '
              f'first_ts={first_ev.get("timestamp","N/A")} first_name={first_ev.get("event_name","N/A")} '
              f'last_ts={last_ev.get("timestamp","N/A")} last_name={last_ev.get("event_name","N/A")}')
    except Exception as e:
        print(f'{d}: ERROR: {e}')

print(f'\n=== 总计事件数: {total_events} ===')
