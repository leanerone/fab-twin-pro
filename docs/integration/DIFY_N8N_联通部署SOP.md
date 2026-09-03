# FabTwin Dify + n8n 部署联通 SOP（完整版）

> **版本**: v3.0（2026-09-03，去掉 DB Proxy 中间层，n8n 直连数据库）
> **适用**: 已部署 Dify 和 n8n，需从零配置到与 FabTwin 网站联通
> **架构**: n8n 用 Oracle 节点直连 Oracle，用 ODBC 节点直连 Informix

***

## 目录

1. [架构总览](#1-架构总览)
2. [第1步：配置 n8n 数据库凭据](#第1步配置-n8n-数据库凭据)
3. [第2步：导入 n8n 工作流（7个）](#第2步导入-n8n-工作流7个)
4. [第3步：创建 Dify 智能体](#第3步创建-dify-智能体)
5. [第4步：配置 Dify 工具（接入 n8n）](#第4步配置-dify-工具接入-n8n)
6. [第5步：网站后端配置](#第5步网站后端配置)
7. [第6步：端到端调试](#第6步端到端调试)
8. [故障排查](#故障排查)

***

## 1. 架构总览

```
用户在 FabTwin 网站提问
        │
        ▼
FabTwin 后端 (ai_middleware.py)
        │  调用 Dify Chat API
        ▼
┌───────────────────────────┐
│  Dify（AI 中枢）            │
│  · 理解自然语言              │
│  · 决定调用哪个工具          │
│  · 整合结果生成回答          │
│  · 输出跳转标记              │
└───────────┬───────────────┘
            │ 调用工具（HTTP Webhook）
            ▼
┌───────────────────────────┐
│  n8n（直连数据库）           │
│  · 7 个工作流               │
│  · Oracle 节点查 Oracle     │
│  · ODBC 节点查 Informix     │
└───────────┬───────────────┘
            │ SQL 直连
            ▼
    Oracle + Informix 数据库
```

**核心原则**：

- Dify 负责 AI 逻辑（理解、决策、回答生成）

- n8n 直连数据库查询（Oracle 节点 + ODBC 节点），无需中间层

- 网站仅负责显示和跳转执行

### 组件清单

| 组件         | 端口   | 作用                        |
| ---------- | ---- | ------------------------- |
| n8n        | 5678 | 工作流引擎，Oracle/ODBC 节点直连 DB |
| Dify       | 3000 | AI 中枢                     |
| FabTwin 后端 | 8000 | 网站服务，调用 Dify API          |

### 文件目录结构

```
docs/integration/
├── DIFY_N8N_联通部署SOP.md        ← 本文件（唯一 SOP）
├── n8n/
│   ├── 01_query_alarms.json       ← 告警查询（Oracle节点）
│   ├── 02_query_machine_status.json ← 机台状态（Oracle节点）
│   ├── 03_query_events.json        ← 事件时间线（Oracle节点）
│   ├── 04_query_lots.json          ← Lot查询（Oracle节点）
│   ├── 05_query_yield.json         ← 产量统计（Oracle节点）
│   ├── 06_query_rcms_maintenance.json ← RCMS维修（ODBC节点）
│   └── 07_query_mes_lot.json       ← MES Lot（ODBC节点）
└── dify/
    ├── fabtwin-ai-assistant.dsl.yaml ← Dify 应用模板
    ├── fabtwin-tools-openapi.yaml   ← 7个工具 OpenAPI 定义
    └── system_prompt.md             ← 系统提示词（参考）
```

***

## 第1步：配置 n8n 数据库凭据

n8n 工作流用 Oracle 节点和 ODBC 节点直连数据库，需要先在 n8n 中创建数据库凭据。

### 1.1 创建 Oracle 凭据

1. 打开 n8n：`http://localhost:5678`
2. 左侧菜单 → **Credentials** → **Add Credential**
3. 搜索 **Oracle**，选择 Oracle 类型
4. 填写连接信息：

   - **Host**: Oracle 数据库 IP（如 `10.30.116.xxx`）

   - **Port**: `1521`

   - **Service Name**: 你的 Oracle 服务名（如 `orcl`）

   - **User**: Oracle 用户名（如 `fabtwin`）

   - **Password**: Oracle 密码
5. 凭据名称填 **FabTwin Oracle**（与工作流模板中一致）
6. 保存

### 1.2 创建 Informix ODBC 凭据（RCMS/MES）

1. Credentials → **Add Credential**
2. 搜索 **ODBC**，选择 ODBC 类型
3. 填写 ODBC 连接字符串（按实际 Informix 配置）：

   ```
   DRIVER={IBM INFORMIX ODBC DRIVER};SERVER=rcms_server;HOST=xxx;SERVICE=9088;DATABASE=rcms;UID=admin;PWD=xxx
   ```
4. 凭据名称填 **Informix RCMS**（对应工作流 06）
5. 保存
6. 重复创建 **Informix MES** 凭据（对应工作流 07，如果 MES 和 RCMS 是同一数据库，可共用）

> **如果 n8n 中找不到 Oracle 或 ODBC 节点类型**：说明 n8n 环境未安装对应扩展。Docker 部署需在镜像中安装 `oracledb` npm 包和 Oracle Instant Client，ODBC 需安装 unixodbc + Informix ODBC 驱动。

***

## 第2步：导入 n8n 工作流（7个）

### 2.1 逐个导入

对 7 个 JSON 文件，重复以下操作：

1. 左侧菜单 **Workflows** → 右上角 **Add workflow**
2. 右上角 **...** → **Import from File** → 选择 JSON 文件
3. 导入后，工作流包含 5 个节点：Webhook → Parse → Query → Format → Respond

| 序号 | 文件名                              | Webhook 路径          | 查询节点   | 数据库      |
| -- | -------------------------------- | ------------------- | ------ | -------- |
| 1  | `01_query_alarms.json`           | `/alarms`           | Oracle | Oracle   |
| 2  | `02_query_machine_status.json`   | `/status`           | Oracle | Oracle   |
| 3  | `03_query_events.json`           | `/events`           | Oracle | Oracle   |
| 4  | `04_query_lots.json`             | `/lots`             | Oracle | Oracle   |
| 5  | `05_query_yield.json`            | `/yield`            | Oracle | Oracle   |
| 6  | `06_query_rcms_maintenance.json` | `/rcms-maintenance` | ODBC   | Informix |
| 7  | `07_query_mes_lot.json`          | `/mes-lot`          | ODBC   | Informix |

### 2.2 绑定数据库凭据

导入后，每个工作流的 Query 节点（Query Oracle / Query Informix）需要绑定凭据：

1. 双击 **Query Oracle** 节点
2. 在 **Credential to connect with** 下拉中，选择第1步创建的 **FabTwin Oracle**
3. 确认 SQL 查询语句正确
4. 对 06/07 的 **Query Informix** 节点，选择 **Informix RCMS** / **Informix MES** 凭据

### 2.3 检查 SQL（可选）

每个 Query 节点中的 SQL 语句需与实际数据库表结构匹配。如果表名/字段名不同，双击节点修改 SQL。

主要表：

- **DT\_EVENT\_RAW** — 事件/告警原始表（字段：event\_ts\_utc, machine\_id, event\_name, event\_value, parse\_status）

- **MACHINES** — 机台表（字段：id, model, status, current\_lot\_id, last\_event\_ts）

- **LOTS** — 批次表（字段：lot\_id, machine\_id, status, wafer\_qty, start\_time）

- **maintenance\_log**（Informix）— 维修记录表

- **lot\_info**（Informix）— MES Lot 信息表

### 2.4 激活工作流

对每个工作流，点击右上角 **Active** 开关，使其变为绿色。

### 2.5 验证工作流

用 PowerShell 测试（以告警查询为例）：

```powershell
$body = '{"machine_id": "OXE-01", "limit": 5}'
Invoke-RestMethod -Uri "http://localhost:5678/webhook/alarms" -Method POST -Body $body -ContentType "application/json"
```

返回应包含 `summary` 字段和查询数据。

> **7 个工作流全部导入、绑定凭据、激活后，再继续下一步。**

***

## 第3步：创建 Dify 智能体

### 3.1 导入应用模板

1. 打开 Dify：`http://localhost:3000`
2. 进入 **工作室（Studio）**
3. 点击 **创建空白应用** 旁的 **...** → **从 DSL 导入**
4. 选择文件 `dify/fabtwin-ai-assistant.dsl.yaml`
5. 导入后应用名为「FabTwin AI Assistant」

### 3.2 配置模型

1. 进入应用 → **编排（Overview）**
2. 右侧 **模型** 区域设置
3. 选择你实际可用的模型（推荐智谱 GLM-4.5）
4. 保存

### 3.3 确认系统提示词

1. 编排页面找到 **提示词（Prompt）** 区域
2. 确认系统提示词已自动填充（含 7 个工具说明和跳转标记规则）
3. 如提示词为空，从 `dify/system_prompt.md` 复制「提示词正文」粘贴

### 3.4 确认对话变量

编排页面 **变量** 区域确认：

| 变量名          | 类型   | 说明           |
| ------------ | ---- | ------------ |
| `machine_id` | 文本输入 | 当前机台ID（网站传入） |
| `user_role`  | 下拉选择 | 用户角色         |

### 3.5 发布应用

点击右上角 **发布（Publish）**。

***

## 第4步：配置 Dify 工具（接入 n8n）

### 4.1 导入 OpenAPI 工具定义

1. Dify 应用编排页面，找到 **工具（Tools）** 区域
2. **添加工具** → **自定义（Custom）** → **自定义工具**
3. 工具集名称：`FabTwin 产线查询工具`
4. **OpenAPI Schema** 文本框粘贴 `dify/fabtwin-tools-openapi.yaml` 全部内容
5. **服务器地址**：填 n8n Webhook 基址

   - 同机：`http://localhost:5678/webhook`

   - 不同机：`http://<n8n的IP>:5678/webhook`
6. 保存

### 4.2 启用工具

保存后 7 个工具自动注册，逐个点击开关启用。

### 4.3 测试工具调用

在 Dify 调试面板输入：「OXE-01 最近有什么告警？」

- 观察 Dify 是否调用 `query_alarms` 工具

- 确认返回告警数据

- 确认回答末尾有跳转标记：`[JUMP: ...] [MACHINE: OXE-01]`

***

## 第5步：网站后端配置

FabTwin 后端已有 Dify 调用代码，只需配置连接参数。

### 5.1 获取 Dify API Key

1. Dify 应用页面 → 左侧 **访问 API（API Access）**
2. 复制 **API 密钥**（格式 `app-xxxxxxxxxxxx`）
3. 记录 Dify Base URL：`http://localhost:3000`（不带 /v1）

### 5.2 网站配置

1. 登录 FabTwin 网站（管理员）
2. 进入 **AI 配置管理**（用户管理旁边）
3. **Dify/N8N 配置** 区域：

   - **启用 Dify**：开启

   - **Dify Base URL**：`http://localhost:3000`

   - **Dify API Key**：粘贴密钥
4. **保存全部配置**
5. 点击 **测试 Dify 连接**，确认返回「连接成功」

***

## 第6步：端到端调试

### 6.1 确认服务运行

- [x] n8n（端口 5678，7个工作流已激活，凭据已绑定）

- [x] Dify（端口 3000，应用已发布）

- [x] FabTwin 后端（端口 8000）

- [x] FabTwin 前端（端口 5173 或 IIS）

### 6.2 测试场景

在 FabTwin 网站 AI 助手窗口测试：

| 场景     | 输入                      | 预期                          |
| ------ | ----------------------- | --------------------------- |
| 1. 问候  | 你好                      | Dify 回复，不调工具                |
| 2. 状态  | OXE-01 现在状态怎么样？         | 调用 query\_machine\_status   |
| 3. 告警  | OXE-01 最近有什么告警？         | 调用 query\_alarms，有跳转标记      |
| 4. 事件  | OXE-01 最近发生了什么？         | 调用 query\_events            |
| 5. Lot | 最近的 Lot 进度如何？           | 调用 query\_lots              |
| 6. 产量  | OXE-01 的产量统计            | 调用 query\_yield             |
| 7. 维修  | OXE-01 上次保养什么时候？        | 调用 query\_rcms\_maintenance |
| 8. MES | Lot LOT001 在 MES 里什么状态？ | 调用 query\_mes\_lot          |

### 6.3 查看执行日志

AI 配置面板 → **使用日志**，查看每次调用的 Provider、Token 用量、工具调用记录、执行步骤。

***

## 故障排查

### n8n Oracle 节点报错

- **凭据未绑定**：检查 Query Oracle 节点的 Credential 下拉是否已选择

- **连接超时**：检查 n8n Docker 容器能否访问 Oracle IP（`docker exec -it <container> ping <oracle_ip>`）

- **Oracle Client 缺失**：Docker 镜像需安装 Oracle Instant Client

### n8n ODBC 节点报错

- **驱动未找到**：检查 n8n Docker 容器是否安装了 IBM Informix ODBC Driver

- **连接字符串错误**：在 n8n Credentials 中测试连接

### Dify 工具未被调用

- 系统提示词未包含工具说明 → 检查提示词

- 工具未启用 → Dify 工具列表确认开关

- n8n 工作流未激活 → n8n 确认 Active 状态

- 模型不支持 Function Calling → 换支持工具调用的模型

### 跳转标记未触发

1. 浏览器开发者工具 Network → 查看 `/api/ai/chat` 响应
2. 确认响应包含 `jump_timestamp` 和 `jump_machine_id`
3. 如果为空，检查 Dify 回答末尾是否有 `[JUMP: ...] [MACHINE: ...]`

### Dify 配置保存后刷新丢失

已修复（v2.9.3）：后端返回原始 URL 字段，前端使用正确字段名回显。API Key 不回显但显示"已保存"标志。

***

## 附：文件清单

| 文件                                   | 用途               | 使用位置 |
| ------------------------------------ | ---------------- | ---- |
| `n8n/01~07_*.json`                   | 7 个工作流           | 第2步  |
| `dify/fabtwin-ai-assistant.dsl.yaml` | Dify 应用模板        | 第3步  |
| `dify/fabtwin-tools-openapi.yaml`    | 7 个工具 OpenAPI 定义 | 第4步  |
| `dify/system_prompt.md`              | 系统提示词（参考）        | 第3步  |

