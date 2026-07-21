"""修复 DB 中 model_id 不一致问题
将 VPO-2200 改为 PODOPENER-2200，与 Machine.model 字段一致

运行方式：backend\venv\Scripts\python.exe _fix_model_id.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal
from models import MachineModelConfig, Machine

db = SessionLocal()
try:
    print("=" * 60)
    print("Fix model_id mismatch")
    print("=" * 60)

    # 1. 查看当前状态
    print("\n[1] BEFORE FIX")
    all_models = db.query(MachineModelConfig).all()
    print(f"  MachineModelConfig records: {len(all_models)}")
    for m in all_models:
        print(f"    - model_id={m.model_id}, view_mode={m.view_mode}")

    pod = db.query(Machine).filter(Machine.id == "PODOPENER-1").first()
    if pod:
        print(f"  PODOPENER-1.model = {pod.model}")

    # 2. 检查是否需要修复
    vpo_model = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == "VPO-2200").first()
    poco_model = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == "PODOPENER-2200").first()

    if vpo_model and not poco_model:
        print(f"\n[2] FIXING: VPO-2200 -> PODOPENER-2200")
        old_id = vpo_model.model_id
        vpo_model.model_id = "PODOPENER-2200"
        db.commit()
        print(f"  [OK] Updated: {old_id} -> PODOPENER-2200")
    elif poco_model:
        print(f"\n[2] SKIP: PODOPENER-2200 already exists")
    else:
        print(f"\n[2] ERROR: Neither VPO-2200 nor PODOPENER-2200 found!")

    # 3. 验证修复结果
    print("\n[3] AFTER FIX")
    all_models = db.query(MachineModelConfig).all()
    print(f"  MachineModelConfig records: {len(all_models)}")
    for m in all_models:
        print(f"    - model_id={m.model_id}, view_mode={m.view_mode}")

    # 4. 验证匹配
    pod_model = pod.model if pod else "PODOPENER-2200"
    match = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == pod_model).first()
    if match:
        print(f"\n[4] MATCH CHECK: Machine.model={pod_model} -> MachineModelConfig.model_id={match.model_id} [OK]")
    else:
        print(f"\n[4] MATCH CHECK: Machine.model={pod_model} -> NOT FOUND [ERROR]")

    print("\n" + "=" * 60)
    print("Done. Please restart backend to apply changes.")
    print("=" * 60)

finally:
    db.close()
