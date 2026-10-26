"""
TEL-DRM-UNIT (OXE) 机型配置切换：oxe(Canvas看板) → motion2d(SVG资产 + Motion JSON)

SVG 统一改造（feature/svg-unify 分支）：
- 2D 视图改走通用 MachineMotion2D 管线（views_config.view_2d.svg_source 指向静态 SVG 资产）
- 动画改由 animation_config（Motion JSON v1.1）+ oxe deriver 驱动，
  事件语义移植自旧 MachineOxeView.applyEvent（20+ 事件）
- 保留 view_3d（threejs procedural）不动

幂等：可重复执行。用法：backend 下 ./venv/Scripts/python.exe seed_oxe_motion.py
"""
import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import SessionLocal  # noqa: E402
from models import MachineModelConfig  # noqa: E402

MODEL_ID = "TEL-DRM-UNIT"
SVG_SRC = BASE_DIR.parent / "models" / "user" / "oxe-drm-topview.svg"
SVG_DST = BASE_DIR / "uploads" / "models" / "oxe-drm-topview.svg"
MOTION_JSON_PATH = BASE_DIR.parent / "models" / "user" / "oxe-drm-topview.motion.json"


def main():
    anim = json.loads(MOTION_JSON_PATH.read_text(encoding="utf-8"))

    # SVG 资产同步到 uploads（URL 由 views_config 引用）
    shutil.copyfile(SVG_SRC, SVG_DST)

    views_config = {
        "view_3d": {"type": "threejs", "model_source": "procedural",
                    "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
        "view_2d": {"type": "motion2d", "svg_source": "/uploads/models/oxe-drm-topview.svg",
                    "view_label": "OXE DRM 顶视图"},
    }
    source_files = {
        "svg": "models/user/oxe-drm-topview.svg",
        "motion_json": "models/user/oxe-drm-topview.motion.json",
    }

    db = SessionLocal()
    try:
        row = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == MODEL_ID).first()
        if not row:
            print(f"[ERROR] 未找到机型配置 {MODEL_ID}，请先跑 seed_data.py")
            sys.exit(1)

        row.view_mode = "motion2d"
        row.version = "2.0"
        row.description = "OXE DRM UNITY 刻蚀机（motion2d 统一管线）：静态 SVG + Motion JSON + oxe deriver"
        row.views_config_json = json.dumps(views_config, ensure_ascii=False)
        row.animation_config_json = json.dumps(anim, ensure_ascii=False)
        row.source_files_json = json.dumps(source_files, ensure_ascii=False)
        db.commit()
        print(f"[OK] {MODEL_ID} → view_mode=motion2d, motion steps={len(anim['motions'])}, "
              f"svg={views_config['view_2d']['svg_source']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
