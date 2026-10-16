# P1 一次性同步脚本：把 models/user/amat_metsput_v1.1.json 写入 Oracle machine_model_configs.animation_config_json
# 用法：在 backend 目录运行  python ../scripts/sync_amat_motion_to_db.py
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import text
from database import engine

SRC = os.path.join(os.path.dirname(__file__), '..', 'models', 'user', 'amat_metsput_v1.1.json')

with open(SRC, 'r', encoding='utf-8') as f:
    payload = json.load(f)

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT model_id, model_name, version, LENGTH(animation_config_json) "
        "FROM machine_model_configs WHERE UPPER(model_id) LIKE '%METSPUT%' OR UPPER(model_name) LIKE '%METSPUT%'"
    )).fetchall()
    print('[INFO] 命中记录:')
    for r in rows:
        print('   ', r)
    if not rows:
        print('[ERROR] 未找到 AMAT-METSPUT 记录，终止')
        sys.exit(1)

    target = rows[0][0]
    if len(rows) > 1:
        # 取版本号最大的
        target = sorted(rows, key=lambda r: str(r[2]))[-1][0]
        print(f'[WARN] 多条记录，取 version 最大: {target}')

    conn.execute(text(
        "UPDATE machine_model_configs SET animation_config_json = :cfg, updated_at = :ts WHERE model_id = :mid"
    ), {
        'cfg': json.dumps(payload, ensure_ascii=False),
        'ts': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'mid': target,
    })
    conn.commit()

    n = conn.execute(text(
        "SELECT LENGTH(animation_config_json) FROM machine_model_configs WHERE model_id = :mid"
    ), {'mid': target}).fetchone()[0]
    print(f'[OK] 已更新 {target}, animation_config_json 长度 = {n}')
