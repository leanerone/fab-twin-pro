"""FabTwin 半导体厂数字孪生 - FastAPI 入口"""
import os
import sys
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Windows 控制台默认 GBK：print/logging 输出含 ✓ 等非 GBK 字符会直接
# UnicodeEncodeError，在 SSE 生成器里炸断流（前端永远等不到 final/[DONE]）。
# 强制 UTF-8 + errors='replace'：无法编码的字符降级为 ?，绝不让日志炸业务。
# IIS/服务化部署下 stdout 可能无 reconfigure 属性，try 保护。
for _stream_name in ("stdout", "stderr"):
    _s = getattr(sys, _stream_name, None)
    try:
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 配置日志：确保db_poller等模块的logger.info能输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

from config import API_HOST, API_PORT, CORS_ORIGINS, SIMULATION_ENABLED, DB_POLLER_ENABLED
from database import init_db, SessionLocal
from models import Machine, AIConfig, AIProviderConfig, AIUsageLog
from seed_data import init_seed_data
from routers import machines, events, lots, alarms, ai, oht, recipes, floors, models, history, auth, users, uploads, oxe, debug
from routers.rvmessages import router as rv_router
from services.realtime import manager
from services.simulator import start_simulator
from services.db_poller import start_db_poller
from services.cache import cache

# T8：operation_id 统一用函数名（默认会拼路径后缀，如 list_machines_api_machines_get），
# 让 MCP 工具名保持 list_machines / get_machine 这种干净命名。
# 前端只按 URL 调接口，不消费 operationId，无副作用。
app = FastAPI(
    title="FabTwin API",
    version="1.0",
    generate_unique_id_function=lambda route: route.name,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载上传目录为静态文件服务，让前端可通过 /uploads/models/xxx.svg 访问
_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads", "models")
os.makedirs(_UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "uploads")), name="uploads")

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
app.include_router(uploads.router, tags=["uploads"])
app.include_router(rv_router, tags=["rv"])
app.include_router(oxe.router, tags=["oxe"])
app.include_router(debug.router, tags=["debug"])

# ========== MCP（T8）：把内部只读 API 注册为标准 MCP 工具 ==========
# 选择性暴露：只挂读类/跳转类，管理操作（写/删/用户/上传/AI配置）一律不挂。
# Dify/n8n 以 MCP Client 连 http://<host>:8002/mcp 即可调这些工具。
from fastapi_mcp import FastApiMCP

_MCP_READ_OPERATIONS = [
    # 机台状态
    "list_machines", "get_machine", "machine_stats",
    # 实时事件（EAP LOG）
    "get_events", "get_latest_events", "get_event_timeline",
    # 告警
    "list_alarms", "alarm_stats",
    # 批次 / MES
    "list_lots", "get_lot", "get_lot_events",
    # 历史回溯
    "get_history", "get_history_timeline", "get_alarm_history", "get_event_detail",
    # OXE 事件
    "get_latest_event", "get_history_events",
    # OHT / 配方 / 布局 / 型号 / RV 消息
    "get_oht_positions", "get_oht_history",
    "get_recipes", "get_recipe",
    "list_floors", "get_floor", "get_floor_machines",
    "list_models", "get_model",
    "get_current_rv", "get_rv_history",
]

mcp = FastApiMCP(app, include_operations=_MCP_READ_OPERATIONS)
mcp.mount_http()  # Streamable HTTP，默认 /mcp

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

    # test31：后台预载 whisper 语音模型（不依赖 DB，避免首次语音请求
    # 触发 75MB 下载 + 数秒加载）
    try:
        from services.speech_service import preload_in_background
        preload_in_background()
        print("[ASR] whisper 模型后台预载已启动")
    except Exception as _asr_err:
        print(f"[ASR] 预载启动失败（忽略，首次请求时会再试）: {_asr_err}")

    try:
        init_db()
        from database import engine
        print(f"[DB] Connected to: {engine.url}")
        print("[DB] 数据库初始化完成")

        # T4.5: 预热 DT 表时间列类型反射缓存。
        # machines._col_is_temporal / history._ts_columns_are_temporal 首次调用
        # 要 inspect 数据字典（Oracle 单表 400-800ms），不预热会全部叠加到第一个
        # 用户请求上（本地实测 /api/machines 冷态因此多耗 ~2s）。
        try:
            from routers.machines import _col_is_temporal
            from routers.history import _ts_columns_are_temporal
            _pw_db = SessionLocal()
            try:
                _ts_columns_are_temporal(_pw_db)
                for _t, _c in (
                    ("dt_alarm_event", "start_ts_utc"),
                    ("dt_event_raw", "event_ts_utc"),
                    ("dt_event_raw", "received_ts_utc"),
                ):
                    _col_is_temporal(_pw_db, _t, _c)
                print("[DB] 时间列反射缓存预热完成")
            finally:
                _pw_db.close()
        except Exception as _pw_err:
            print(f"[DB] 反射缓存预热失败（忽略，首个请求会兜底探测）: {_pw_err}")

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
