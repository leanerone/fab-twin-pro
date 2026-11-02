"""
三台 cluster 新机台（LAM2300 / Centris Sym3 / TEL Synapse）接线入库
——ver3 资产复核补漏：资产/deriver 已交付，但 MACHINE_MODEL_CONFIGS 未写入、
也未绑定演示机台，前端无模型可选（2026-10-30 复核发现）。

幂等：先删后插配置 + merge 演示机台。
用法：backend 下  ORACLE_SERVICE=xepdb python seed_cluster_models.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import SessionLocal  # noqa: E402
from models import MachineModelConfig, Machine, Floor  # noqa: E402

ROOT = BASE_DIR.parent

# (model_id, 中文名, process_type, vendor, 资产名, 演示机台号)
MODELS = [
    ("LAM-2300", "LAM 2300 刻蚀平台", "ETCH", "LAM", "lam2300-topview", "LAM-01"),
    ("CENTRIS-SYM3", "AMAT Centris Sym3 刻蚀机", "ETCH", "AMAT", "centris-sym3-topview", "SYM3-01"),
    ("TEL-SYNAPSE", "TEL Synapse 200mm fpD", "ETCH", "TEL", "tel-synapse-topview", "SYNAPSE-01"),
]

VERSION = "3.0"


def build_config(mid, name, process_type, vendor, asset, machine_id):
    svg_src = ROOT / "models" / "user" / f"{asset}.svg"
    motion_src = ROOT / "models" / "user" / f"{asset}.motion.json"
    svg_dst = BASE_DIR / "uploads" / "models" / f"{asset}.svg"
    shutil.copyfile(svg_src, svg_dst)

    anim = json.loads(motion_src.read_text(encoding="utf-8"))
    svg_url = f"/uploads/models/{asset}.svg"
    views_config = {
        "view_3d": {"type": "threejs", "model_source": "procedural",
                    "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
        "view_2d": {"type": "motion2d", "svg_source": svg_url,
                    "view_label": f"{name} 顶视图"},
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slot = {
        "file_id": f"seed{asset.replace('-', '')}",
        "file_name": f"{asset}.svg",
        "file_url": svg_url,
        "file_type": ".svg",
        "file_size": svg_src.stat().st_size,
        "version": VERSION,
        "uploaded_by": "seed",
        "created_at": now,
    }
    source_files = {"current_svg": slot, "current_file": slot}

    db = SessionLocal()
    try:
        row = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == mid).first()
        if not row:
            row = MachineModelConfig(model_id=mid)
            db.add(row)
        row.model_name = name
        row.vendor = vendor
        row.process_type = process_type
        row.version = VERSION
        row.view_mode = "motion2d"
        row.description = f"{name}（ver3 cluster 建模，motion2d 统一管线，deriver={anim['ext']['deriver']}）"
        row.views_config_json = json.dumps(views_config, ensure_ascii=False)
        row.animation_config_json = json.dumps(anim, ensure_ascii=False)
        row.source_files_json = json.dumps(source_files, ensure_ascii=False)
        row.parts_config_json = row.parts_config_json or "[]"
        row.state_mapping_json = row.state_mapping_json or "{}"
        row.hotspots_config_json = row.hotspots_config_json or "[]"
        row.created_at = row.created_at or now
        row.updated_at = now

        # 演示机台绑定（挂 3F 主生产楼层；无楼层则不挂）
        floor = db.query(Floor).filter(Floor.name.like('%3%')).first()
        m = db.query(Machine).filter(Machine.id == machine_id).first()
        if not m:
            m = Machine(id=machine_id)
            db.add(m)
        m.name = name
        m.model = mid
        m.process_type = process_type
        m.state = "idle"
        m.line = 1
        m.has_smif = 1
        if floor is not None:
            m.floor = floor.id
        db.commit()
        print(f"[OK] {mid} → motion2d（{len(anim['motions'])} 步），机台 {machine_id} 已绑定")
    finally:
        db.close()


def main():
    for args in MODELS:
        build_config(*args)


if __name__ == "__main__":
    main()
