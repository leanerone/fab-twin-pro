# -*- coding: utf-8 -*-
"""修复 machine_model_configs 缺行问题（固化 2026-10-25 晨间手工旁路操作）。

背景：
    backend/seed_data.py 的 create_machine_model_configs() 有守卫：
    "表非空(count>0)即整体跳过"。当库从公司导入了部分数据、
    machine_model_configs 非空但缺默认机型（PODOPENER-2200 /
    TEL-DRM-UNIT / GENERIC-ETCH）时，后端启动时的自动 seed 永远补不上，
    机台详情页表现为"只剩单一视图"或视图 404（如 OXE/PODOPENER 缺 3D+2D）。

做法：
    1. 只删除这三个默认 model_id 的旧配置行（连同 event_action_mappings），
       其他手工/编辑器产生的配置不受影响；
    2. 用去掉守卫的 seed 函数重新插入完整默认配置；
    3. 校验并打印结果。

用法（在仓库根目录执行）：
    python tests/repair_model_configs.py --check   # 只看现状，不改库
    python tests/repair_model_configs.py           # 执行修复
"""
import sys
import inspect
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from database import SessionLocal  # noqa: E402
import seed_data  # noqa: E402

# seed_data.create_machine_model_configs() 内写死的三个默认机型
DEFAULT_MODEL_IDS = ["PODOPENER-2200", "TEL-DRM-UNIT", "GENERIC-ETCH"]


def patched_create(db):
    """取 seed 函数源码、去掉非空守卫后执行（与线上 seed 完全同源，防漂移）。"""
    src = inspect.getsource(seed_data.create_machine_model_configs)
    patched = src.replace("if existing > 0:", "if False:  # repair: guard disabled")
    if patched == src:
        raise RuntimeError("未能定位 seed 守卫代码，seed_data.py 可能已改动，请人工核对")
    ns = dict(vars(seed_data))
    exec(compile(patched, "<repair_model_configs>", "exec"), ns)
    ns["create_machine_model_configs"](db)


def show_status(db):
    from models import MachineModelConfig, EventActionMapping
    rows = db.query(MachineModelConfig).all()
    print(f"machine_model_configs 共 {len(rows)} 行：")
    for r in rows:
        print(f"  {r.model_id:<18} view_mode={r.view_mode}")
    maps = db.query(EventActionMapping).count()
    print(f"event_action_mappings 共 {maps} 行")
    missing = [m for m in DEFAULT_MODEL_IDS if m not in {r.model_id for r in rows}]
    print(f"缺失默认机型：{missing if missing else '无'}")
    return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只查看现状，不修改")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        missing = show_status(db)
        if args.check:
            return
        if not missing:
            print("默认机型齐全，无需修复")
            return

        from models import MachineModelConfig, EventActionMapping
        # 先删默认机型的旧行，避免重新插入时主键冲突（GENERIC-ETCH 教训）
        db.query(EventActionMapping).filter(
            EventActionMapping.model_id.in_(DEFAULT_MODEL_IDS)
        ).delete(synchronize_session=False)
        db.query(MachineModelConfig).filter(
            MachineModelConfig.model_id.in_(DEFAULT_MODEL_IDS)
        ).delete(synchronize_session=False)
        db.commit()

        patched_create(db)
        db.commit()

        print("\n修复后：")
        show_status(db)
        print("完成。若后端正在运行请重启，使配置缓存生效。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
