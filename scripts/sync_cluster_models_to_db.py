# -*- coding: utf-8 -*-
"""Cluster 机型批量接线入库（照 sync_lam2300_model_to_db.py 模式，可重复执行）：

每台机：SVG 拷到 backend/uploads/models/ + upsert machine_model_configs
（views_config_json 挂 2D SVG、animation_config_json 写 motion JSON）+
确保存在一条机台行供 /api/debug/event 注入与前端选择。

用法：python scripts/sync_cluster_models_to_db.py [lam2300|synapse|sym3|all]
"""
import datetime
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import MachineModelConfig  # noqa: E402

# model_id: (型号名, 厂商, SVG 文件名, 视图标签, 机台行 id, motion 里的 deriver 名)
MODELS = {
    "lam2300": ("LAM 2300 刻蚀台", "LAM", "lam2300-topview.svg", "LAM 2300 顶视图", "LAM2300-1", "LAM2300"),
    "synapse": ("TEL Synapse SPT 刻蚀台", "TEL", "tel-synapse-topview.svg", "TEL Synapse 等角视图", "SYN-1", "TEL-SYNAPSE"),
    "sym3": ("AMAT Centris Sym3 刻蚀台", "AMAT", "centris-sym3-topview.svg", "Centris Sym3 等角视图", "SYM3-1", "CENTRIS-SYM3"),
}


def sync_one(key: str) -> None:
    mname, vendor, svg_file, view_label, machine_id, _ = MODELS[key]
    model_id = {
        "lam2300": "LAM2300", "synapse": "TEL-SYNAPSE", "sym3": "AMAT-CENTRIS-SYM3",
    }[key]
    user_dir = os.path.join(_ROOT, "models", "user")
    motion_file = svg_file.replace(".svg", ".motion.json")
    with open(os.path.join(user_dir, motion_file), "r", encoding="utf-8") as f:
        motion = json.load(f)
    with open(os.path.join(user_dir, svg_file), "r", encoding="utf-8") as f:
        svg_text = f.read()

    dst = os.path.join(_ROOT, "backend", "uploads", "models", svg_file)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg_text)

    views = {
        "view_3d": {"type": "threejs", "model_source": "procedural",
                    "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
        "view_2d": {"type": "motion2d", "svg_source": f"/uploads/models/{svg_file}",
                    "view_label": view_label},
    }
    now = datetime.datetime.now().isoformat(timespec="seconds")
    values = {
        "model_name": mname,
        "vendor": vendor,
        "process_type": "ETCH",
        "version": "1.0",
        "view_mode": "motion2d",
        "views_config_json": json.dumps(views, ensure_ascii=False),
        "animation_config_json": json.dumps(motion, ensure_ascii=False),
        "updated_at": now,
    }
    with SessionLocal() as db:
        config = db.get(MachineModelConfig, model_id)
        if config is None:
            db.add(MachineModelConfig(
                model_id=model_id,
                description=f"{mname}（motion2d 统一管线，26 步标准事件词表）",
                created_at=now,
                **values,
            ))
        else:
            for field, value in values.items():
                setattr(config, field, value)
        if not db.execute(text("SELECT COUNT(*) FROM machines WHERE id = :id"), {"id": machine_id}).scalar():
            db.execute(text(
                "INSERT INTO machines (id, model, name, line, floor, chamber_count, process_type, state, "
                "temp, pressure, gas_flow, rf_power, wafer_count, alarm_count, process_step, has_smif, "
                "updated_at, x_pos, y_pos, floor_x, floor_y, display_order, use_external_url) "
                "VALUES (:id, :model, :id, 1, 1, 6, 'ETCH', 'idle', 25.0, 1.0, 0.0, 0.0, 0, 0, 0, 0, "
                ":ts, 0, 0, 50.0, 50.0, 0, 0)"), {"id": machine_id, "model": model_id, "ts": now})
            machine_msg = f"机台行已创建 {machine_id}"
        else:
            machine_msg = f"机台行已存在 {machine_id}"
        db.commit()
    print(f"[OK] {model_id}: SVG {len(svg_text)}ch / motion {len(motion['motions'])} 步 / deriver={motion['ext']['deriver']} / {machine_msg}")


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    keys = list(MODELS) if which == "all" else [which]
    for key in keys:
        if key not in MODELS:
            print(f"[ERROR] 未知机型 {key}（可选 {', '.join(MODELS)}）")
            return 1
        sync_one(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
