"""诊断 OXE 回放问题：事件日期分布 + 时间戳格式"""
import sys, json
from collections import Counter
sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from models import DT_EVENT_RAW
from services.time_utils import parse_ts, build_date_like_patterns

db = SessionLocal()

# 1. OXE-61 事件总数 + 日期分布
rows = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == 'OXE-61').all()
print(f'=== OXE-61 总事件数: {len(rows)} ===')

dates = Counter()
ts_formats = Counter()
for r in rows:
    ts = r.event_ts_utc or r.received_ts_utc
    if not ts:
        dates['(empty)'] += 1
        continue
    dt = parse_ts(ts)
    if dt:
        dates[dt.strftime('%Y-%m-%d')] += 1
    else:
        dates['(unparseable)'] += 1
    # 记录时间戳格式样本
    if len(ts_formats) < 5:
        ts_formats[ts] += 1

print('\n日期分布:')
for d, cnt in sorted(dates.items()):
    print(f'  {d}: {cnt} 条')

print('\n时间戳样本（前5个）:')
for r in rows[:5]:
    print(f'  raw_id={r.raw_id}')
    print(f'    received_ts_utc={repr(r.received_ts_utc)}')
    print(f'    event_ts_utc={repr(r.event_ts_utc)}')
    parsed = parse_ts(r.event_ts_utc or r.received_ts_utc)
    print(f'    parsed={parsed}')

# 2. 测试 LIKE 过滤是否能匹配到数据
print('\n=== LIKE 过滤测试 ===')
test_date = '2026-08-08'  # 假设这个日期有数据
like_patterns = build_date_like_patterns(test_date)
print(f'build_date_like_patterns("{test_date}") = {like_patterns}')

if like_patterns:
    from sqlalchemy import or_
    like_conditions = []
    for p in like_patterns:
        like_conditions.append(DT_EVENT_RAW.received_ts_utc.like(p))
        like_conditions.append(DT_EVENT_RAW.event_ts_utc.like(p))
    matched = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.tool_id == 'OXE-61',
        or_(*like_conditions)
    ).all()
    print(f'LIKE 匹配到 {len(matched)} 条')

# 3. 找到有数据的日期
if dates:
    valid_dates = [d for d in dates if d.startswith('202')]
    if valid_dates:
        test_date = sorted(valid_dates)[0]
        print(f'\n用 {test_date} 测试 history 接口逻辑:')
        start = f'{test_date}T00:00:00'
        end = f'{test_date}T23:59:59.999'
        start_dt = parse_ts(start)
        end_dt = parse_ts(end)
        print(f'  start_dt={start_dt}, end_dt={end_dt}')
        print(f'  same day: {start_dt.date() == end_dt.date()}')

        # 模拟 get_history 的 LIKE 查询
        like_patterns2 = build_date_like_patterns(test_date)
        print(f'  like_patterns={like_patterns2}')
        if like_patterns2:
            like_conditions2 = []
            for p in like_patterns2:
                like_conditions2.append(DT_EVENT_RAW.received_ts_utc.like(p))
                like_conditions2.append(DT_EVENT_RAW.event_ts_utc.like(p))
            matched2 = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.tool_id == 'OXE-61',
                or_(*like_conditions2)
            ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(2000).all()
            print(f'  LIKE 匹配 {len(matched2)} 条')

            # Python 层过滤
            filtered = []
            for r in matched2:
                ts = r.event_ts_utc or r.received_ts_utc
                from services.time_utils import normalize_ts
                norm_ts = normalize_ts(ts)
                ev_dt = parse_ts(norm_ts)
                if not ev_dt:
                    continue
                if ev_dt < start_dt or ev_dt > end_dt:
                    continue
                filtered.append(r)
            print(f'  Python 层过滤后: {len(filtered)} 条')

db.close()
