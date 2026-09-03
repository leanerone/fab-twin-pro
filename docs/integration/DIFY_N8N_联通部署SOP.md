# FabTwin Dify + n8n 部署联通 SOP（完整版）

> **版本**: v2.0（2026-09-03，合并旧版多份分散文档，全部重新梳理）
> **适用**: 已部署 Dify 和 n8n，需从零配置到与 FabTwin 网站联通
> **预计步骤**: 6 大步，逐步导入调试，直至端到端联通

---

## 目录

1. [架构总览](#1-架构总览)
2. [第1步：部署 DB Proxy 服务](#第1步部署-db-proxy-服务)
3. [第2步：导入 n8n 工作流（7个）](#第2步导入-n8n-工作流7个)
4. [第3步：创建 Dify 智能体](#第3步创建-dify-智能体)
5. [第4步：配置 Dify 工具（接入 n8n）](#第4步配置-dify-工具接入-n8n)
6. [第5步：网站后端配置](#第5步网站后端配置)
7. [第6步：端到端调试](#第6步端到端调试)
8. [故障排查](#故障排查)

---

## 1. 架构总览

```
用户在 FabTwin 网站提问
        │
        ▼
FabTwin 后端 (ai_middleware.py)
        │  调用 Dify Chat API
        ▼
┌───────────────────────────┐
│  Dify（AI 中枢）           │
│  · 理解自然语言             │
│  · 决定调用哪个工具          │
│  · 整合结果生成回答          │
│  · 输出跳转标记              │
└───────────┬───────────────┘
            │ 调用工具（HTTP）
            ▼
┌───────────────────────────┐
│  n8n（数据通道）            │
│  · 7 个工作流               │
│  · 接收 Dify 请求            │
│  · 调用 DB Proxy            │
│  · 格式化返回               │
└───────────┬───────────────┘
            │ HTTP 请求
            ▼
┌───────────────────────────┐
│  DB Proxy（数据库代理）      │
│  · 查询 Oracle（FabTwin）    │
│  · 查询 Informix（RCMS/MES） │
└───────────┬───────────────┘
            │ SQL
            ▼
    Oracle + Informix 数据库
```

**核心原则**：
- Dify 负责 AI 逻辑（理解、决策、回答生成）
- n8n 负责数据通道（工作流编排、格式化）
- DB Proxy 负责数据库查询（统一连接池、安全令牌）
- 网站仅负责显示和跳转执行，**不直接查数据库**

### 组件清单

| 组件 | 端口 | 作用 | 对应文件 |
|------|------|------|----------|
| DB Proxy | 8010 | 数据库代理 | `db-proxy/db_proxy.py` |
| n8n | 5678 | 工作流引擎 | `n8n/01~07_*.json`（7个） |
| Dify | 3000 | AI 中枢 | `dify/fabtwin-ai-assistant.dsl.yaml` |
| FabTwin 后端 | 8000 | 网站服务 | `backend/services/ai_middleware.py` |

### 文件目录结构

```
docs/integration/
├── DIFY_N8N_联通部署SOP.md        ← 本文件（唯一 SOP）
├── db-proxy/
│   ├── db_proxy.py               ← DB Proxy 服务
│   ├── requirements.txt          ← Python 依赖
│   └── start.ps1                 ← 启动脚本
├── n8n/
│   ├── 01_query_alarms.json      ← 告警查询工作流
│   ├── 02_query_machine_status.json ← 机台状态工作流
│   ├── 03_query_events.json      ← 事件时间线工作流
│   ├── 04_query_lots.json        ← Lot查询工作流
│   ├── 05_query_yield.json       ← 产量统计工作流
│   ├── 06_query_rcms_maintenance.json ← RCMS维修工作流
│   └── 07_query_mes_lot.json     ← MES Lot工作流
└── dify/
    ├── fabtwin-ai-assistant.dsl.yaml ← Dify 应用模板
    ├── fabtwin-tools-openapi.yaml   ← 7个工具的 OpenAPI 定义
    └── system_prompt.md             ← 系统提示词（参考）
```

---

## 第1步：部署 DB Proxy 服务

DB Proxy 是独立的 FastAPI 服务，负责统一查询 Oracle 和 Informix 数据库。

### 1.1 安装 Python 依赖

```powershell
cd "C:\FabTwin\fab-twin-pro\docs\integration\db-proxy"
pip install -r requirements.txt
```

`requirements.txt` 内容：
```
fastapi
uvicorn
oracledb
pyodbc
```

> **Informix 驱动**：pyodbc 需要 IBM Informix ODBC Driver 已安装。如果暂不使用 RCMS/MES 查询，可先跳过 Informix 配置，只使用 Oracle 查询。

### 1.2 配置数据库连接

编辑 `start.ps1`，填入实际数据库连接信息：

```powershell
# Oracle 配置（FabTwin 数据库）
$env:ORACLE_HOST = "10.30.116.xxx"      # ← 改为实际 Oracle IP
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "orcl"             # ← 改为实际服务名
$env:ORACLE_USER = "fabtwin"             # ← 改为实际用户名
$env:ORACLE_PASSWORD = "your-password"   # ← 改为实际密码

# Oracle Thick 模式（10g/11g 必须配置）
$env:ORACLE_CLIENT_DIR = "C:\oracle\instantclient_19_9"  # ← 64位 Oracle Client 路径

# Informix 配置（RCMS/MES 数据库，暂不使用可留空）
$env:INFORMIX_SERVER = ""
$env:INFORMIX_HOST = ""
$env:INFORMIX_PORT = "9088"
$env:INFORMIX_DATABASE = ""
$env:INFORMIX_USER = ""
$env:INFORMIX_PASSWORD = ""

# 安全配置
$env:DB_PROXY_PORT = "8010"
$env:DB_PROXY_TOKEN = "fabtwin-db-proxy-secret"  # ← 访问令牌，与 n8n 中保持一致
```

### 1.3 启动 DB Proxy

```powershell
.\start.ps1
```

看到以下输出表示启动成功：
```
[DB Proxy] 启动中... 端口 8010
[DB Proxy] Oracle: 10.30.116.xxx:1521/orcl
[DB Proxy] Informix: 未配置  （或显示配置信息）
INFO:     Uvicorn running on http://0.0.0.0:8010
```

### 1.4 验证 DB Proxy

打开浏览器访问：`http://localhost:8010/health`

返回：
```json
{"status": "ok", "time": "2026-09-03 15:30:00"}
```

用 PowerShell 测试告警查询接口：
```powershell
$headers = @{ "Authorization" = "Bearer fabtwin-db-proxy-secret"; "Content-Type" = "application/json" }
$body = '{"machine_id": "OXE-01", "limit": 5}'
Invoke-RestMethod -Uri "http://localhost:8010/alarms" -Method POST -Headers $headers -Body $body
```

如果返回告警数据或空列表（非报错），说明 DB Proxy 正常。

> **保持 DB Proxy 运行**，整个调试过程中不要关闭此窗口。

---

## 第2步：导入 n8n 工作流（7个）

### 2.1 访问 n8n

打开浏览器：`http://localhost:5678`（或你的 n8n 实际地址）

### 2.2 逐个导入工作流

对 7 个 JSON 文件，重复以下操作：

1. 点击左侧菜单 **Workflows**
2. 右上角点击 **Add workflow** → 然后点击右上角 **...** → **Import from File**
3. 选择对应 JSON 文件
4. 导入后，工作流名称和 4 个节点会自动出现

需要导入的 7 个文件（按顺序）：

| 序号 | 文件名 | Webhook 路径 | 功能 |
|------|--------|-------------|------|
| 1 | `01_query_alarms.json` | `/alarms` | 告警查询 |
| 2 | `02_query_machine_status.json` | `/status` | 机台状态 |
| 3 | `03_query_events.json` | `/events` | 事件时间线 |
| 4 | `04_query_lots.json` | `/lots` | Lot 查询 |
| 5 | `05_query_yield.json` | `/yield` | 产量统计 |
| 6 | `06_query_rcms_maintenance.json` | `/rcms-maintenance` | RCMS 维修 |
| 7 | `07_query_mes_lot.json` | `/mes-lot` | MES Lot |

### 2.3 修改 DB Proxy 地址

每个工作流中有一个 **Query DB** 节点，URL 默认为 `http://localhost:8010/xxx`。

如果 DB Proxy 和 n8n 不在同一台机器，需要修改：
1. 双击 **Query DB** 节点
2. 将 URL 中的 `localhost:8010` 改为 DB Proxy 实际地址
3. 确认 Authorization Header 为 `Bearer fabtwin-db-proxy-secret`（与 DB Proxy 的 TOKEN 一致）

### 2.4 激活工作流

对每个工作流：
1. 点击右上角 **Active** 开关，使其变为绿色
2. 记录 Webhook URL（显示在 Webhook 节点上方），格式为 `http://localhost:5678/webhook/alarms` 等

### 2.5 验证工作流

用 PowerShell 逐个测试（以告警查询为例）：
```powershell
$body = '{"machine_id": "OXE-01", "limit": 5}'
Invoke-RestMethod -Uri "http://localhost:5678/webhook/alarms" -Method POST -Body $body -ContentType "application/json"
```

返回应包含 `summary` 字段和告警数据。

> **7 个工作流全部导入并激活后，再继续下一步。**

---

## 第3步：创建 Dify 智能体

### 3.1 导入应用模板

1. 打开 Dify：`http://localhost:3000`（或你的 Dify 地址）
2. 进入 **工作室（Studio）**
3. 点击 **创建空白应用** 旁的 **...** → **从 DSL 导入**
4. 选择文件 `dify/fabtwin-ai-assistant.dsl.yaml`
5. 导入后应用名为「FabTwin AI Assistant」

### 3.2 配置模型

导入后需确认模型配置：

1. 进入应用 → **编排（Overview）**
2. 在右侧 **模型** 区域，点击设置
3. 选择你实际可用的模型：
   - **推荐**：智谱 GLM-4.5（`langgenius/zhipu/zhipu`）
   - 或其他已接入 Dify 的模型
4. 保存

> 如果 Dify 未接入任何模型，先在「设置 → 模型供应商」中配置（如智谱 GLM 的 API Key）。

### 3.3 确认系统提示词

1. 在编排页面，找到 **提示词（Prompt）** 区域
2. 确认系统提示词已自动填充（导入 DSL 时携带）
3. 如提示词为空，从 `dify/system_prompt.md` 文件中复制「提示词正文」粘贴进去
4. 确认包含 7 个工具的说明和跳转标记规则

### 3.4 确认对话变量

在编排页面的 **变量** 区域，确认以下变量存在：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `machine_id` | 文本输入 | 当前机台ID（由网站传入） |
| `user_role` | 下拉选择 | 用户角色（user/engineer/admin） |

> 这些变量由 FabTwin 后端调用 Dify API 时自动传入，用户无需手动输入。

### 3.5 发布应用

1. 点击右上角 **发布（Publish）**
2. 确认状态为「已发布」

---

## 第4步：配置 Dify 工具（接入 n8n）

这一步将 7 个 n8n 工作流注册为 Dify 工具，让 Dify 能调用它们。

### 4.1 导入 OpenAPI 工具定义

1. 在 Dify 应用编排页面，找到 **工具（Tools）** 区域
2. 点击 **添加工具** → **自定义（Custom）** → **自定义工具**
3. 填写工具集名称：`FabTwin 产线查询工具`
4. 在 **OpenAPI Schema** 文本框中，粘贴 `dify/fabtwin-tools-openapi.yaml` 的全部内容
5. **服务器地址（Server URL）**：填写 n8n 的 Webhook 基地址
   - 如果 n8n 和 Dify 同机：`http://localhost:5678/webhook`
   - 如果不同机：`http://<n8n的IP>:5678/webhook`
6. 点击 **保存**

### 4.2 验证工具注册

保存后，Dify 会自动解析 OpenAPI，注册 7 个工具：
- `query_alarms`
- `query_machine_status`
- `query_events`
- `query_lots`
- `query_yield`
- `query_rcms_maintenance`
- `query_mes_lot`

在工具列表中确认 7 个工具全部出现。

### 4.3 启用工具

对每个工具，点击开关启用（变为蓝色）。

### 4.4 测试工具调用

在 Dify 调试面板中测试：
1. 输入问题：「OXE-01 最近有什么告警？」
2. 观察 Dify 是否自动调用 `query_alarms` 工具
3. 确认返回结果包含告警数据
4. 确认回答末尾有跳转标记：`[JUMP: ...] [MACHINE: OXE-01]`

> **如果工具未被调用**，检查：系统提示词是否包含工具说明、工具是否已启用、n8n 工作流是否激活。

---

## 第5步：网站后端配置

FabTwin 后端已有 Dify 调用代码（`ai_middleware.py`），只需配置 Dify 连接参数。

### 5.1 获取 Dify API Key

1. 在 Dify 应用页面，点击左侧 **访问 API（API Access）**
2. 复制 **API 密钥（API Key）**，格式类似 `app-xxxxxxxxxxxx`
3. 记录 Dify Base URL：`http://localhost:3000/v1`（或你的 Dify 地址 + `/v1`）

### 5.2 在网站 AI 配置面板配置

1. 登录 FabTwin 网站（管理员账号）
2. 进入 **AI 配置管理**（用户管理旁边）
3. 在 **Dify/N8N 配置** 区域：
   - **启用 Dify**：开启
   - **Dify Base URL**：`http://localhost:3000`（不带 /v1）
   - **Dify API Key**：粘贴上一步复制的密钥
   - **Dify App ID**：可留空
4. 点击 **保存**

### 5.3 测试 Dify 连接

在 AI 配置面板点击 **测试 Dify 连接** 按钮，确认返回「连接成功」。

### 5.4 确认后端调用链路

后端调用流程（代码已实现，无需修改）：
1. 前端发送问题 → 后端 `/api/ai/chat`
2. 后端 `ai_middleware.py` 调用 Dify `/v1/chat-messages`
3. Dify 调用 n8n 工具 → n8n 调用 DB Proxy → 返回数据
4. Dify 生成回答（含跳转标记）
5. 后端解析 `[JUMP: ...] [MACHINE: ...]` 标记
6. 返回前端：回答文本 + `jump_timestamp` + `jump_machine_id`
7. 前端渲染跳转按钮

---

## 第6步：端到端调试

### 6.1 启动所有服务

确认以下服务全部运行：
- [x] DB Proxy（端口 8010）
- [x] n8n（端口 5678，7个工作流已激活）
- [x] Dify（端口 3000，应用已发布）
- [x] FabTwin 后端（端口 8000）
- [x] FabTwin 前端（端口 5173 或 IIS）

### 6.2 测试场景

在 FabTwin 网站的 AI 助手窗口，逐个测试以下场景：

#### 场景1：简单问候（不调工具）
- 输入：「你好」
- 预期：Dify 回复问候，不调用工具

#### 场景2：机台状态查询
- 输入：「OXE-01 现在状态怎么样？」
- 预期：Dify 调用 `query_machine_status`，返回机台状态
- 检查：回答末尾是否有跳转标记（如果有具体时间）

#### 场景3：告警查询（含跳转）
- 输入：「OXE-01 最近有什么告警？」
- 预期：Dify 调用 `query_alarms`，返回告警列表
- 检查：回答末尾有 `[JUMP: 时间] [MACHINE: OXE-01]` 标记
- 检查：前端显示「跳转到回放」按钮
- 点击按钮：应跳转到对应机台和时间段

#### 场景4：Lot 查询
- 输入：「最近的 Lot 进度如何？」
- 预期：Dify 调用 `query_lots`，返回 Lot 列表

#### 场景5：产量统计
- 输入：「OXE-01 的产量统计」
- 预期：Dify 调用 `query_yield`，返回产量数据

#### 场景6：RCMS 维修记录
- 输入：「OXE-01 上次保养是什么时候？」
- 预期：Dify 调用 `query_rcms_maintenance`
- 注意：需要 Informix 已配置，否则返回错误提示

#### 场景7：MES Lot 查询
- 输入：「Lot LOT20260903001 在 MES 里是什么状态？」
- 预期：Dify 调用 `query_mes_lot`
- 注意：需要 Informix 已配置

### 6.3 查看执行日志

在 FabTwin AI 配置面板 → **使用日志** 页面，可以查看：
- 每次调用的 Provider、模型、Token 用量
- 工具调用记录
- 执行步骤日志
- 成功/失败状态

如果某次调用失败，在日志中查看 `error_msg` 和 `execution_log` 定位问题。

---

## 故障排查

### 问题1：Dify 工具未被调用

**可能原因**：
- 系统提示词未包含工具说明 → 检查提示词
- 工具未启用 → 在 Dify 工具列表确认开关
- n8n 工作流未激活 → 在 n8n 确认 Active 状态
- 模型不支持 Function Calling → 换用支持工具调用的模型（如 GLM-4.5）

### 问题2：n8n 工作流返回错误

**检查步骤**：
1. 在 n8n 中点击工作流的 **Executions** 查看执行日志
2. 检查 **Query DB** 节点的 HTTP 请求是否成功
3. 检查 DB Proxy 是否在运行：访问 `http://localhost:8010/health`
4. 检查 Authorization Header 是否与 DB Proxy TOKEN 一致

### 问题3：DB Proxy 连接 Oracle 失败

**常见错误**：`DPI-1047: Cannot locate a 64-bit Oracle Client library`

**解决**：
1. 确认已安装 64 位 Oracle Instant Client（19c+）
2. 在 `start.ps1` 中设置 `ORACLE_CLIENT_DIR` 指向 Instant Client 目录
3. 确认 Python 也是 64 位

### 问题4：DB Proxy 连接 Informix 失败

**常见错误**：`Data source name not found and no default driver specified`

**解决**：
1. 确认已安装 IBM Informix ODBC Driver
2. 在 ODBC 数据源管理器中确认驱动已注册
3. 如果暂不使用 RCMS/MES，可忽略（Oracle 查询不受影响）

### 问题5：跳转标记未触发跳转

**检查步骤**：
1. 在浏览器开发者工具 Network 中，查看 `/api/ai/chat` 响应
2. 确认响应中包含 `jump_timestamp` 和 `jump_machine_id` 字段
3. 如果字段为空，检查 Dify 回答末尾是否有 `[JUMP: ...] [MACHINE: ...]` 标记
4. 确认时间格式为 `YYYY-MM-DD HH:MM:SS`
5. 检查后端 `ai_middleware.py` 的正则解析：`\[JUMP:\s*([^\]]+)\]`

### 问题6：网站 AI 窗口不显示

**检查步骤**：
1. 确认 AI 配置面板中 Dify 已启用
2. 确认 Dify API Key 正确
3. 在浏览器控制台查看是否有报错
4. 检查后端日志是否有 Dify 调用失败信息

---

## 附：已废弃文档

以下旧版文档已被本 SOP 替换，不再维护：
- `DIFY_N8N_ADVANCED_GUIDE.md`（已删除）
- `dify/DIFY_INTEGRATION_SOP.md`（已删除）
- `dify/Dify部署与RAG接入指南.md`（已删除）
- `n8n/N8N_INTEGRATION_SOP.md`（已删除）
- `n8n/N8N部署与工作流接入指南.md`（已删除）

所有内容已合并到本文件中。

---

## 附：文件下载清单

部署所需全部文件位于 `fab-twin-pro/docs/integration/` 目录：

| 文件 | 用途 | 使用位置 |
|------|------|----------|
| `db-proxy/db_proxy.py` | DB Proxy 服务 | 第1步 |
| `db-proxy/requirements.txt` | Python 依赖 | 第1步 |
| `db-proxy/start.ps1` | 启动脚本 | 第1步 |
| `n8n/01~07_*.json` | 7 个工作流 | 第2步 |
| `dify/fabtwin-ai-assistant.dsl.yaml` | Dify 应用模板 | 第3步 |
| `dify/fabtwin-tools-openapi.yaml` | 7 个工具 OpenAPI 定义 | 第4步 |
| `dify/system_prompt.md` | 系统提示词（参考） | 第3步 |
