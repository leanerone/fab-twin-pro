# FabTwin + Dify + n8n 部署执行 SOP（手把手版）

> **你不需要懂 Dify/n8n 原理，照着下面每一步做就行。**
> 架构：Dify（AI 中枢）→ n8n（HTTP Request）→ DB Proxy（Python FastAPI）→ Oracle 11g
>
> 前置条件：
>
> - Dify 已部署能访问网页（如 <http://10.30.116.68）>
>
> - n8n 已部署能访问网页（如 <http://10.30.116.151:5678）>
>
> - FabTwin 后端 server 上有 Oracle Client（用于 DB Proxy 连接 11g）

***

## 总览（7 大步）

| 步骤    | 在哪做            | 做什么                        | 耗时参考  |
| ----- | -------------- | -------------------------- | ----- |
| 第 1 步 | FabTwin Server | 部署 DB Proxy 服务（Python）     | 10 分钟 |
| 第 2 步 | n8n            | 导入 10 个工作流 + 改地址 + 激活      | 10 分钟 |
| 第 3 步 | Dify           | 导入应用模板 .yml                | 2 分钟  |
| 第 4 步 | Dify           | 配置 OpenAPI 工具（接通 n8n）      | 10 分钟 |
| 第 5 步 | Dify           | 测试对话（验证 AI 能调工具）           | 5 分钟  |
| 第 6 步 | FabTwin 后端     | 配置 .env（Dify 地址 + API Key） | 3 分钟  |
| 第 7 步 | FabTwin 网页     | 端到端测试                      | 5 分钟  |

***

## 第 1 步：在 FabTwin Server 上部署 DB Proxy

DB Proxy 是一个轻量 Python 服务，与 FabTwin 后端共用 Oracle Client，负责替 n8n 查询 Oracle 11g。

### 1.1 复制文件

将 `services/db_proxy/` 整个目录复制到 FabTwin 后端所在 server（或直接用项目里的）。

### 1.2 安装依赖

```bash
cd services\db_proxy
pip install -r requirements.txt
```

### 1.3 配置 .env

复制 `.env.example` 为 `.env`，修改为你的实际值：

```env
# Oracle 11g 连接（和 FabTwin 后端用同一套）
ORACLE_USER=fabtwin
ORACLE_PASSWORD=你的密码
ORACLE_HOST=10.30.116.150
ORACLE_PORT=1521
ORACLE_SERVICE=ORCL
ORACLE_DSN_TYPE=sid
ORACLE_CLIENT_DIR=C:\app\client\product\11.2.0\client_1

# 代理服务
DB_PROXY_PORT=8001
DB_PROXY_API_KEY=fabtwin-proxy-2026
```

> **重要**：`ORACLE_DSN_TYPE=sid`（11g 用 SID 模式，不是 service\_name）
> `ORACLE_CLIENT_DIR` 指向你的 Oracle Client 安装目录（要有 oci.dll）

### 1.4 启动

```bash
python main.py
```

或双击 `start.bat`。

**确认成功**：

- 控制台显示 `FabTwin DB Proxy 启动: port=8001`

- 浏览器访问 `http://10.30.116.150:8001/health`，返回 `{"status":"ok","db":"connected"}`

### 1.5 设为后台服务（可选）

用 NSSM 或 Windows 任务计划程序设为开机自启。

***

## 第 2 步：在 n8n 导入 10 个工作流

### 2.1 导入

1. 打开 n8n 网页 → **Workflows** → **Import from File**
2. 依次选择 `docs/integration/n8n/F1_get_machine_status.json` \~ `F10_list_capabilities.json`
3. 每个工作流只有 3 个节点：Webhook → HTTP Request → Respond

### 2.2 修改 DB Proxy 地址

每个工作流里的 **Query DB Proxy** 节点，URL 默认是 `http://10.30.116.150:8001/query/xxx`：

1. 如果 DB Proxy 就在 10.30.116.150:8001 → 不用改
2. 如果不在 → 双击 Query DB Proxy 节点，修改 URL 里的 IP 和端口
3. 同时检查 `X-API-Key` 头是否和 .env 里的 `DB_PROXY_API_KEY` 一致

### 2.3 激活

每个工作流右上角 **Active** 开关打开（变绿色）。10 个都要激活。

**确认成功**：10 个工作流都是 Active 状态。

> **注意**：这版工作流**不需要绑定 Oracle 凭据**——数据库连接由 DB Proxy 处理。

***

## 第 3 步：在 Dify 导入应用模板

1. 打开 Dify → **Create App** → **Import**
2. 选择 `docs/integration/dify/fabtwin-ai-assistant.dsl.yml`
3. 导入后自动跳转到应用编排页面

**确认成功**：

- 应用名称显示 "FabTwin AI Assistant"

- pre\_prompt 里有完整中文系统提示词（10 类 4 步 + FABTWIN 块）

- Variables 能看到 machine\_id 和 user\_role

***

## 第 4 步：在 Dify 配置 OpenAPI 工具

### 4.1 上传 OpenAPI 规范

1. 应用编排页面 → **Tools** → **Add Tool** → **Custom Tool**
2. 填 Name: `FabTwin n8n Tools`
3. 把 `docs/integration/dify/fabtwin-tools-openapi.yaml` 内容粘贴进 Schema
4. **重要**：把 `servers.url` 改成你的 n8n 地址，如 `http://10.30.116.151:5678/webhook`
5. Save

### 4.2 启用 10 个工具

在 Tools 区域勾选全部 10 个工具。

**确认成功**：10 个工具全部 enabled。

***

## 第 5 步：在 Dify 测试对话

1. 点 **Preview** / **调试**
2. 输入：`你能帮我干什么` → 应返回 10 类功能清单
3. 设置变量 machine\_id = `OXE-1`，输入：`今天产量` → 应返回产量数据

**如果报错**：

- "Connection refused" → 检查 n8n 和 DB Proxy 是否在运行

- "401" → 检查 n8n Webhook Secret 或 DB Proxy API Key

- "timeout" → 检查 Oracle Client 是否正确安装

***

## 第 6 步：配置 FabTwin 后端

### 6.1 获取 Dify API Key

Dify 应用 → **Publish** → **API Access** → 复制 API Key

### 6.2 编辑后端 .env

```env
ENABLE_LOCAL_RULE_FALLBACK=false
DIFY_BASE_URL=http://10.30.116.68
DIFY_API_KEY=app-你的key
```

重启后端。

***

## 第 7 步：FabTwin 网页端到端测试

| 用例        | 输入          | 预期            |
| --------- | ----------- | ------------- |
| 浮动球不带机台   | `今天产量`      | 提示"请告诉我机台ID"  |
| OXE-1 详情页 | `今天产量`      | 直接返回产量表格+跳转按钮 |
| 全厂报警      | `最近7天有什么报警` | 返回全厂报警统计      |
| OXE-1 报警  | `最近有什么报警`   | 报警列表+跳转按钮     |
| 普通用户导出    | `导出报警报表`    | "需管理员权限"      |
| 管理员导出     | `导出报警报表`    | 返回下载链接        |

***

## 架构图

```
用户在 FabTwin 网页提问
        │
        ▼
FabTwin 后端 (ai_middleware.py)
        │  POST /v1/chat-messages
        ▼
┌───────────────────┐
│  Dify (AI 中枢)    │  理解自然语言 → 选工具 → 整理答案
└───────┬───────────┘
        │  调工具（HTTP Webhook）
        ▼
┌───────────────────┐
│  n8n (3节点)       │  Webhook → HTTP Request → Respond
└───────┬───────────┘
        │  HTTP POST
        ▼
┌───────────────────┐
│  DB Proxy (8001)   │  Python FastAPI，Thick mode 连 Oracle 11g
│  /query/*          │  10 个查询端点
└───────┬───────────┘
        │  SQL
        ▼
    Oracle 11g DB
```

***

## 故障排查速查表

| 现象                      | 原因                    | 解决                                                     |
| ----------------------- | --------------------- | ------------------------------------------------------ |
| DB Proxy /health 返回 503 | Oracle Client 未安装或路径错 | 检查 ORACLE\_CLIENT\_DIR 指向 oci.dll 所在目录                 |
| DB Proxy 报 ORA-03134    | 11g 不支持 Thin 模式       | 确认 ORACLE\_DSN\_TYPE=sid，安装 Oracle Client              |
| n8n 调 DB Proxy 报 401    | API Key 不匹配           | 检查 n8n HTTP Request 的 X-API-Key 头和 DB\_PROXY\_API\_KEY |
| n8n 调 DB Proxy 报超时      | Oracle 查询慢或网络问题       | 检查 DB Proxy 日志，确认 SQL 能执行                              |
| Dify 导入 .yml 报错         | 格式不匹配                 | 确认 dependencies.value 无引号，Dify 版本 0.6.0+               |
| Dify 调工具 404            | n8n 工作流未激活            | 在 n8n 里打开 Active 开关                                    |
| 回答有 SQL 代码              | Dify prompt 未生效       | 检查 pre\_prompt 是否完整                                    |

***

## 文件清单

| 文件                                                   | 用途                    |
| ---------------------------------------------------- | --------------------- |
| `services/db_proxy/main.py`                          | DB Proxy 服务（10 个查询端点） |
| `services/db_proxy/requirements.txt`                 | Python 依赖             |
| `services/db_proxy/.env.example`                     | 配置模板                  |
| `services/db_proxy/start.bat`                        | Windows 启动脚本          |
| `docs/integration/n8n/F1~F10*.json`                  | n8n 工作流模板（DB Proxy 版） |
| `docs/integration/n8n/backup_oracle_direct/`         | 旧版备份（Oracle 直连版）      |
| `docs/integration/dify/fabtwin-ai-assistant.dsl.yml` | Dify 应用模板             |
| `docs/integration/dify/fabtwin-tools-openapi.yaml`   | OpenAPI 工具定义          |

