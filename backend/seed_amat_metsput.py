"""一次性脚本：把 AMAT METSPUT 机型资料补齐到本地 Oracle DB

内容：
1. MACHINE_MODEL_CONFIGS 插入 AMAT-METSPUT（view_mode=motion2d，animation_config_json=amat_metsput_v1.1.json）
2. MACHINES 插入 AMAT-T1 测试机台
3. 拷贝 amat_metsput.svg → backend/uploads/models/

幂等：已存在则先删后插。
执行：cd backend && python seed_amat_metsput.py
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Machine, MachineModelConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_SRC = os.path.join(ROOT, "models", "user", "amat_metsput_v1.1.json")
SVG_SRC = os.path.join(ROOT, "models", "user", "amat_metsput.svg")
SVG_DST_DIR = os.path.join(ROOT, "backend", "uploads", "models")
SVG_DST = os.path.join(SVG_DST_DIR, "amat_metsput.svg")

MODEL_ID = "AMAT-METSPUT"
MACHINE_ID = "AMAT-T1"

now = datetime.now().isoformat(timespec="seconds")


def main():
    # 1. 读 JSON
    with open(JSON_SRC, "r", encoding="utf-8") as f:
        anim_payload = json.load(f)
    anim_json = json.dumps(anim_payload, ensure_ascii=False)
    print(f"[1/4] 读取 {JSON_SRC}，长度={len(anim_json)}")

    db = SessionLocal()
    try:
        # 2. 机型配置（幂等：先删后插）
        db.query(MachineModelConfig).filter(MachineModelConfig.model_id == MODEL_ID).delete()
        views_config = {
            "view_2d": {
                "type": "motion2d",
                "svg_source": "/uploads/models/amat_metsput.svg",
                "view_label": "AMAT METSPUT 俯视图",
            }
        }
        source_files = {
            "svg": "models/user/amat_metsput.svg",
            "motion_json": "models/user/amat_metsput_v1.1.json",
        }
        db.add(MachineModelConfig(
            model_id=MODEL_ID,
            model_name="AMAT METSPUT PVD 溅射机",
            vendor="AMAT",
            process_type="PVD",
            version="1.1",
            view_mode="motion2d",
            description="AMAT METSPUT PVD 溅射机，Motion2D 通用动画（ARM_1 缓冲臂 + ARM_2 传送臂，PVD 1-4 腔 + Buffer A-F）",
            views_config_json=json.dumps(views_config, ensure_ascii=False),
            animation_config_json=anim_json,
            source_files_json=json.dumps(source_files, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        ))
        db.flush()
        print(f"[2/4] 机型配置已写入: {MODEL_ID} (view_mode=motion2d, version=1.1)")

        # 3. 机台（幂等：先删后插）
        db.query(Machine).filter(Machine.id == MACHINE_ID).delete()
        db.add(Machine(
            id=MACHINE_ID,
            model=MODEL_ID,
            name="AMAT METSPUT 测试机",
            line=1,
            floor=1,
            chamber_count=4,
            process_type="PVD",
            state="idle",
            temp=25.0,
            pressure=760.0,
            gas_flow=0.0,
            rf_power=0.0,
            wafer_count=0,
            alarm_count=0,
            process_step=0,
            has_smif=0,
            updated_at=now,
            x_pos=0.0,
            y_pos=0.0,
            floor_x=100.0,
            floor_y=100.0,
            display_order=999,
        ))
        db.flush()
        print(f"[3/4] 机台已写入: {MACHINE_ID} (model={MODEL_ID})")

        db.commit()
    finally:
        db.close()

    # 4. 拷贝 SVG
    os.makedirs(SVG_DST_DIR, exist_ok=True)
    shutil.copyfile(SVG_SRC, SVG_DST)
    print(f"[4/4] SVG 已部署: {SVG_DST} ({os.path.getsize(SVG_DST)} bytes)")

    # 5. 验证
    db = SessionLocal()
    try:
        m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == MODEL_ID).first()
        print(f"\n[验证] MACHINE_MODEL_CONFIGS: model_id={m.model_id}, view_mode={m.view_mode}, version={m.version}, json_len={len(m.animation_config_json)}")
        mc = db.query(Machine).filter(Machine.id == MACHINE_ID).first()
        print(f"[验证] MACHINES: id={mc.id}, model={mc.model}, state={mc.state}")
    finally:
        db.close()

    print("\n[完成] AMAT METSPUT 资料已补齐")


if __name__ == "__main__":
    main()