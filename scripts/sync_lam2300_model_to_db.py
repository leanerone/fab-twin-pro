# -*- coding: utf-8 -*-
"""LAM2300 接线入库一次性脚本（照 sync_amat_motion_to_db.py 模式）：

1. models/user/lam2300-topview.svg → backend/uploads/models/（前端经 /uploads/models/ 访问）
2. upsert machine_model_configs：model_id='LAM2300'，views_config_json 挂 2D SVG、
   animation_config_json 写入 lam2300-topview.motion.json
3. 确保存在机台行 LAM2300-1（model='LAM2300'）——前端按 machines.model 解析模型配置，
   /api/debug/event 注入也要求机台存在

用法：在仓库根目录运行  python scripts/sync_lam2300_model_to_db.py
"""
import json
import os
import sys
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

from sqlalchemy import text  # noqa: E402
from database import engine  # noqa: E402

MODEL_ID = "LAM2300"
SVG_SRC = os.path.join(_ROOT, "models", "user", "lam2300-topview.svg")
MOTION_SRC = os.path.join(_ROOT, "models", "user", "lam2300-topview.motion.json")
SVG_DST = os.path.join(_ROOT, "backend", "uploads", "models", "lam2300-topview.svg")
SVG_URL = "/uploads/models/lam2300-topview.svg"

VIEWS_CONFIG = {
    "view_3d": {
        "type": "threejs",
        "model_source": "procedural",
        "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]},
    },
    "view_2d": {
        "type": "motion2d",
        "svg_source": SVG_URL,
        "view_label": "LAM 2300 顶视图",
    },
}


def main() -> int:
    with open(MOTION_SRC, "r", encoding="utf-8") as f:
        motion = json.load(f)
    with open(SVG_SRC, "r", encoding="utf-8") as f:
        svg_text = f.read()

    os.makedirs(os.path.dirname(SVG_DST), exist_ok=True)
    with open(SVG_DST, "w", encoding="utf-8") as f:
        f.write(svg_text)
    print(f"[OK] SVG 已同步: {SVG_DST} ({len(svg_text)} chars)")

    views_json = json.dumps(VIEWS_CONFIG, ensure_ascii=False)
    anim_json = json.dumps(motion, ensure_ascii=False)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    with engine.connect() as conn:
        conn.execute(text(
            "MERGE INTO machine_model_configs t USING (SELECT :mid AS model_id FROM dual) s ON (t.model_id = s.model_id) "
            "WHEN MATCHED THEN UPDATE SET t.model_name = :mname, t.vendor = :vendor, t.process_type = :ptype, "
            "  t.version = :ver, t.view_mode = :vmode, t.views_config_json = :vjson, "
            "  t.animation_config_json = :ajson, t.updated_at = :ts "
            "WHEN NOT MATCHED THEN INSERT (model_id, model_name, vendor, process_type, version, view_mode, "
            "  description, views_config_json, animation_config_json, created_at, updated_at) "
            "VALUES (:mid, :mname, :vendor, :ptype, :ver, :vmode, :desc, :vjson, :ajson, :ts, :ts)"
        ), {
            "mid": MODEL_ID, "mname": "LAM 2300 刻蚀台", "vendor": "LAM",
            "ptype": "ETCH", "ver": "1.0", "vmode": "motion2d",
            "desc": "LAM 2300 cluster 顶视图（ATM/2xAirlock/VTM/4xPM，motion2d 统一管线）",
            "vjson": views_json, "ajson": anim_json, "ts": now,
        })

        row = conn.execute(text(
            "SELECT CASE WHEN views_config_json IS NULL THEN 0 ELSE 1 END, "
            "CASE WHEN animation_config_json IS NULL THEN 0 ELSE 1 END, "
            "LENGTH(views_config_json), LENGTH(animation_config_json) "
            "FROM machine_model_configs WHERE model_id = :mid"
        ), {"mid": MODEL_ID}).fetchone()
        print(f"[OK] model_configs: {MODEL_ID} views={row[2]}ch anim={row[3]}ch")

        mach = conn.execute(text(
            "SELECT COUNT(*) FROM machines WHERE id = :mid"
        ), {"mid": "LAM2300-1"}).scalar()
        if not mach:
            conn.execute(text(
                "INSERT INTO machines (id, model, name, line, floor, chamber_count, process_type, state, "
                "temp, pressure, gas_flow, rf_power, wafer_count, alarm_count, process_step, has_smif, "
                "updated_at, x_pos, y_pos, floor_x, floor_y, display_order, use_external_url) "
                "VALUES (:id, :model, :name, 1, 1, 4, 'ETCH', 'idle', 25.0, 1.0, 0.0, 0.0, 0, 0, 0, 0, "
                ":ts, 0, 0, 50.0, 50.0, 0, 0)"
            ), {"id": "LAM2300-1", "model": MODEL_ID, "name": "LAM2300-1", "ts": now})
            print("[OK] 机台行已创建: LAM2300-1 (model=LAM2300)")
        else:
            print("[OK] 机台行已存在: LAM2300-1")

        conn.commit()
    print("[DONE] LAM2300 接线完成：SVG + views_config + animation_config + 机台行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
