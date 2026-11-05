# FabTwin Pro 团队交接文档

> 适用分支：`ver3`
>
> 更新日期：2026-11-05
>
> 用途：向团队成员说明“我负责什么、代码在哪里、新文件放哪里、哪些公共文件不能随意改”。

## 1. 先看懂这一句话

**每个人纵向负责一个业务模块的前端和后端；公共代码由洪佳琪把关；Dify/n8n 集成资产和独立 `db_proxy` 由张亮负责。**

本文件用于交接讲解。开始实际开发时，仍按下面的顺序阅读：

1. 阅读根目录 [README.md](README.md)，确认最新开发、启动和提交要求。
2. 阅读自己模块的 README。
3. 只修改当前需求需要的模块；涉及公共代码或其他人的模块时，先沟通再改。

不要先翻 `docs/archive/`，也不要使用旧 Archify 图或历史文档中的目录结构。

## 2. 人员分工

| 人员 | 负责范围 | 主要目录 |
|---|---|---|
| **钱鸣** | 模型库前后端、模型与模型资产 | `backend/modules/model_library/`、`frontend/src/modules/model-library/`、`models/`、`frontend/public/models/`、`frontend/src/api/{models,uploads}.js` |
| **季世庆** | 生产监控前后端、数据链路、团队总控，协调进度与合并冲突 | `backend/modules/production_monitor/`、`frontend/src/modules/production-monitor/`、`backend/seed_oxe_test_data.py`、`frontend/src/api/{machines,history,floors}.js` |
| **朱明钊** | AI 助手前后端、Provider、MCP、语音 | `backend/modules/ai_assistant/`、`frontend/src/modules/ai-assistant/`、`frontend/src/api/ai.js` |
| **洪佳琪** | 系统管理、平台内核、公共代码与最终审核 | `backend/modules/system_admin/`、`frontend/src/modules/system-admin/`、`backend/core/`、`frontend/src/platform/`、`backend/` 根公共文件、`frontend/src/api/{core,index,auth}.js` |
| **张亮** | Dify/n8n 集成资产、运维脚本和独立 `db_proxy`，不负责平台业务代码 | `backend/integrations/dify_n8n/`、`services/db_proxy/`、Dify/n8n 相关 `deploy/` 与 `scripts/` 资产 |

### 三个容易分错的边界

- `backend/modules/ai_assistant/services/providers/` 中的 Dify/n8n Provider 是平台业务代码，归 **朱明钊**。
- Dify/n8n 工作流、部署运维、集成脚本和 `services/db_proxy/` 归 **张亮**。
- `backend/modules/production_monitor/seeds/seed_vpo_motion.py` 位于生产监控模块，归 **季世庆**。

## 3. 当前文件架构

当前仍是一个 Vue 前端和一个 FastAPI 后端，不是微服务。后端只是按业务模块整理目录，启动入口仍是 `backend/main.py`。

```text
fab-twin-pro/
├── frontend/src/
│   ├── modules/
│   │   ├── model-library/           钱鸣：模型库页面与模型编辑
│   │   ├── production-monitor/      季世庆：生产监控页面
│   │   ├── ai-assistant/            朱明钊：AI 助手页面
│   │   └── system-admin/            洪佳琪：登录、用户和权限页面
│   ├── platform/                    洪佳琪：前端公共平台能力
│   ├── api/                         现有接口文件，按责任表划分归属
│   ├── stores/ / router/            全局状态与路由，属于公共代码
│   └── main.js / App.vue            前端公共入口与应用装配
│
├── backend/
│   ├── modules/
│   │   ├── model_library/           钱鸣：模型库接口和业务逻辑
│   │   ├── production_monitor/      季世庆：生产监控接口和数据链路
│   │   ├── ai_assistant/            朱明钊：AI、Provider、MCP、语音
│   │   └── system_admin/            洪佳琪：登录、用户和权限接口
│   ├── core/                        洪佳琪：后端公共依赖和公共服务
│   ├── integrations/dify_n8n/       张亮：Dify/n8n 集成资产
│   └── 根目录 8 个 Python 文件       总入口、公共数据库底座、数据脚本
│
├── models/                          钱鸣：SVG / Motion 等模型资产
├── services/db_proxy/               张亮：独立 Oracle 只读代理
└── deploy/ / scripts/               部署和运维资产，按实际内容划分归属
```

## 4. 前后端怎样对应开发

| 业务模块 | 前端位置 | 后端位置 | 负责人 |
|---|---|---|---|
| 模型库 | `frontend/src/modules/model-library/` | `backend/modules/model_library/` | 钱鸣 |
| 生产监控 | `frontend/src/modules/production-monitor/` | `backend/modules/production_monitor/` | 季世庆 |
| AI 助手 | `frontend/src/modules/ai-assistant/` | `backend/modules/ai_assistant/` | 朱明钊 |
| 系统管理 | `frontend/src/modules/system-admin/` | `backend/modules/system_admin/` | 洪佳琪 |

例如，要修改“告警页面和告警接口”，主要负责人只需要先检查自己的生产监控前端模块和生产监控后端模块，不需要去模型库或 AI 目录中寻找。

后端业务模块内部按下面的规则理解：

| 目录或文件 | 用途 |
|---|---|
| `routes/` | 前端调用的 HTTP 接口，处理请求参数、权限依赖和响应 |
| `services/` | 业务逻辑、数据轮询、外部 Provider、工具等 |
| `seeds/` | 当前模块专用的测试或初始化数据 |
| `__init__.py` | Python 包标识，通常为空或只做包导出，不是独立业务模块 |

## 5. `backend/` 根目录的 8 个 Python 文件

这些文件不是漏归档的业务代码，也不是“没人管的散落文件”。它们分为系统公共底座、初始化数据和独立工具三组。

### 5.1 系统运行必需的公共文件

| 文件 | 作用 | 修改规则 |
|---|---|---|
| `backend/main.py` | FastAPI 总入口和总装配线：注册四个业务模块路由，负责启动初始化、WebSocket 和健康检查 | 普通业务开发一般不改；新增顶级模块或调整启动过程时才修改，洪佳琪审核 |
| `backend/config.py` | 公共配置中心：Oracle、端口、CORS、功能开关等 | 增加或调整全局配置时修改，洪佳琪审核 |
| `backend/database.py` | 数据库连接底座：Oracle Client、SQLAlchemy 连接、`SessionLocal`、`get_db`，以及建表、补列和索引初始化 | 普通接口开发只使用它；公共连接和初始化机制由洪佳琪负责 |
| `backend/models.py` | 数据库 ORM 表定义，例如 `Machine`、`Lot`、`Alarm`、`User`、`AIConfig` | 新增表或字段时可能涉及，需要对应模块负责人和洪佳琪协调 |
| `backend/schemas.py` | Pydantic 请求和响应结构，例如 `AIChatRequest`、`MachineOut` | 修改接口字段时可能涉及，由对应模块负责人修改，公共影响由洪佳琪审核 |

特别注意：

- `backend/models.py` 是**数据库表定义**。
- 仓库根目录 `models/` 是 **SVG、Motion 等模型资产**。
- `backend/schemas.py` 是**接口请求和响应结构**，不是数据库表。

### 5.2 初始化和测试数据脚本

| 文件 | 作用 | 使用规则 |
|---|---|---|
| `backend/seed_data.py` | 公共演示数据初始化入口，生成机台、Lot、告警、楼层、角色、用户等基础数据；后端启动初始化会调用 | 目前保留为公共入口，普通业务开发不擅自拆改，洪佳琪最终审核 |
| `backend/seed_oxe_test_data.py` | 给 `OXE-01` 生成最近两天的事件、腔体快照、告警和 KPI 测试数据 | 归季世庆，仅在需要这套 OXE 测试数据时手动执行 |

### 5.3 独立 SQL 工具

| 文件 | 作用 | 使用规则 |
|---|---|---|
| `backend/sql_runner.py` | 独立手动 SQL 执行工具：读取 `services/db_proxy/.env`，连接 Oracle，执行指定 SQL 文件并提交 | 不是普通业务路由或启动服务；使用 `system` 账号且会提交修改，不要为了测试随意运行或修改 |

可以把这 8 个文件记成：

```text
启动和公共底座：main.py / config.py / database.py / models.py / schemas.py
初始化数据：    seed_data.py / seed_oxe_test_data.py
手动数据库工具：sql_runner.py
```

## 6. 新需求和新文件放在哪里

| 新需求 | 应该放在哪里 |
|---|---|
| 模型上传校验 | 后端放 `backend/modules/model_library/routes/` 或 `services/`；前端组件放模型库模块，现有上传接口改 `frontend/src/api/uploads.js` |
| 新增机台 SVG / Motion 资产 | 资产放根目录 `models/` 的对应位置；模型库专用 seed 放 `backend/modules/model_library/seeds/` |
| 告警筛选或 Lot 查询 | 后端放 `backend/modules/production_monitor/routes/`，可复用业务逻辑放该模块 `services/`；前端放生产监控模块 |
| AI 查询工具或 Provider 调整 | 后端放 `backend/modules/ai_assistant/services/`，Provider 放其 `providers/`；前端放 AI 助手模块 |
| 用户角色字段或登录规则 | 业务接口放 `backend/modules/system_admin/routes/`；共享认证底座在 `backend/core/services/security.py`，必须洪佳琪审核 |
| Dify 工作流或 n8n 运维 | 集成资产放 `backend/integrations/dify_n8n/`，运维脚本沿用 `deploy/`、`scripts/` 的现有分类；需要平台 Provider 改动时交给朱明钊 |

两个“不要放错”的例子：

- 改告警页面时，不要把组件放进 `frontend/src/platform/`，它属于生产监控。
- 改 AI Provider 时，不要把代码放进 `backend/integrations/dify_n8n/`，它属于 AI 助手模块。

如果一个文件同时被多个模块使用，或者无法判断归属，**先问洪佳琪，不要自行新建 `common/`、`utils2/` 或另一套目录。**

## 7. 每个人接手时看什么

| 人员 | 接手入口 |
|---|---|
| 钱鸣 | [模型库 README](frontend/src/modules/model-library/README.md) |
| 季世庆 | [生产监控 README](frontend/src/modules/production-monitor/README.md) |
| 朱明钊 | [AI 助手 README](frontend/src/modules/ai-assistant/README.md) |
| 洪佳琪 | [系统管理 README](frontend/src/modules/system-admin/README.md)；维护公共底座时再看 [platform README](frontend/src/platform/README.md) |
| 张亮 | 按本文件第 2、6 节确认集成边界；平台业务需求仍回到对应模块负责人 |

交接负责人可以直接对成员这样说：

> 你负责这个业务模块的前端和后端。前端只先看你自己的模块，后端只先看 `backend/modules/` 下的同名业务模块。接口放 `routes/`，业务逻辑放 `services/`。需要改数据库表、公共配置、公共入口或 `core/` 时先找洪佳琪，不要把业务代码塞进公共根文件。

## 8. 开发和审核的最低规则

1. 从 `ver3` 创建自己的功能或修复分支，不直接推送到 `ver3`。
2. 一个 PR 聚焦一个模块、一件事，不把多个业务和部署脚本捆在一起。
3. 只改自己模块，由模块负责人安排人工审核。
4. 改到别人的模块，在 PR 中说明原因并请对方审核。
5. 改到公共代码、内核、工程配置或无法确定归属的共享文件，必须请洪佳琪最终审核。
6. PR 中写清修改模块、测试命令和测试结果，以及是否修改公共文件。
7. 当前 `CODEOWNERS` 规则仍为注释状态，GitHub 不会自动强制指定审核人，必须主动找人审核。
8. 真实密码和本机凭据不写进文档，也不提交到仓库。

## 9. 管理者检查清单

每次交接或合并前，只重点检查下面几项：

- [ ] 成员是否知道自己的前端目录、后端目录和模块 README。
- [ ] 新业务代码是否进入对应负责人的 `modules/`。
- [ ] 是否有人把业务代码放进 `main.py`、`database.py`、`core/` 或前端 `platform/`。
- [ ] 修改数据库表、公共 Schema、公共配置或启动入口时，是否经过协调和审核。
- [ ] Dify/n8n 平台 Provider 与外部集成资产是否分错负责人。
- [ ] PR 是否聚焦一个模块，并写清测试和审核情况。
- [ ] 是否误用了旧 Archify 图、历史归档目录或已删除的旧后端路径。
