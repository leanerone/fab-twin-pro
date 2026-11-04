# FabTwin Pro

> **新人只看这一条阅读路径：先读本文件 → 再读自己模块的 README。** 不要先翻 `docs/`，也不要照搬历史归档里的目录和命令。

## 1. 先知道自己在做什么

FabTwin Pro 是半导体机台数字孪生监控系统，包含：

- **模型库**：SVG / 2D Motion / 3D 模型资产，模型编辑、上传和动画预览。
- **生产监控**：总览、楼层、机台详情、历史回放、Lot、告警、配方、OHT 和实时事件。
- **AI 助手**：问答、流式输出、Text-to-SQL、Provider 配置、语音和 AI 配置界面。
- **系统管理**：登录、用户、角色和权限。
- **外部集成**：Dify / n8n 集成资产、运维脚本和 Oracle 只读 `db_proxy`。

前端是 Vue 3 + Vite，后端是 FastAPI + SQLAlchemy。**后端当前只支持 Oracle，不是 SQLite/mock；本地启动前必须先有可连接的开发 Oracle。**

## 2. 找对自己的负责人和目录

每个人都纵向负责一个业务模块的前端和后端，不是一个人只写前端、另一个人再接手同模块后端。

| 人员 | 负责什么 | 主要目录 |
|---|---|---|
| **钱鸣** | 模型库；模型与资产 | `backend/modules/model_library/`、`frontend/src/modules/model-library/`、`models/`、`frontend/public/models/`、`frontend/src/api/{models,uploads}.js` |
| **季世庆** | 生产监控 + 团队总控；协调进度与合并冲突 | `backend/modules/production_monitor/`、`frontend/src/modules/production-monitor/`、`backend/seed_oxe_test_data.py`、`frontend/src/api/{machines,history,floors}.js`；其中 `seed_vpo_motion.py` 也归季世庆 |
| **朱明钊** | AI 助手，包括 Dify/n8n 的**平台 Provider 代码** | `backend/modules/ai_assistant/`、`frontend/src/modules/ai-assistant/`、`frontend/src/api/ai.js` |
| **洪佳琪** | 系统管理过渡、平台内核、公共代码与最终审核 | `backend/modules/system_admin/`、`frontend/src/modules/system-admin/`、后端根公共文件、`backend/core/`、`frontend/src/platform/`、`frontend/src/api/{core,index,auth}.js` |
| **张亮** | 集成资产、运维脚本和 `db_proxy`，**不负责平台业务代码** | `backend/integrations/dify_n8n/`、`services/db_proxy/`、Dify/n8n 相关 `deploy/` 与 `scripts/` 资产 |

特别分清两件事：

- `backend/modules/ai_assistant/services/providers/` 里的 Dify/n8n Provider 是平台业务代码，归**朱明钊**。
- Dify/n8n 工作流、部署运维、集成脚本和 `services/db_proxy/` 归**张亮**；不要让他另写一套业务路由或业务服务。

公共代码不是“谁顺手谁改”。后端根入口、公共配置/模型/Schema、`backend/core/`、前端 `platform/` 和全局构建配置，改动都必须交给**洪佳琪审核**。涉及别的业务模块时，还要该模块负责人审核。

## 3. 现在真实的目录

下面是放代码时要看的位置，不是未来规划。

```text
backend/
├── main.py                         # FastAPI 总入口：注册各模块路由
├── config.py / database.py         # 公共配置、Oracle 连接
├── models.py / schemas.py          # 公共 ORM 与 Pydantic 模型
├── seed_data.py / sql_runner.py    # 根级公共种子入口、SQL 执行工具
├── seed_oxe_test_data.py           # 生产监控 OXE 测试种子，归季世庆
├── core/
│   ├── deps.py / events_query.py   # 公共依赖、事件查询
│   └── services/                   # cache / perf / realtime / security / time_utils
├── modules/
│   ├── model_library/
│   │   ├── routes/                 # models.py / uploads.py
│   │   ├── services/               # html_parser.py
│   │   └── seeds/                  # seed_amat_metsput.py / seed_oxe_motion.py
│   ├── production_monitor/
│   │   ├── routes/                 # alarms / debug / events / floors / history / lots
│   │   │                           # machines / oht / oxe / recipes / rvmessages
│   │   ├── services/               # db_poller.py / ods.py / simulator.py
│   │   └── seeds/                  # seed_vpo_motion.py
│   ├── ai_assistant/
│   │   ├── routes/                 # ai.py
│   │   └── services/               # middleware / tools / sql / config_store / ...
│   │       └── providers/          # openai / dify / n8n 等 Provider
│   └── system_admin/
│       └── routes/                 # auth.py / users.py
└── integrations/
    └── dify_n8n/                   # 集成设置与连接资产；不是新业务模块

frontend/src/
├── main.js / App.vue               # 前端公共入口与应用装配
├── api/                            # 现有接口文件，按责任表分模块归属
├── stores/ / router/               # 全局状态与路由，公共代码
├── utils/ / styles/ / configs/     # 公共工具、样式、配置
├── modules/
│   ├── model-library/
│   │   ├── frontend/               # engine / derivers / editor
│   │   └── README.md               # 钱鸣模块说明
│   ├── production-monitor/
│   │   ├── frontend/               # components / composables / pages
│   │   └── README.md               # 季世庆模块说明
│   ├── ai-assistant/
│   │   ├── frontend/               # components / pages
│   │   └── README.md               # 朱明钊模块说明
│   └── system-admin/
│       ├── frontend/pages/         # LoginPage / UserManagementPage
│       └── README.md               # 洪佳琪模块说明
└── platform/
    ├── frontend/core/composables/  # three / RafLoop / WebSocket 等共享组合函数
    ├── frontend/shell/components/  # AppHeader
    └── README.md                   # 公共平台边界
```

**旧的平铺后端路由、服务目录和 7 个 AI 兼容 shim 已移除。不要再按旧路径建文件。**

## 4. 新需求、新文件到底放哪里

先判断属于哪个模块，再把前后端放在同名业务模块里。下面是可直接对照的例子：

| 新需求 | 后端放这里 | 前端放这里 |
|---|---|---|
| 增加模型上传校验 | `backend/modules/model_library/routes/` 或 `backend/modules/model_library/services/` | 组件放 `frontend/src/modules/model-library/frontend/editor/components/`；上传接口改 `frontend/src/api/uploads.js` |
| 新增一个机台的 SVG / Motion 资产 | 资产放 `models/` 下已有对应位置；模型库专属 seed 放 `backend/modules/model_library/seeds/` | 展示引擎确需修改时放 `frontend/src/modules/model-library/frontend/engine/` |
| 增加告警筛选或 Lot 查询 | `backend/modules/production_monitor/routes/`；可复用业务逻辑放 `backend/modules/production_monitor/services/` | Lot 接口改 `frontend/src/api/history.js`；界面放 `frontend/src/modules/production-monitor/frontend/components/` 或 `frontend/src/modules/production-monitor/frontend/pages/` |
| 增加 AI 查询工具或调整 Provider | `backend/modules/ai_assistant/services/`；Provider 放 `backend/modules/ai_assistant/services/providers/` | 界面放 `frontend/src/modules/ai-assistant/frontend/components/` 或 `frontend/src/modules/ai-assistant/frontend/pages/`；现有接口改 `frontend/src/api/ai.js` |
| 增加用户角色字段或登录规则 | `backend/modules/system_admin/routes/`；共享认证底座在 `backend/core/services/security.py`，必须洪佳琪审核 | 页面放 `frontend/src/modules/system-admin/frontend/pages/`；现有登录接口在 `frontend/src/api/auth.js` |
| 更新 Dify 工作流或 n8n 运维 | 集成资产放 `backend/integrations/dify_n8n/`，运维脚本沿用 `deploy/` / `scripts/` 的现有分类 | 不改平台业务页面；需要平台 Provider 改动时另交给朱明钊 |

再放两个“不要放错”的例子：

- 改告警页面时，不要把组件塞进 `frontend/src/platform/`；它属于生产监控。
- 改 AI Provider 时，不要把代码塞进 `backend/integrations/dify_n8n/`；它属于 AI 助手模块。

如果一个文件同时被多个模块使用，或者你判断不了归属，**先问洪佳琪，不要自己新建 `common/`、`utils2/` 或另一套目录。**

## 5. 新人第一次开发，照这个顺序做

1. 在上面责任表找到自己的名字。
2. 只打开自己模块的第二份文档：
   - 钱鸣：[模型库 README](frontend/src/modules/model-library/README.md)
   - 季世庆：[生产监控 README](frontend/src/modules/production-monitor/README.md)
   - 朱明钊：[AI 助手 README](frontend/src/modules/ai-assistant/README.md)
   - 洪佳琪：[系统管理 README](frontend/src/modules/system-admin/README.md)；维护公共底座时再看 [platform README](frontend/src/platform/README.md)
   - 张亮：按本文件第 2、4 节确认集成边界，平台业务代码仍回到对应模块负责人。
3. 从 `ver3` 建分支，只改本需求需要的一个模块。
4. 按第 8 节运行与改动有关的测试。
5. 发 PR 到 `ver3`，在 PR 里写清改了哪个模块、运行了哪条命令、是否碰了公共文件。

## 6. 启动项目（Windows）

### 6.1 第一次安装

先安装 **Python 3.10+、Node.js 20、可用的 Oracle 开发库和 Oracle Client**。Node.js 20 与当前 CI 一致。

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd ..\frontend
npm ci
```

后端没有通用 mock 开关。启动前请找季世庆确认开发 Oracle 连接参数，并核对 `deploy/env.bat` 中的 `ORACLE_*`、`ORACLE_DSN_TYPE` 和 `ORACLE_CLIENT_DIR`。**真实密码不要写进文档，也不要把本机凭据提交到仓库。**

### 6.2 一键启动前后端

在仓库根目录执行：

```powershell
.\deploy\start-dev.bat
```

脚本会启动后端、前端，并尝试启动 `db_proxy`。普通业务开发如果不需要 `db_proxy`，先按 [deploy/README.md](deploy/README.md) 核对本机配置，不要把代理配置错误当成前端或后端代码错误。

也可以开两个 PowerShell 窗口分别启动。手动后端窗口必须已经设置同样的 `ORACLE_*` 会话或系统环境变量；`deploy/env.bat` 只由 deploy 脚本读取，不会由 `main.py` 自动加载：

```powershell
# 窗口 1：后端，http://localhost:8002
cd backend
.\venv\Scripts\python.exe main.py
```

```powershell
# 窗口 2：前端，http://localhost:3000
cd frontend
npm run dev
```

后端接口文档：`http://localhost:8002/docs`。`services/db_proxy/` 默认端口是 `8001`，只有集成联调需要时才配置和启动。

## 7. 怎么提交，不走丢

### 分支和 PR

```powershell
git switch ver3
git pull
git switch -c feature/qianming-model-library-upload-check
```

分支名用 `feature/你的名字-模块-事情`；修 bug 用 `fix/你的名字-模块-事情`。例如 `fix/jishiqing-production-monitor-alarm-filter`。

- PR 的目标分支选 **`ver3`**，不要直接推 `ver3`。
- **一个 PR 聚焦一个模块、一件事。** 不要把模型库、AI、部署脚本捆在一起。
- 只改自己模块：由模块负责人安排人工审核。
- 改到别人模块：PR 里说明原因，请对方人工审核。
- 改到公共代码、内核、工程配置或拿不准的共享文件：必须请**洪佳琪最终审核**。
- PR 描述按 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) 填，自测结果不要只写“本地没问题”。

### CI 和人工审核都要看

当前 `.github/workflows/ci.yml` 有三个检查：

1. `backend-tests`：安装后端依赖并运行指定回归 pytest。
2. `frontend-build`：执行前端生产构建。
3. `svg-motion-contract`：校验六台机台的 SVG / Motion 契约。

**CI 全绿仍需要人工审核。当前 `CODEOWNERS` 的规则全部保持注释，自动 Code Owner 审核尚未启用。** 所以要在 PR 里主动找对应负责人，不能等系统自动分配，也不能把“没人被自动指派”理解成无需审核。真实 GitHub 账号确认前，不要自行取消 CODEOWNERS 注释。

## 8. 测试命令

以下命令都按仓库现有 CI、脚本和模块 README 写，路径以仓库根目录为起点。

### 后端回归（CI 同款）

```powershell
.\backend\venv\Scripts\python.exe -m pytest tests/test_ai_middleware_regressions.py tests/test_model_draft_validation.py -q
```

### 前端构建（CI 同款）

```powershell
cd frontend
npm run build
```

### 改了模型资产

把文件名换成你实际修改的 SVG / Motion：

```powershell
python models/svg_kit/validate.py models/user/你的模型.svg models/user/你的模型.motion.json
```

### 核心链路冒烟

先启动后端并确保开发 Oracle 数据就绪，再执行：

```powershell
.\backend\venv\Scripts\python.exe tests/smoke_baseline.py
```

真实库读写测试位于 `tests/pytest/`，会使用真实 Oracle，不是无依赖单元测试；运行前先按该目录 README 和季世庆确认环境。AI 专属测试按 [AI 助手 README](frontend/src/modules/ai-assistant/README.md) 执行。

## 9. 还需要查什么

- 部署任务：看 [deploy/README.md](deploy/README.md)。
- 当前进度和历史验证：看 [PROJECT_STATUS.md](PROJECT_STATUS.md)，其中旧日期条目是历史记录，不作为当前目录依据。
- `docs/archive/` 与 `docs/architecture/archive/` 是历史材料，**不是新人操作手册，也不要照着里面的旧路径开发**。
