"""完整端到端诊断：检查前端/后端/DB 全链路
运行方式：backend\venv\Scripts\python.exe _full_debug.py
"""
import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

print("=" * 70)
print("FabTwin FULL DEBUG - End-to-end chain check")
print("=" * 70)

# ---- 1. 数据库连接 ----
print("\n[1] DATABASE CONNECTION")
print("-" * 70)
try:
    from database import SessionLocal, engine, DB_IS_SQLITE
    from config import DB_TYPE, ORACLE_HOST, ORACLE_SERVICE, ORACLE_USER
    print(f"  DB_TYPE: {DB_TYPE}")
    print(f"  Is SQLite: {DB_IS_SQLITE}")
    print(f"  Oracle: {ORACLE_HOST}/{ORACLE_SERVICE} user={ORACLE_USER}")
    print(f"  Engine: {engine}")
    db = SessionLocal()
    print("  [OK] Session opened")
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

# ---- 2. 查 PODOPENER-1 机台 ----
print("\n[2] MACHINE PODOPENER-1")
print("-" * 70)
try:
    from models import Machine
    pod = db.query(Machine).filter(Machine.id == "PODOPENER-1").first()
    if pod:
        print(f"  [OK] Found: {pod.id}")
        print(f"    name: {pod.name}")
        print(f"    model: {pod.model}")
        print(f"    state: {pod.state}")
    else:
        print("  [ERROR] PODOPENER-1 NOT FOUND in Machine table")
        all_machines = db.query(Machine).filter(Machine.model.like('%PODOPENER%')).all()
        for m in all_machines:
            print(f"    Possible: {m.id} model={m.model}")
except Exception as e:
    print(f"  [ERROR] {e}")

# ---- 3. 查 PODOPENER-2200 模型 ----
print("\n[3] MODEL PODOPENER-2200")
print("-" * 70)
try:
    from models import MachineModelConfig
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == "PODOPENER-2200").first()
    if m:
        print(f"  [OK] Found: {m.model_id}")
        print(f"    view_mode: {m.view_mode}")
        print(f"    model_name: {m.model_name}")
        try:
            vc = json.loads(m.views_config_json) if m.views_config_json else {}
            print(f"    views_config keys: {list(vc.keys())}")
            if 'view_2d' in vc:
                print(f"    view_2d.type: {vc['view_2d'].get('type')}")
            if 'view_3d' in vc:
                print(f"    view_3d.type: {vc['view_3d'].get('type')}")
        except Exception as e:
            print(f"    [ERROR] parsing views_config: {e}")
    else:
        print("  [ERROR] PODOPENER-2200 NOT FOUND in MachineModelConfig")
except Exception as e:
    print(f"  [ERROR] {e}")

# ---- 4. 模拟前端 resolveModelId 逻辑 ----
print("\n[4] SIMULATE FRONTEND resolveModelId('PODOPENER-2200')")
print("-" * 70)
try:
    all_models = db.query(MachineModelConfig).all()
    model_map = {m.model_id: m for m in all_models}
    print(f"  Available model_ids: {list(model_map.keys())}")

    machine_model = "PODOPENER-2200"
    if model_map.get(machine_model):
        resolved = machine_model
        print(f"  [OK] Exact match: {resolved}")
    else:
        upper = machine_model.upper().replace('\\s+', '-')
        if model_map.get(upper):
            resolved = upper
            print(f"  [OK] Uppercase match: {resolved}")
        else:
            # Fuzzy
            for id_ in model_map:
                if machine_model.upper() in id_.upper():
                    resolved = id_
                    print(f"  [OK] Fuzzy match: {resolved}")
                    break
            else:
                resolved = "GENERIC-ETCH"
                print(f"  [FALLBACK] No match, using: {resolved}")

    # 模拟 resolveViewMode
    target = model_map.get(resolved)
    if target:
        vm = target.view_mode
        print(f"  view_mode from DB: {vm}")
        vc = json.loads(target.views_config_json) if target.views_config_json else {}
        view_3d_type = vc.get('view_3d', {}).get('type')
        print(f"  view_3d.type: {view_3d_type}")
        if vm == 'vpo':
            if view_3d_type == 'vpo':
                final = 'vpo3d'
            else:
                final = 'vpo'
            print(f"  FINAL viewMode: {final}")
        else:
            print(f"  FINAL viewMode: {vm}")
except Exception as e:
    print(f"  [ERROR] {e}")

# ---- 5. HTTP API 测试 ----
print("\n[5] HTTP API TEST")
print("-" * 70)
try:
    import urllib.request
    import urllib.error

    base = "http://127.0.0.1:8002"
    endpoints = [
        ("/health", "GET"),
        ("/api/models", "GET"),
        ("/api/machines/PODOPENER-1", "GET"),
        ("/api/history/PODOPENER-1?limit=5", "GET"),
    ]

    for path, method in endpoints:
        url = base + path
        try:
            req = urllib.request.Request(url, method=method)
            req.add_header("User-Agent", "FullDebug/1.0")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                print(f"  [OK] {method} {path} -> {resp.status}")
                if "/models" in path and resp.status == 200:
                    data = json.loads(body)
                    print(f"    Got {len(data)} models:")
                    for d in data:
                        print(f"      - {d.get('model_id')}: view_mode={d.get('view_mode')}")
                        vc = d.get('views_config', {})
                        if vc:
                            v2d = vc.get('view_2d', {}).get('type', '?')
                            v3d = vc.get('view_3d', {}).get('type', '?')
                            print(f"        view_2d.type={v2d}, view_3d.type={v3d}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  [{e.code}] {method} {path}: {e.reason}")
            print(f"    body: {body[:200]}")
        except urllib.error.URLError as e:
            print(f"  [CONN-ERROR] {method} {path}: {e.reason}")
            print(f"    (Backend may not be running on port 8002)")
            break
        except Exception as e:
            print(f"  [ERROR] {method} {path}: {e}")
except Exception as e:
    print(f"  [ERROR] {e}")

# ---- 6. 检查 vite preview 是否在 5173 端口 ----
print("\n[6] VITE PREVIEW CHECK")
print("-" * 70)
try:
    base = "http://127.0.0.1:5173"
    # 检查 dist 静态资源
    try:
        with urllib.request.urlopen(base + "/", timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:200]
            print(f"  [OK] GET / -> {resp.status}")
            print(f"    HTML preview: {body[:100]}")
    except Exception as e:
        print(f"  [ERROR] GET /: {e}")

    # 检查 vite proxy 是否生效（请求 /api/models 应该被代理到后端）
    try:
        req = urllib.request.Request(base + "/api/models", method="GET")
        req.add_header("User-Agent", "FullDebug/1.0")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"  [OK] GET /api/models (via vite proxy) -> {resp.status}")
            data = json.loads(body)
            print(f"    Got {len(data)} models")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [{e.code}] GET /api/models via vite proxy: {e.reason}")
        if e.code == 403:
            print(f"    [DIAGNOSIS] Vite preview IS NOT proxying /api!")
            print(f"    Vite config needs preview.proxy section.")
            print(f"    body: {body[:200]}")
        else:
            print(f"    body: {body[:200]}")
    except Exception as e:
        print(f"  [ERROR] GET /api/models via vite: {e}")
except Exception as e:
    print(f"  [ERROR] {e}")

# ---- 7. 检查前端的 dist 是否包含最新配置 ----
print("\n[7] FRONTEND DIST CHECK")
print("-" * 70)
try:
    import os
    frontend_dir = os.path.join(BASE_DIR, 'frontend')
    dist_index = os.path.join(frontend_dir, 'dist', 'index.html')
    dist_assets = os.path.join(frontend_dir, 'dist', 'assets')

    if os.path.exists(dist_index):
        size = os.path.getsize(dist_index)
        mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(dist_index)))
        print(f"  [OK] dist/index.html: {size} bytes, modified {mtime}")
    else:
        print(f"  [ERROR] dist/index.html NOT FOUND")
        print(f"    Please run: cd frontend && npm run build")

    if os.path.exists(dist_assets):
        files = sorted(os.listdir(dist_assets))
        js_files = [f for f in files if f.endswith('.js')]
        print(f"  Assets: {len(files)} files, {len(js_files)} JS files")
        if js_files:
            for js in js_files[:3]:
                fp = os.path.join(dist_assets, js)
                size = os.path.getsize(fp)
                mtime = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(fp)))
                print(f"    {js}: {size} bytes, {mtime}")

    # 检查 vite.config.js 修改时间
    vite_cfg = os.path.join(frontend_dir, 'vite.config.js')
    if os.path.exists(vite_cfg):
        mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(vite_cfg)))
        print(f"  vite.config.js modified: {mtime}")
        with open(vite_cfg, 'r') as f:
            content = f.read()
            if 'preview' in content and 'proxy' in content:
                if 'preview:' in content and 'proxy:' in content[content.find('preview:'):]:
                    print(f"  [OK] vite.config.js has preview.proxy")
                else:
                    print(f"  [WARN] vite.config.js has preview but no preview.proxy!")
            else:
                print(f"  [WARN] vite.config.js may be missing preview.proxy")
except Exception as e:
    print(f"  [ERROR] {e}")

print("\n" + "=" * 70)
print("END OF DIAGNOSIS")
print("=" * 70)

db.close()
