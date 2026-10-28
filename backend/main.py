"""FabTwin 半导体厂数字孪生 - FastAPI 入口"""
import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

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
from services.perf import router as perf_router
from services.perf import install as install_perf, install_sql_timing

# T8：operation_id 统一用函数名（默认会拼路径后缀，如 list_machines_api_machines_get），
# 让 MCP 工具名保持 list_machines / get_machine 这种干净命名。
# 前端只按 URL 调接口，不消费 operationId，无副作用。
# ========== 启动时初始化 ==========
# 2026-10-29 修复：原来是同步 `def on_startup()`，Starlette 会把它丢进线程池执行，
# 线程池里没有事件循环 → asyncio.create_task() 抛 "no running event loop"，
# 又被下面的 except 当成"数据库初始化失败"吞掉（此时 init_db 其实已成功），
# 导致 db_poller / simulator 从未真正启动。改用 async lifespan 后二者都在事件循环内创建。
def _startup_blocking():
    """所有阻塞型初始化（DDL / 建表 / 种子数据）。在 asyncio.to_thread 里跑，不冻事件循环。"""
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

    # test31：whisper 预载改为环境变量开关（WHISPER_PRELOAD=1 显式开启）。
    # 实测本机在服务运行中并发预载 ctranslate2 会触发进程段错误（独立进程加载正常，
    # 疑似多 DLL 线程竞态）；默认关闭保稳定，首次语音请求时在工作线程内加载。
    if os.getenv("WHISPER_PRELOAD", "").strip().lower() in ("1", "true", "yes"):
        try:
            from services.speech_service import preload_in_background
            preload_in_background()
            print("[ASR] whisper 模型后台预载已启动")
        except Exception as _asr_err:
            print(f"[ASR] 预载启动失败（忽略，首次请求时会再试）: {_asr_err}")
    else:
        print("[ASR] whisper 预载未开启（设置 WHISPER_PRELOAD=1 可开启）")

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

    except Exception as e:
        print(f"[WARN] 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        print("[WARN] 将以降级模式启动，部分功能可能不可用")

    # SQL 计时钩子要挂在 engine 上，等 init_db 建好 engine 之后再挂
    try:
        from database import engine as _engine
        install_sql_timing(_engine)
        print("[perf] SQL 计时钩子已挂载")
    except Exception as _perf_err:
        print(f"[perf] SQL 计时钩子挂载失败（忽略）: {_perf_err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：阻塞初始化丢线程，后台任务在事件循环内创建；关闭：统一取消并回收。"""
    await asyncio.to_thread(_startup_blocking)

    bg_tasks = []
    try:
        if SIMULATION_ENABLED:
            bg_tasks.append(asyncio.create_task(start_simulator(manager, cache)))
            print("[Simulator] 模拟器已启动")
    except Exception as e:
        print(f"[WARN] 模拟器启动失败: {e}")

    if DB_POLLER_ENABLED:
        try:
            bg_tasks.append(asyncio.create_task(start_db_poller()))
            print("[DB Poller] DB事件轮询服务已启动")
        except Exception as e:
            print(f"[WARN] DB轮询服务启动失败: {e}")
            import traceback
            traceback.print_exc()

    print(f"[API] 服务运行在 http://{API_HOST}:{API_PORT}")
    print(f"[API] 文档地址: http://{API_HOST}:{API_PORT}/docs")
    print("========== 启动完成 ==========")

    yield

    print("========== FabTwin 关闭 ==========")
    for t in bg_tasks:
        t.cancel()
    if bg_tasks:
        await asyncio.gather(*bg_tasks, return_exceptions=True)


app = FastAPI(
    title="FabTwin API",
    version="1.0",
    lifespan=lifespan,
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
app.include_router(perf_router, tags=["metrics"])

# 性能观测中间件（请求耗时 / 慢查询）
install_perf(app)

# ========== MCP（T8）：把内部只读 API 注册为标准 MCP 工具 ==========
# 选择性暴露：只挂读类/跳转类，管理操作（写/删/用户/上传/AI配置）一律不挂。
# Dify/n8n 以 MCP Client 连 http://<host>:8002/mcp 即可调这些工具。
#
# 2026-10-29：MCP 是可选集成，不该成为后端启动的硬依赖——原先 fastapi_mcp 缺包或
# 版本不兼容时，import 失败会直接让整个后端起不来（含机台看板等核心功能）。
# 改为软依赖：装了就挂 /mcp，没装就跳过并打印提示。
try:
    from fastapi_mcp import FastApiMCP
    _MCP_AVAILABLE = True
except Exception as _mcp_import_err:
    FastApiMCP = None
    _MCP_AVAILABLE = False
    print(f"[MCP] fastapi_mcp 不可用，跳过 /mcp 挂载（不影响其他功能）: {_mcp_import_err}")

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

if _MCP_AVAILABLE:
    mcp = FastApiMCP(app, include_operations=_MCP_READ_OPERATIONS)
    mcp.mount_http()  # Streamable HTTP，默认 /mcp
else:
    mcp = None

# 2026-10-29 安全修复：/mcp 上的 35 个只读接口此前完全无鉴权，工厂生产数据对外裸奔。
# 在 MCP 挂载之后插入鉴权中间件，要求：
#   - 设置了 FABTWIN_INGEST_API_KEY → 携带匹配的 X-API-Key 或 Bearer
#   - 未设置 → 仅允许本机/内网来源（Dify/n8n 与后端同机部署时行为不变）
@app.middleware("http")
async def _mcp_auth_middleware(request, call_next):
    if request.url.path.startswith("/mcp"):
        from routers.rvmessages import _ingest_key, _client_is_local
        import hmac as _hmac
        expected = _ingest_key()
        if expected:
            provided = request.headers.get("X-API-Key", "")
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided = provided or auth_header[7:].strip()
            if not _hmac.compare_digest(provided, expected):
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-API-Key"})
        elif not _client_is_local(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "MCP 访问需要鉴权：请设置 FABTWIN_INGEST_API_KEY 并携带 X-API-Key"},
            )
    return await call_next(request)

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

# ========== 健康检查 ==========
@app.get("/health")
async def health():
    """探活：真实检查 DB 连通性 + 后台轮询任务存活，不再无条件返回 ok。"""
    checks = {"api": "ok"}
    status_code = 200

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1 FROM DUAL"))
            checks["db"] = "ok"
        finally:
            db.close()
    except Exception as e:
        checks["db"] = f"error: {type(e).__name__}"
        status_code = 503

    if DB_POLLER_ENABLED:
        from services.db_poller import poller_health
        ph = poller_health()
        checks["db_poller"] = ph
        if ph.get("status") != "ok":
            status_code = 503

    return JSONResponse(status_code=status_code, content={"status": "ok" if status_code == 200 else "degraded", "service": "fabtwin", "checks": checks})

# ========== 运行服务 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
