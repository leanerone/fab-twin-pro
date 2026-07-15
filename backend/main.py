"""FabTwin 半导体厂数字孪生 - FastAPI 入口"""
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import API_HOST, API_PORT, CORS_ORIGINS, SIMULATION_ENABLED
from database import init_db, SessionLocal
from models import Machine
from seed_data import init_seed_data
from routers import machines, events, lots, alarms, ai, oht, recipes, floors, models, history
from services.realtime import ConnectionManager
from services.simulator import start_simulator
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

# WebSocket 管理器
manager = ConnectionManager()

# ========== WebSocket 端点 ==========
@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ========== 启动时初始化 ==========
@app.on_event("startup")
def on_startup():
    print("========== FabTwin 启动 ==========")

    init_db()
    print("[DB] 数据库初始化完成")

    db = SessionLocal()
    try:
        machine_count = db.query(Machine).count()
        if machine_count == 0:
            print("[Seed] 首次启动，生成种子数据...")
            init_seed_data(db)
        else:
            print("[Seed] 数据库已有数据，跳过种子数据生成")
    finally:
        db.close()

    if SIMULATION_ENABLED:
        asyncio.create_task(start_simulator(manager, cache))
        print("[Simulator] 模拟器已启动")

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
