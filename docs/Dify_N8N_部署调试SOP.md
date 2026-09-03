# FabTwin + Dify + n8n 部署调试 SOP（Informix 版）

> 版本：v1.0  日期：2026-09-03
> 适用场景：RCMS 和 MES 均使用 IBM Informix 数据库
> 前置条件：FabTwin Pro 后端已部署运行（Oracle），Docker 已安装

***

## 〇、架构总览（为什么这样设计）

```
用户浏览器
  │
  ▼
FabTwin 前端 (Vue 3)  ←→  FabTwin 后端 (FastAPI:8002)
                              │
                    ┌─────────┼─────────────┐
                    ▼         ▼             ▼
               Oracle     Informix      Dify (Docker:8088)
             (机台/事件   (RCMS+MES     (AI 对话编排)
              /平面图)    数据查询)           │
                              │         ┌────┴────┐
                              │         ▼         ▼
                              │    API 工具    RAG 知识库
                              │    (14个)     (SOP文档)
                              │
                              ▼
                         n8n (Docker:5678)
                         (工作流自动化：
                          导出报表/邮件/工单)
```

**核心思路**：

- Informix 查询直接在 FabTwin 后端做（Dify/n8n 不直连 Informix）

- Dify 通过 API 工具调用 FabTwin 后端 → FabTwin 查 Informix → 返回 JSON

- n8n 负责工作流自动化（导出 CSV、发邮件、创建工单），后续按需配置

- 这样 Dify 和 n8n 都不需要安装 Informix 驱动，降低复杂度

***

## 一、环境准备

### 1.1 需要准备的机器/地址

| 服务              | 机器          | 端口       | 说明                 |
| --------------- | ----------- | -------- | ------------------ |
| FabTwin 后端      | 已部署         | 8002     | 已有                 |
| FabTwin 前端      | 已部署         | IIS/5173 | 已有                 |
| Oracle DB       | 已部署         | 1521     | 已有                 |
| Informix (RCMS) | 公司服务器       | 待确认      | 需提供 IP/端口/库名/用户/密码 |
| Informix (MES)  | 公司服务器       | 待确认      | 同上                 |
| Dify            | 新部署（Docker） | 8088     | 本 SOP 部署           |
| n8n             | 新部署（Docker） | 5678     | 本 SOP 部署           |
| LLM API         | 智谱/OpenAI   | -        | 需提供 API Key        |

### 1.2 需要你确认的信息清单

在开始前，请找 IT/DBA 确认以下信息（填在纸上记好）：

**RCMS Informix：**

- [ ] IP 地址：\_\_\_\_\_\_\_\_

- [ ] 端口：\_\_\_\_\_\_\_\_（Informix 默认 9088 或 1526）

- [ ] 服务名/实例名：\_\_\_\_\_\_\_\_（Informix 的 INFORMIXSERVER）

- [ ] 数据库名：\_\_\_\_\_\_\_\_

- [ ] 用户名：\_\_\_\_\_\_\_\_

- [ ] 密码：\_\_\_\_\_\_\_\_

- [ ] 有哪些表？（让 DBA 导出表名清单，或给你 `systables` 查询权限）

**MES Informix：**

- [ ] （同上 6 项）

**LLM API（选一个）：**

- [ ] 智谱 AI：到 <https://open.bigmodel.cn/> 注册，获取 API Key = \_\_\_\_\_\_\_\_

- [ ] OpenAI：API Key = \_\_\_\_\_\_\_\_

- [ ] 其他国内模型：\_\_\_\_\_\_\_\_

### 1.3 Docker 安装确认

```powershell
# 在准备部署 Dify/n8n 的服务器上运行
docker --version
docker compose version
docker info
```

如果报错，去 <https://www.docker.com/products/docker-desktop/> 下载安装 Docker Desktop。

***

## 二、在 FabTwin 后端增加 Informix 查询能力

### 2.1 安装 Informix Python 驱动

在 FabTwin 后端服务器上：

```powershell
# 方案A：用 ibm_db（IBM 官方驱动，推荐）
pip install ibm_db ibm_db_sa

# 方案B：如果 ibm_db 装不上，用 ODBC 方式
# 先安装 IBM Informix CSDK（从 IBM 官网下载）
# 然后：
pip install pyodbc
```

> **如果 pip install ibm\_db 失败**（Windows 常见）：
>
> 1. 去 <https://github.com/ibmdb/python-ibmdb/releases> 下载对应 Python 版本的 wheel 文件
> 2. 例：`ibm_db-3.1.5-cp311-cp311-win_amd64.whl`
> 3. `pip install ibm_db-3.1.5-cp311-cp311-win_amd64.whl`
> 4. 如果还是不行，用 ODBC 方案：安装 Informix CSDK → 配置 ODBC 数据源 → 用 pyodbc

### 2.2 在 config.py 增加 Informix 配置

在 `backend/config.py` 文件末尾追加：

```python
# ========== Informix 数据库配置（RCMS / MES）==========
INFORMIX_ENABLED = os.getenv("INFORMIX_ENABLED", "false").lower() == "true"

# RCMS Informix 连接参数
RCMS_INFORMIX_HOST = os.getenv("RCMS_INFORMIX_HOST", "")
RCMS_INFORMIX_PORT = int(os.getenv("RCMS_INFORMIX_PORT", "9088"))
RCMS_INFORMIX_SERVER = os.getenv("RCMS_INFORMIX_SERVER", "")  # INFORMIXSERVER
RCMS_INFORMIX_DB = os.getenv("RCMS_INFORMIX_DB", "")
RCMS_INFORMIX_USER = os.getenv("RCMS_INFORMIX_USER", "")
RCMS_INFORMIX_PASSWORD = os.getenv("RCMS_INFORMIX_PASSWORD", "")

# MES Informix 连接参数
MES_INFORMIX_HOST = os.getenv("MES_INFORMIX_HOST", "")
MES_INFORMIX_PORT = int(os.getenv("MES_INFORMIX_PORT", "9088"))
MES_INFORMIX_SERVER = os.getenv("MES_INFORMIX_SERVER", "")
MES_INFORMIX_DB = os.getenv("MES_INFORMIX_DB", "")
MES_INFORMIX_USER = os.getenv("MES_INFORMIX_USER", "")
MES_INFORMIX_PASSWORD = os.getenv("MES_INFORMIX_PASSWORD", "")

# 构建连接字符串
def _build_informix_conn_str(host, port, server, db, user, password):
    """构建 Informix ODBC 连接字符串"""
    return (
        f"DRIVER={{IBM INFORMIX ODBC DRIVER}};"
        f"HOST={host};SRVR={server};SERV={port};"
        f"PRO=onsoctcp;DB={db};UID={user};PWD={password};"
    )

RCMS_CONN_STR = _build_informix_conn_str(
    RCMS_INFORMIX_HOST, RCMS_INFORMIX_PORT, RCMS_INFORMIX_SERVER,
    RCMS_INFORMIX_DB, RCMS_INFORMIX_USER, RCMS_INFORMIX_PASSWORD
) if INFORMIX_ENABLED else ""

MES_CONN_STR = _build_informix_conn_str(
    MES_INFORMIX_HOST, MES_INFORMIX_PORT, MES_INFORMIX_SERVER,
    MES_INFORMIX_DB, MES_INFORMIX_USER, MES_INFORMIX_PASSWORD
) if INFORMIX_ENABLED else ""
```

### 2.3 创建 Informix 查询路由文件

新建 `backend/routers/external.py`：

```python
"""外部系统数据查询（Informix: RCMS / MES）

提供 API 端点供 Dify 工具调用，也供前端直接使用。
所有查询返回统一 JSON 格式。
"""
import pyodbc
from fastapi import APIRouter, Query
from config import (
    INFORMIX_ENABLED, RCMS_CONN_STR, MES_CONN_STR,
)

router = APIRouter(prefix="/api/external", tags=["external"])


def _query_informix(conn_str: str, sql: str, params: list = None):
    """执行 Informix SQL 查询，返回 dict 列表"""
    if not INFORMIX_ENABLED:
        return {"error": "Informix 未启用", "data": []}
    try:
        with pyodbc.connect(conn_str, timeout=10) as conn:
            conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            conn.setencoding(encoding='utf-8')
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            columns = [desc[0] for desc in cursor.description]
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(columns, row)))
            return {"data": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e), "data": []}


# ========== RCMS 查询接口 ==========

@router.get("/rcms/maintenance")
def get_rcms_maintenance(
    machine_id: str = Query(..., description="机台ID"),
    limit: int = Query(10, description="返回条数")
):
    """查询机台维修/PM记录（RCMS Informix）

    供 Dify 工具 get_rcms_maintenance 调用。
    """
    # TODO: 确认 RCMS 实际表名和字段后修改 SQL
    sql = """
        SELECT FIRST ? 
            machine_id, maint_type, maint_date, description,
            technician, status, work_order_no
        FROM maintenance_log
        WHERE machine_id = ?
        ORDER BY maint_date DESC
    """
    result = _query_informix(RCMS_CONN_STR, sql, [limit, machine_id])
    return result


@router.get("/rcms/work-order")
def get_rcms_work_order(
    machine_id: str = Query(None, description="机台ID（可选）"),
    status: str = Query(None, description="状态过滤：open/closed")
):
    """查询工单状态（RCMS Informix）

    供 Dify 工具 get_rcms_work_order 调用。
    """
    sql = "SELECT * FROM work_order WHERE 1=1"
    params = []
    if machine_id:
        sql += " AND machine_id = ?"
        params.append(machine_id)
    if status == "open":
        sql += " AND status NOT IN ('CLOSED','DONE')"
    elif status == "closed":
        sql += " AND status IN ('CLOSED','DONE')"
    sql += " ORDER BY created_at DESC"
    result = _query_informix(RCMS_CONN_STR, sql, params)
    return result


# ========== MES 查询接口 ==========

@router.get("/mes/lot-info")
def get_mes_lot_info(
    lot_id: str = Query(..., description="Lot ID")
):
    """查询 Lot MES 信息（MES Informix）

    供 Dify 工具 get_mes_lot_info 调用。
    """
    # TODO: 确认 MES 实际表名和字段后修改 SQL
    sql = """
        SELECT 
            lot_id, product_id, route_id, current_step,
            status, wafer_qty, start_time, expected_end_time
        FROM lot_info
        WHERE lot_id = ?
    """
    result = _query_informix(MES_CONN_STR, sql, [lot_id])
    return result


@router.get("/mes/product-route")
def get_mes_product_route(
    product_id: str = Query(..., description="产品ID")
):
    """查询产品工艺路线（MES Informix）

    供 Dify 工具 get_mes_product_route 调用。
    """
    # TODO: 确认 MES 表名
    sql = """
        SELECT 
            step_no, step_name, machine_type, expected_time
        FROM product_route
        WHERE product_id = ?
        ORDER BY step_no
    """
    result = _query_informix(MES_CONN_STR, sql, [product_id])
    return result


@router.get("/mes/wip")
def get_mes_wip(
    machine_id: str = Query(None, description="机台ID（可选）"),
    line_id: str = Query(None, description="产线ID（可选）")
):
    """查询在制品 WIP（MES Informix）

    供 Dify 工具 get_mes_wip 调用。
    """
    sql = "SELECT * FROM wip_lot WHERE 1=1"
    params = []
    if machine_id:
        sql += " AND machine_id = ?"
        params.append(machine_id)
    sql += " ORDER BY start_time DESC"
    result = _query_informix(MES_CONN_STR, sql, params)
    return result


# ========== 健康检查 ==========

@router.get("/health")
def external_health_check():
    """检查 Informix 连接状态"""
    status = {"informix_enabled": INFORMIX_ENABLED}
    if INFORMIX_ENABLED:
        rcms = _query_informix(RCMS_CONN_STR, "SELECT FIRST 1 1 FROM systables")
        mes = _query_informix(MES_CONN_STR, "SELECT FIRST 1 1 FROM systables")
        status["rcms_connected"] = "error" not in rcms
        status["mes_connected"] = "error" not in mes
    return status
```

### 2.4 在 main.py 注册新路由

在 `backend/main.py` 的 routers 导入行追加：

```python
from routers import machines, events, lots, alarms, ai, oht, recipes, floors, models, history, auth, users, uploads, oxe, external
```

在路由注册行追加（找到 `app.include_router` 那段）：

```python
app.include_router(external.router)
```

### 2.5 在 requirements.txt 追加依赖

```
pyodbc>=5.0.0
```

（或 `ibm_db>=3.1.0` 如果用 ibm\_db 方式）

### 2.6 配置环境变量并重启

在 FabTwin 后端的启动脚本或环境变量中增加：

```powershell
$env:INFORMIX_ENABLED = "true"
$env:RCMS_INFORMIX_HOST = "实际IP"
$env:RCMS_INFORMIX_PORT = "实际端口"
$env:RCMS_INFORMIX_SERVER = "实际server名"
$env:RCMS_INFORMIX_DB = "实际库名"
$env:RCMS_INFORMIX_USER = "实际用户"
$env:RCMS_INFORMIX_PASSWORD = "实际密码"
$env:MES_INFORMIX_HOST = "实际IP"
$env:MES_INFORMIX_PORT = "实际端口"
$env:MES_INFORMIX_SERVER = "实际server名"
$env:MES_INFORMIX_DB = "实际库名"
$env:MES_INFORMIX_USER = "实际用户"
$env:MES_INFORMIX_PASSWORD = "实际密码"
```

重启 FabTwin 后端，然后测试：

```powershell
# 健康检查
curl http://localhost:8002/api/external/health

# 查询某 Lot 的 MES 信息（确认表名后）
curl "http://localhost:8002/api/external/mes/lot-info?lot_id=NT938.15"

# 查询机台维修记录
curl "http://localhost:8002/api/external/rcms/maintenance?machine_id=OXE-01"
```

> **重要**：`external.py` 中的 SQL（表名 `maintenance_log`、`work_order`、`lot_info`、`product_route`、`wip_lot`）是**示例表名**。
> 你需要找 DBA 确认 RCMS 和 MES 中的实际表名和字段名，然后修改 SQL。
> 可以先用 `SELECT * FROM systables WHERE tabtype = 'T'` 查看所有用户表。

***

## 三、部署 Dify（Docker）

### 3.1 执行部署

在部署服务器上，以管理员打开 PowerShell：

```powershell
cd "C:\路径\到\fab-twin-pro\deploy"

# 安装 Dify（默认端口 8088）
powershell -ExecutionPolicy Bypass -File .\deploy_dify.ps1 -Action install
```

等待 Docker 拉取镜像并启动，约 5-10 分钟。

### 3.2 验证 Dify 启动

```powershell
# 检查容器状态
powershell -ExecutionPolicy Bypass -File .\deploy_dify.ps1 -Action status

# 应看到 7 个容器全部 Up：
# nginx / web / api / worker / db(postgres) / redis / weaviate
```

浏览器打开 `http://localhost:8088`：

1. 首次访问会提示创建管理员账号
2. 邮箱：自己的工作邮箱
3. 密码：设一个强密码并记住

### 3.3 配置模型供应商

1. 登录 Dify → 左下角「设置」（齿轮图标）
2. 进入「模型供应商」
3. 找到「智谱 AI」（或你选的供应商）
4. 点击添加 → 填入 API Key（从 <https://open.bigmodel.cn/> 获取）
5. 在「模型」列表中启用：

   - `glm-4-plus`（对话用）

   - `embedding-3`（RAG 知识库用，必须启用否则知识库无法创建）
6. 点「连接测试」→ 绿灯 OK

### 3.4 导入 FabTwin AI 助手模板

1. 在 Dify「工作室」首页 → 右上角「创建应用」→「从 DSL 导入」
2. 上传文件：`docs/integration/dify/fabtwin-ai-assistant.dsl.yaml`
3. 等待导入完成，应用名「FabTwin AI Assistant」

**导入后 5 项必检**：

- [ ] 提示词编辑器有文字（开头是「你是 FabTwin Pro 半导体产线数字孪生平台的 AI 助手」）

- [ ] 变量区域有 `machine_id`（文本输入）+ `user_role`（下拉）

- [ ] 开场白显示「👋 你好！我是 FabTwin Pro 数字孪生 AI 助手」

- [ ] 左上角**没有** AGENT 标签

- [ ] 知识库 → `retriever_resource` 已开启

**切换模型**：

1. 进入应用 → 右上角「设置」→「模型和供应商」
2. 选你 Step 3.3 配置的模型（如 `glm-4-plus`）
3. Temperature: 0.3
4. Max Tokens: 2048
5. 保存

***

## 四、在 Dify 中配置 API 工具（14 个）

> **重要概念**：Dify 的「工具」就是让 AI 能调用外部 API。
> 你的 FabTwin 后端已经有 14 个 API 端点（9 个原有 + 5 个 Informix 新增），
> 需要在 Dify 中逐个配置，让 AI 能调用它们。

### 4.1 获取 FabTwin API Token

```powershell
# 在 FabTwin 后端服务器上执行
curl -X POST http://localhost:8002/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"admin123"}'
# 返回的 token 复制保存
```

### 4.2 方法A（推荐）：通过 OpenAPI 批量导入

1. 浏览器打开 `http://你的FabTwin后端地址:8002/openapi.json` → 另存为 JSON 文件
2. Dify → 「工作室」→「工具」→「添加工具」→「OpenAPI/Swagger」
3. 上传 JSON 文件
4. 勾选以下 14 个接口：

   - `get_machine_status`（GET /api/machines/{machine\_id}）

   - `get_machine_alarms`（GET /api/ai/alarms）

   - `get_event_timeline`（GET /api/events）

   - `get_yield_stats`（GET /api/ai/yield-stats）

   - `get_lot_info`（GET /api/lots）

   - `get_recipe_info`（GET /api/recipes）

   - `get_wafer_flow`（GET /api/oxe/wafer-flow）

   - `get_chamber_status`（GET /api/oxe/chamber-status）

   - `get_oxe_lot_summary`（GET /api/oxe/lot-summary）

   - `get_rcms_maintenance`（GET /api/external/rcms/maintenance）

   - `get_rcms_work_order`（GET /api/external/rcms/work-order）

   - `get_mes_lot_info`（GET /api/external/mes/lot-info）

   - `get_mes_product_route`（GET /api/external/mes/product-route）

   - `get_mes_wip`（GET /api/external/mes/wip）
5. 鉴权方式：选 **API Key**

   - Header 名：`Authorization`

   - 值：`Bearer 你刚才获取的Token`
6. 点「保存」

### 4.3 方法B（备选）：逐个手动添加

如果方法A失败，逐个点「添加工具 → API 扩展」配置。

**以** **`get_mes_lot_info`** **为例**：

| 配置项  | 填写内容                                                  |
| ---- | ----------------------------------------------------- |
| 工具名称 | `get_mes_lot_info`                                    |
| 描述   | 查询 MES 系统 Lot 信息，包括产品、工艺步骤、状态、晶圆数量。需要 lot\_id。        |
| 请求方式 | GET                                                   |
| URL  | `http://你的FabTwin后端地址:8002/api/external/mes/lot-info` |
| 鉴权   | Header: `Authorization` = `Bearer 你的Token`            |
| 参数   | `lot_id`（string，必填，"Lot ID 如 NT938.15"）               |

配置完点「测试」，确认返回 JSON 数据。

### 4.4 将工具添加到应用

1. 回到「FabTwin AI Assistant」→「编排」
2. 找到「工具」区域 → 点「+ 添加」
3. 选中刚导入的 14 个工具 → 确认

### 4.5 创建 RAG 知识库

1. Dify 顶部菜单 →「知识库」→「创建知识库」
2. 名称：`OXE-Etcher-SOP`，权限：仅工作室成员
3. 上传文件：`docs/integration/dify/knowledgebase/OXE_Etcher_SOP_v1.0.md`
4. 索引方式：高质量（推荐）
5. Embedding 模型：选 `embedding-3`
6. 分段：最大 500 tokens，重叠 50 tokens
7. 点「保存并处理」→ 等 1-2 分钟
8. 测试检索：输入「OXE Chamber 颗粒偏高怎么排查？」→ 应命中
9. 回到应用 → 编排 → 知识库 → 关联 `OXE-Etcher-SOP`

***

## 五、连接 FabTwin 与 Dify

### 5.1 获取 Dify API Key

1. Dify →「FabTwin AI Assistant」应用 → 左上角「访问 API」
2. 点「创建 API Key」→ 名称 `fabtwin-backend`
3. **复制保存**（只显示一次！），格式：`app-xxxxxxxxxxxxxxxx`
4. 记录 API 地址：`http://你的Dify地址:8088/v1`

### 5.2 在 FabTwin 配置面板填写

1. 浏览器打开 FabTwin → 用 admin 登录
2. 进入「AI 配置管理」（用户管理旁边）
3. 切换到 **Dify/N8N** Tab
4. 填写：

   - ✅ 启用 Dify

   - Dify 服务地址：`http://你的Dify地址:8088/v1`（末尾不加 `/chat-messages`）

   - Dify API 密钥：粘贴刚才的 Key

   - Dify 应用 ID：留空
5. 点「测试连接」→ 预期提示：`Dify 连接成功`
6. 保存

### 5.3 切换 Provider

在「模型配置」Tab：

- Provider 选 **Hybrid**（Dify 失败自动回退本地规则引擎，生产推荐）

- 保存

***

## 六、端到端测试（3 条链路）

在 FabTwin 中测试：

### 测试 1：FabTwin 已有数据查询

```
打开任一 OXE 机台详情页 → 点击 AI 悬浮球 → 输入：
"这台机现在的状态怎样？"
```

预期：AI 调用 `get_machine_status` 工具，返回机台状态，回答底部显示 Provider: Hybrid/Dify

### 测试 2：RAG 知识库问答

```
输入：
"OXE 做 PM-A 周期是多少？"
```

预期：AI 从知识库检索 SOP 文档，回答引用 PM 表格，消息下方显示 RAG 引用来源

### 测试 3：Informix 数据查询（RCMS/MES）

```
输入：
"查一下 NT938.15 这个 lot 的 MES 信息"
```

预期：AI 调用 `get_mes_lot_info` 工具 → FabTwin 后端查 Informix → 返回 Lot 产品/步骤/状态

> 如果返回错误：检查 Informix 连接是否正常（`/api/external/health`）、SQL 表名是否正确

### 测试 4：跳转回放

```
输入：
"查 OXE-01 最近 24h 的报警"
```

预期：AI 返回告警列表，回答末尾有 `[JUMP: 时间] [MACHINE: OXE-01]` 标记被后端解析，
前端显示「跳转到历史回放」按钮，点击后回放自动 seek 到该时间点

***

## 七、部署 n8n（Docker）

### 7.1 执行部署

```powershell
cd "C:\路径\到\fab-twin-pro\deploy"

# 安装 n8n（默认端口 5678）
powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action install
```

### 7.2 验证 n8n 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action status
# 应看到 2 个容器 Up：n8n + postgres
```

浏览器打开 `http://localhost:5678`：

1. 首次访问设置管理员账号
2. 邮箱/密码设好并记住

### 7.3 n8n 的用途

n8n 在你的架构中用于**工作流自动化**，不是用来查 Informix 的。
后续可以做的 n8n 工作流：

| 工作流    | 触发方式           | 做什么                             |
| ------ | -------------- | ------------------------------- |
| 导出告警报表 | AI 对话关键词「导出告警」 | 调 FabTwin API → 生成 CSV → 返回下载链接 |
| 发送邮件日报 | 定时（每天 18:00）   | 汇总当日数据 → 发邮件                    |
| 创建维修工单 | AI 对话关键词「创建工单」 | 调 RCMS API → 创建工单 → 返回工单号       |

**n8n 的配置可以等 Dify + Informix 跑通后再做**，不影响主流程。

***

## 八、Dify 提示词调优指南

如果 AI 回答不理想，在 Dify「FabTwin AI Assistant → 编排 → 提示词」中调整：

### 常见问题与调优

| 问题             | 调优方法                                                                         |
| -------------- | ---------------------------------------------------------------------------- |
| AI 不调用工具       | 提示词中强调：「如果用户询问机台状态/Lot/告警等信息，必须调用对应工具获取数据，不要凭空回答」                            |
| AI 总问机台ID      | 提示词中强调：「如果 {{machine\_id}} 变量非空，说明用户在机台详情页提问，直接使用此ID，不要反问用户」                 |
| 跳转按钮不出现        | 确认回答末尾有 `[JUMP: YYYY-MM-DD HH:MM:SS] [MACHINE: 机台ID]`，且时间格式正确                |
| Informix 数据查不到 | 确认 FabTwin 后端 Informix 连接正常（`/api/external/health` 返回 rcms\_connected: true） |
| RAG 无引用来源      | 确认知识库已关联到应用（编排 → 知识库 → 关联）                                                   |
| 回答太长           | 提示词加「回答简洁，重点突出，不超过 200 字」                                                    |
| 回答不专业          | 提示词加行业术语要求：「使用半导体行业用语，如 Chamber/Lot/Wafer/PM/CQ 等」                           |

***

## 九、故障排查速查表

| 现象                  | 可能原因                         | 处理                                           |
| ------------------- | ---------------------------- | -------------------------------------------- |
| FabTwin AI 回答显示本地规则 | Dify 未启用或 Provider 未切 Hybrid | AI 配置面板 → 启用 Dify + 切 Hybrid                 |
| Dify 测试连接失败 401     | API Key 错误                   | Dify 应用 → 访问 API → 重新创建 Key                  |
| Dify 工具调用失败         | FabTwin 后端不可达或 Token 过期      | 检查 FabTwin 后端运行状态；重新获取 Token                 |
| Informix 查询报错       | ODBC 驱动未装 / 表名错误             | 安装 Informix CSDK；用 `/api/external/health` 诊断 |
| Dify 容器不断重启         | 内存不足                         | `docker stats` 确认内存；Dify 至少需 8GB             |
| RAG 检索命中率低          | 分段过大 / 无 Rerank              | 改 500 段 + 开 Rerank                           |
| n8n Webhook 不通      | 端口未开放 / 防火墙                  | 检查 Docker 端口映射；防火墙放行                         |
| AI 回答没有跳转按钮         | Dify 提示词未约束输出格式              | 确认提示词中有 `[JUMP: xxx] [MACHINE: xxx]` 格式说明    |
| Informix ODBC 驱动找不到 | 未安装 IBM CSDK                 | 从 IBM 官网下载 Informix CSDK 并安装                 |

***

## 十、执行顺序总结

```
第一阶段（让 Dify 跑起来 + 基础工具）
  ① 确认 Docker 已装 → 部署 Dify（§三）
  ② 配置模型供应商 + 导入 DSL 模板（§3.3-3.4）
  ③ 在 Dify 配置 9 个 FabTwin 原有 API 工具（§4.2-4.4）
  ④ 配置 RAG 知识库（§4.5）
  ⑤ 在 FabTwin 面板填 Dify Key + 测连接（§五）
  ⑥ 测试链路 1-2-4（§六）
  → 此时 AI 能查 FabTwin Oracle 数据 + RAG 知识库 + 跳转回放

第二阶段（接通 Informix）
  ⑦ 找 DBA 确认 Informix 连接信息和表名（§1.2）
  ⑧ 装 Informix Python 驱动 + 加配置（§2.1-2.2）
  ⑨ 创建 external.py 路由 + 修改 SQL 表名（§2.3）
  ⑩ 重启后端 + 测试 Informix 查询（§2.6）
  ⑪ 在 Dify 加 5 个 Informix 工具（§4.2-4.3）
  ⑫ 测试链路 3（§六）
  → 此时 AI 能查 RCMS/MES Informix 数据

第三阶段（n8n 工作流，后续按需）
  ⑬ 部署 n8n（§七）
  ⑭ 创建工作流（导出报表/邮件/工单等）
  → 此时 AI 能触发自动化工作流
```

***

## 附录 A：环境变量完整清单

在 FabTwin 后端服务器配置以下环境变量（用于 NSSM 服务或启动脚本）：

```powershell
# ===== Oracle（已有）=====
$env:DB_TYPE = "oracle"
$env:ORACLE_HOST = "..."
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "..."
$env:ORACLE_USER = "..."
$env:ORACLE_PASSWORD = "..."

# ===== Informix（新增）=====
$env:INFORMIX_ENABLED = "true"
$env:RCMS_INFORMIX_HOST = "RCMS的IP"
$env:RCMS_INFORMIX_PORT = "9088"
$env:RCMS_INFORMIX_SERVER = "RCMS的server名"
$env:RCMS_INFORMIX_DB = "RCMS的库名"
$env:RCMS_INFORMIX_USER = "RCMS的用户"
$env:RCMS_INFORMIX_PASSWORD = "RCMS的密码"
$env:MES_INFORMIX_HOST = "MES的IP"
$env:MES_INFORMIX_PORT = "9088"
$env:MES_INFORMIX_SERVER = "MES的server名"
$env:MES_INFORMIX_DB = "MES的库名"
$env:MES_INFORMIX_USER = "MES的用户"
$env:MES_INFORMIX_PASSWORD = "MES的密码"
```

## 附录 B：Informix 常用排查 SQL

```sql
-- 查看所有用户表
SELECT tabname FROM systables WHERE tabtype = 'T' ORDER BY tabname;

-- 查看表结构（列名/类型）
SELECT colname, coltype, collength
FROM syscolumns
WHERE tabid = (SELECT tabid FROM systables WHERE tabname = '你的表名')
ORDER BY colno;

-- 测试连接
SELECT FIRST 1 1 FROM systables;
```

## 附录 C：文件变更清单

| 文件                                                    | 操作  | 说明                     |
| ----------------------------------------------------- | --- | ---------------------- |
| `backend/config.py`                                   | 修改  | 追加 Informix 连接配置       |
| `backend/routers/external.py`                         | 新建  | Informix RCMS/MES 查询接口 |
| `backend/main.py`                                     | 修改  | 注册 external 路由         |
| `backend/requirements.txt`                            | 修改  | 追加 pyodbc              |
| `docs/integration/dify/fabtwin-ai-assistant.dsl.yaml` | 已更新 | 9 工具描述 + 跳转标记格式        |
| `backend/services/ai_middleware.py`                   | 已更新 | \_call\_dify 跳转标记解析    |

> 注：config.py / external.py / main.py / requirements.txt 的修改需要你确认 Informix 连接信息后执行。
> DSL 和 ai\_middleware.py 的修改已 commit 到 test1 分支。

