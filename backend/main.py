"""FabTwin 半导体厂数字孪生 - FastAPI 入口"""
import os
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 配置日志：确保db_poller等模块的logger.info能输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

from config import API_HOST, API_PORT, CORS_ORIGINS, SIMULATION_ENABLED, DB_POLLER_ENABLED
from database import init_db, SessionLocal
from models import Machine
from seed_data import init_seed_data
from routers import machines, events, lots, alarms, ai, oht, recipes, floors, models, history, auth, users
from routers.rvmessages import router as rv_router
from services.realtime import manager
from services.simulator import start_simulator
from services.db_poller import start_db_poller
from services.cache import cache
from services.ai_mcp import ai_mcp

app = FastAPI(title="FabTwin API", version="1.0")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(machines.router, tags=["machines"])
app.include_router(events.router, tags=["events"])
app.include_router(lots.router, tags=["lots"])
app.include_router(alarms.router, tags=["alarms"])
app.include_router(ai.router, tags=["ai"])
app.include_router(oht.router, tags=["oht"])
app.include_router(recipes.router, tags=["recipes"])
app.include_router(floors.router, tags=["floors"])
app.include_router(models.router, tags=["machine models"])
app.include_router(history.router, tags=["history"])
app.include_router(auth.router, tags=["auth"])
app.include_router(users.router, tags=["users"])
app.include_router(rv_router, tags=["rv"])

# ========== WebSocket 端点 ==========
@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # 发送连接成功确认，防止代理因无双向通信而断开
        await websocket.send_json({"type": "connected", "ts": datetime.now().isoformat()})
        while True:
            data = await websocket.receive_text()
            # 处理前端 ping，回复 pong 保持连接
            if data.strip() == '{"type":"ping"}':
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ========== 启动时初始化 ==========
@app.on_event("startup")
def on_startup():
    print("========== FabTwin 启动 ==========")

    # 打印 DB 配置
    from config import (
        DB_TYPE, ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE,
        ORACLE_USER, ORACLE_DSN_TYPE,
    )
    ORACLE_CLIENT_DIR = os.getenv("ORACLE_CLIENT_DIR", "N/A")
    print(f"[DB Config] DB_TYPE={DB_TYPE}")
    print(f"[DB Config] ORACLE_HOST={ORACLE_HOST}")
    print(f"[DB Config] ORACLE_PORT={ORACLE_PORT}")
    print(f"[DB Config] ORACLE_SERVICE={ORACLE_SERVICE}")
    print(f"[DB Config] ORACLE_USER={ORACLE_USER}")
    print(f"[DB Config] ORACLE_DSN_TYPE={ORACLE_DSN_TYPE}")
    print(f"[DB Config] ORACLE_CLIENT_DIR={ORACLE_CLIENT_DIR}")

    try:
        init_db()
        from database import engine
        print(f"[DB] Connected to: {engine.url}")
        print("[DB] 数据库初始化完成")

        db = SessionLocal()
        try:
            machine_count = db.query(Machine).count()
            if machine_count == 0:
                print("[Seed] 首次启动，生成种子数据...")
                init_seed_data(db)
            else:
                print(f"[Seed] 数据库已有 {machine_count} 台机台，跳过种子数据生成")

                # 检查 MACHINE_MODEL_CONFIGS
                from models import MachineModelConfig
                model_count = db.query(MachineModelConfig).count()
                print(f"[Seed] MACHINE_MODEL_CONFIGS 有 {model_count} 条记录")
                for m in db.query(MachineModelConfig).all():
                    print(f"[Seed]   - {m.model_id}: view_mode={m.view_mode}")
        finally:
            db.close()

        if SIMULATION_ENABLED:
            asyncio.create_task(start_simulator(manager, cache))
            print("[Simulator] 模拟器已启动")

        if DB_POLLER_ENABLED:
            asyncio.create_task(start_db_poller())
            print("[DB Poller] DB事件轮询服务已启动")
    except Exception as e:
        print(f"[WARN] 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        print("[WARN] 将以降级模式启动，部分功能可能不可用")
        try:
            if SIMULATION_ENABLED:
                asyncio.create_task(start_simulator(manager, cache))
                print("[Simulator] 模拟器已启动")
        except Exception as e2:
            print(f"[WARN] 模拟器启动失败: {e2}")

    print(f"[API] 服务运行在 http://{API_HOST}:{API_PORT}")
    print(f"[API] 文档地址: http://{API_HOST}:{API_PORT}/docs")
    print("========== 启动完成 ==========")

# ========== 健康检查 ==========
@app.get("/health")
async def health():
    return {"status": "ok", "service": "fabtwin"}

# ========== 运行服务 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
