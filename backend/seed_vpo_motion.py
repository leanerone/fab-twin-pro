"""
PODOPENER-2200 机型配置切换：vpo(程序化SVG) → motion2d(SVG资产 + Motion JSON)

SVG 统一改造（feature/svg-unify 分支）：
- 2D 视图改走通用 MachineMotion2D 管线（views_config.view_2d.svg_source 指向静态 SVG 资产）
- 动画改由 animation_config（Motion JSON v1.1）+ podopener deriver 驱动
- 保留 view_3d（MachineVpo3DView Three.js 3D 视图）不动

幂等：可重复执行。用法：backend 下 ./venv/Scripts/python.exe seed_vpo_motion.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import SessionLocal  # noqa: E402
from models import MachineModelConfig  # noqa: E402

MODEL_ID = "PODOPENER-2200"
SVG_SRC = BASE_DIR.parent / "models" / "user" / "podopener-2200.svg"
SVG_DST = BASE_DIR / "uploads" / "models" / "podopener-2200.svg"
MOTION_JSON_PATH = BASE_DIR.parent / "models" / "user" / "podopener-2200.motion.json"


def main():
    anim_text = MOTION_JSON_PATH.read_text(encoding="utf-8")
    anim = json.loads(anim_text)

    # SVG 资产同步到 uploads（URL 由 views_config 引用）；
    # 与 seed_oxe_motion.py 对齐，否则改了 models/user 里的源 SVG 副本不会生效。
    shutil.copyfile(SVG_SRC, SVG_DST)

    views_config = {
        "view_3d": {"type": "vpo", "model_source": "/models/podopener-2200-3d.json",
                    "default_camera": {"position": [700, -300, 400], "target": [0, 0, 400]}},
        "view_2d": {"type": "motion2d", "svg_source": "/uploads/models/podopener-2200.svg",
                    "view_label": "PODOPENER 2D 动画"},
    }
    # 按「已上传文件」槽位登记 SVG（模型管理列表可见 + /extract-svg-parts 可提取部件）
    svg_slot = {
        "file_id": "seedvposvg",
        "file_name": SVG_DST.name,
        "file_url": views_config["view_2d"]["svg_source"],
        "file_type": ".svg",
        "file_size": SVG_SRC.stat().st_size,
        "version": "2.0",
        "uploaded_by": "seed",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    source_files = {"current_svg": svg_slot, "current_file": svg_slot}

    db = SessionLocal()
    try:
        row = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == MODEL_ID).first()
        if not row:
            print(f"[ERROR] 未找到机型配置 {MODEL_ID}，请先跑 seed_data.py")
            sys.exit(1)

        row.view_mode = "motion2d"
        row.version = "2.0"
        row.description = "PODOPENER 开盖机（motion2d 统一管线）：静态 SVG + Motion JSON + podopener deriver"
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
