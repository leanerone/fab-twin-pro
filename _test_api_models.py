"""测试后端 API 返回的 models 数据
运行方式：backend\venv\Scripts\python.exe _test_api_models.py
"""
import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal
from models import MachineModelConfig, Machine

db = SessionLocal()
try:
    print("=" * 60)
    print("MachineModelConfig Check (API view)")
    print("=" * 60)

    models = db.query(MachineModelConfig).order_by(MachineModelConfig.model_id).all()
    for m in models:
        print(f"\n[Model] {m.model_id}")
        print(f"  model_name: {m.model_name}")
        print(f"  view_mode: {m.view_mode}")
        print(f"  vendor: {m.vendor}")

        views_config = {}
        try:
            views_config = json.loads(m.views_config_json) if m.views_config_json else {}
        except Exception as e:
            print(f"  ERROR parsing views_config: {e}")
        print(f"  views_config:")
        for key, val in views_config.items():
            print(f"    {key}: {val}")

        parts_config = []
        try:
            parts_config = json.loads(m.parts_config_json) if m.parts_config_json else []
        except Exception:
            pass
        print(f"  parts_config: {len(parts_config)} items")

        state_mapping = []
        try:
            state_mapping = json.loads(m.state_mapping_json) if m.state_mapping_json else []
        except Exception:
            pass
        print(f"  state_mapping: {len(state_mapping)} items")

    print("\n" + "=" * 60)
    print("PODOPENER-1 Machine Check")
    print("=" * 60)
    pod = db.query(Machine).filter(Machine.id == "PODOPENER-1").first()
    if pod:
        print(f"  id: {pod.id}")
        print(f"  name: {pod.name}")
        print(f"  model: {pod.model}")
        print(f"  state: {pod.state}")

        # 验证 resolveModelId 逻辑
        target_id = "PODOPENER-2200"
        if pod.model == target_id:
            print(f"  RESOLVE: {pod.model} -> {target_id} (exact match)")
        else:
            print(f"  RESOLVE: {pod.model} != {target_id}")

    print("\n" + "=" * 60)
    print("HTTP API Test")
    print("=" * 60)
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8000/api/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  /api/models returned {len(data)} models")
            for d in data:
                print(f"    - {d.get('model_id')}, view_mode={d.get('view_mode')}")
                vc = d.get("views_config", {})
                if vc:
                    print(f"      view_2d.type: {vc.get('view_2d', {}).get('type')}")
                    print(f"      view_3d.type: {vc.get('view_3d', {}).get('type')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  (Backend may not be running on port 8000)")

finally:
    db.close()
