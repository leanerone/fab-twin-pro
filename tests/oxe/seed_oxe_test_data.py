"""为测试DB补充OXE-61多日期模拟事件数据

插入4个日期（08-08 ~ 08-11）的完整RV事件流程：
POD_PLACED -> LOCK_PORT_COMPLETED -> MVIN -> DOOR_OPEN -> LOAD_CYCLE_STARTED
-> WAFER_LOADED -> Start -> PS -> PE -> WAFER_UNLOADED -> DOOR_CLOSE -> POD_REMOVED

每日期约25片晶圆流程，确保 history 接口和 oxe.html 回放均能验证。
"""
import sys
import json
import random
from datetime import datetime, timedelta

sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from models import DT_EVENT_RAW

TOOL_ID = 'OXE-61'
# 4个日期，每个日期生成1个完整Lot流程
TEST_DATES = ['2026-08-08', '2026-08-09', '2026-08-10', '2026-08-11']
LOT_IDS = ['TEST0801', 'TEST0802', 'TEST0901', 'TEST1001']
RECIPES = ['X4854', 'X4855', 'X4856', 'X4857']


def build_event(raw_id, tool_id, ts, event_name, lot_id, recipe, port, **extra):
    """构造一条 DT_EVENT_RAW 事件"""
    payload = {
        'event_name': event_name,
        'event_type': 'VFEI',
        'lot_id': lot_id,
        'recipe': recipe,
        'port': str(port),
        'machine_state': 'Running',
    }
    payload.update(extra)
    return DT_EVENT_RAW(
        raw_id=raw_id,
        tool_id=tool_id,
        source_system='SEED_SCRIPT',
        source_message_id=f'SEED-{raw_id}',
        received_ts_utc=ts,
        event_ts_utc=ts,
        payload_json=json.dumps(payload, ensure_ascii=False),
        parse_status='PARSED',
        error_message=None,
    )


def generate_lot_events(base_date, lot_id, recipe, port, start_raw_seq):
    """生成一个Lot的完整事件流程（精简版，约30条事件）"""
    events = []
    seq = start_raw_seq
    base_dt = datetime.strptime(base_date, '%Y-%m-%d')

    def ts(minutes):
        return (base_dt + timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%S')

    def rid():
        nonlocal seq
        seq += 1
        return f'RAW_SEED_{seq}'

    smif = f'SMIF{port}'
    chamber = 'CHAMBER_B' if port == 2 else 'CHAMBER_A'

    # POD流程
    events.append(build_event(rid(), TOOL_ID, ts(0), 'POD_PLACED', lot_id, recipe, port, smif_id=smif, cst_id=f'CST{lot_id}'))
    events.append(build_event(rid(), TOOL_ID, ts(1), 'LOCK_PORT_COMPLETED', lot_id, recipe, port, smif_id=smif))
    events.append(build_event(rid(), TOOL_ID, ts(3), 'MVIN', lot_id, recipe, port, smif_id=smif))
    events.append(build_event(rid(), TOOL_ID, ts(5), 'DOOR_OPEN', lot_id, recipe, port, smif_id=smif))
    events.append(build_event(rid(), TOOL_ID, ts(6), 'LOAD_CYCLE_STARTED', lot_id, recipe, port, smif_id=smif, duration_sec=60))

    # 3片晶圆的完整流程（简化，每片约20分钟）
    for wafer_id in range(1, 4):
        w_min = 10 + (wafer_id - 1) * 20
        events.append(build_event(rid(), TOOL_ID, ts(w_min), 'WaferLoaded', lot_id, recipe, port,
                                   port_id=f'PORT{port}', chamber_id=chamber, wafer_id=wafer_id, slot=wafer_id, duration_sec=6))
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 1), 'Start', lot_id, recipe, port, chamber_id=chamber, duration_sec=1))
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 2), 'PS', lot_id, recipe, port, chamber_id=chamber, duration_sec=1))
        # 添加 STATE 事件用于测试状态映射
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 3), 'STATE', lot_id, recipe, port,
                                   chamber_id=chamber, state='RUNNING', machine_state='Running', description=f'{chamber} 加工中'))
        # 添加 SENSOR 事件用于测试传感器映射
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 5), 'SENSOR', lot_id, recipe, port,
                                   chamber_id=chamber, sensor_name='Temperature', sensor_value=85.5 + wafer_id * 0.3, description='腔体温度'))
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 10), 'PE', lot_id, recipe, port, chamber_id=chamber, duration_sec=1))
        events.append(build_event(rid(), TOOL_ID, ts(w_min + 12), 'WaferUnloaded', lot_id, recipe, port,
                                   port_id=f'PORT{port}', chamber_id=chamber, wafer_id=wafer_id, slot=wafer_id, duration_sec=5))

    # 添加1条 ALARM 事件
    events.append(build_event(rid(), TOOL_ID, ts(75), 'EC_ALARM_REPORT', lot_id, recipe, port,
                               chamber_id=chamber, alarm_id='9003', alarm_text='Chamber temperature drift', severity='warn'))

    # 添加1条 TRANSFER 事件
    events.append(build_event(rid(), TOOL_ID, ts(76), 'TRANSFER', lot_id, recipe, port,
                               chamber_id=chamber, transfer_stage='PLACE', action='PLACE', description='晶圆传输完成'))

    # 结束流程
    events.append(build_event(rid(), TOOL_ID, ts(80), 'LOAD_CYCLE_COMPLETED', lot_id, recipe, port, smif_id=smif, duration_sec=1))
    events.append(build_event(rid(), TOOL_ID, ts(82), 'DOOR_CLOSE', lot_id, recipe, port, smif_id=smif))
    events.append(build_event(rid(), TOOL_ID, ts(85), 'POD_REMOVED', lot_id, recipe, port, smif_id=smif))

    return events, seq


def main():
    db = SessionLocal()
    try:
        # 先清理旧的 SEED 数据
        deleted = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.source_system == 'SEED_SCRIPT').delete()
        print(f'清理旧SEED数据: {deleted} 条')

        all_events = []
        seq = 100000
        for i, date in enumerate(TEST_DATES):
            port = (i % 2) + 1  # 交替使用 PORT1/PORT2
            events, seq = generate_lot_events(date, LOT_IDS[i], RECIPES[i], port, seq)
            all_events.extend(events)
            print(f'{date} PORT{port} {LOT_IDS[i]}: 生成 {len(events)} 条事件')

        # 批量插入
        db.bulk_save_objects(all_events)
        db.commit()
        print(f'\n总计插入: {len(all_events)} 条事件')

        # 验证：按日期统计
        from sqlalchemy import func
        for date in TEST_DATES:
            like_pattern = f'{date}T%'
            cnt = db.query(func.count(DT_EVENT_RAW.raw_id)).filter(
                DT_EVENT_RAW.tool_id == TOOL_ID,
                DT_EVENT_RAW.event_ts_utc.like(like_pattern)
            ).scalar()
            print(f'  {date}: {cnt} 条')

        # 验证：事件类型分布
        rows = db.query(DT_EVENT_RAW).filter(
            DT_EVENT_RAW.tool_id == TOOL_ID,
            DT_EVENT_RAW.source_system == 'SEED_SCRIPT'
        ).all()
        from collections import Counter
        cnt = Counter()
        for r in rows:
            try:
                p = json.loads(r.payload_json)
                cnt[p.get('event_name', '')] += 1
            except Exception:
                cnt['PARSE_ERR'] += 1
        print(f'\n事件类型分布:')
        for k, v in cnt.most_common():
            print(f'  {k}: {v}')

    except Exception as e:
        db.rollback()
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    main()
