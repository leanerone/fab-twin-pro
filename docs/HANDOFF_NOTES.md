# FabTwin Pro — 下次接手须知（HANDOFF NOTES）

> **用途**：给新会话（Codex / 任何 AI Agent / 任何人类工程师）的"上下文急救包"，30 分钟内补齐历史背景。
>
> **更新**：2026-09-23（v2.9.x DB 修复轮后）
>
> **核心原则**：本文件只写"为什么 / 决策 / 禁止事项"，不写"怎么用"——怎么用去看具体文档。

---

## 0. 30 秒项目快照

| 项 | 值 |
|---|---|
| **项目名** | FabTwin Pro |
| **行业** | 半导体 FAB（8 寸 / 12 寸晶圆厂）实时可视 + AI 助手 |
| **核心功能** | 1) 车间 3D 可视化（楼层 / 区域 / 机台 / OHT）<br>2) 机台状态实时监控（OXE 刻蚀机 / VPO 立式氧化炉 / PODOPENER / STK / WAT / WS 等）<br>3) 报警 + 配方管理<br>4) AI 助手（Dify + n8n + 多 Provider LLM）<br>5) AI 自动路由（按 MODEL_ID 路由到不同 Dify App，v2.9.1 新增） |
| **技术栈** | **后端**：FastAPI + SQLAlchemy + Oracle（Thick 模式连接）<br>**前端**：Vue 2 + Element UI + ECharts + Three.js<br>**AI 子系统**：Dify（docker-compose）+ n8n + db_proxy（自研 Go 中间件） |
| **部署形态** | Windows IIS + FastAPI（uvicorn）+ Oracle 19c |
| **代码仓** | `C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro` |
| **远程** | `origin` → `leanerone/fab-twin-pro`<br>**当前工作分支**：`test1` |
| **当前 commit** | `a649045`（"fix(db): DB 恢复机制 + 初始化完整性修复"） |
| **当前版本号** | v2.9.x |

---

## 1. 决策日志（Decisions Log）

> **为什么需要这个**：让接手者不用"反推为什么"。每个决策都带选项和理由。

| # | 日期 | 决策 | 选项 | 选择 | 理由 / 反向警告 |
|---|---|---|---|---|---|
| D1 | 2026-09-23 | `deploy/` 17 个脚本清理策略 | A. 扁平保留 + 写 README<br>B. 全部移到 archive/<br>C. 只留 1 个总入口 | **A** | 用户明确指示"用选项 A"。理由：部署脚本还需要用，不能全删 |
| D2 | 2026-09-23 | `docs/` 文档归档方式 | A. business/ + archive/ 双目录<br>B. 单一 archive/ | **A** | 业务文档（对接规范 / OXE 接入 / 新机台 SOP）需要常驻；技术归档走 archive/ |
| D3 | 2026-09-23 | DB 恢复机制依赖 | A. ORM 自动 + 手工 SQL 双层<br>B. 纯 SQL 脚本 | **A** | `backend/database.py:init_db()` 已自动建 20+ 张表；3 张 AI 表因 init_db 显式 exclude 必须手工 SQLPLUS（详见 [sql/create_ai_tables.sql](../sql/create_ai_tables.sql)） |
| D4 | 2026-09-23 | VPO-01 数据悬空引用 | A. 在 MACHINES 加一条 VPO-01<br>B. 把 mapping + recipes 改成 PODOPENER-1 | **A** | **保留 recipe 的工艺归属语义**：REC-ETCH-A-VPO-01 是"工艺模板"，不绑定特定机台；加一台 VPO-01 别名机台（MODEL=PODOPENER-2200, PROCESS_TYPE=VPO）是最小变更。**反向警告**：不要去改 recipes，会破坏语义 |
| D5 | 2026-09-23 | MACHINE_DIFY_CONFIGS 双重创建冲突 | A. PL/SQL 块 + EXCEPTION_INIT -955 幂等<br>B. 改 ORM 用 NUMBER + 手工 sequence | **A** | 后端 ORM 跑的是 SQLAlchemy Identity 列版本（`Identity(start=1)`），手工 SQL 是 NUMBER + sequence + trigger OLD VERSION。**冲突点**：第二次跑 SQL 会 ORA-00955 报"对象已存在"。**修复**：CREATE TABLE 包 PL/SQL 块捕 ORA-00955 跳过；trigger 加 `WHEN (NEW.ID IS NULL)` 谓词兼容 Identity 列不触发；sequence 也独立包块兜底 |
| D6 | 2026-09-23 | DEPLOY_SOP.md §7 重写 | A. 拆 7.1 / 7.2 / 7.3 三个子节<br>B. 加脚注 | **A** | 强制提示"create_ai_tables.sql init_db.bat 不跑，必须手工 sqlplus"，避免新人部署漏跑导致 AI 配置中心 500 |

---

## 2. 当前 todo 与上次 TODO（已完成 / 遗留 / 下一步）

### 2.1 ✅ 最近 3 个 commit 已完成的工作

| commit | 内容 |
|---|---|
| `a649045` | fix(db): DB 恢复机制 + 初始化完整性修复 (v2.9.x) — 3 文件 |
| `5ab44d9` | refactor(deploy): deploy/ + docs/ 整理归档 — 81 文件 |
| （更早） | ... 见 `git log --oneline` |

### 2.2 ⏳ 遗留 / 半成品

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| L1 | `deploy/init_db.bat` modified 状态 | **未提交** | 仅 LF→CRLF 行尾变化（编辑器自动改的），不是功能变更。**不要为了清掉它再制造一个 commit**，等下次有真实功能变更一起提交 |
| L2 | `frontend/src/views/MachineDetail.vue` 用户最近改过 | **未审阅** | 看 git blame 检查最近变更是否影响 AI 自动路由（Dify ConfigBase 调用） |
| L3 | E2E 验证脚本缺失 | **未实现** | 没有自动化测试覆盖"登录→Dashboard→机台管理→AI 配置"全链路 |

### 2.3 🎯 下一步建议（按优先级）

| # | 任务 | 预期收益 | 备注 |
|---|---|---|---|
| **N1** | 验证 `deploy/init_db.bat` 幂等性 | 确认重跑不报错 | 找一个干净的 schema 跑两遍，验证不会 ORA-00955 |
| **N2** | 跑一次完整 `create_ai_tables.sql` 验证幂等 | 同上，重点是 MACHINE_DIFY_CONFIGS 那段 | 若已建过（ORM Identity 版）应只刷新 trigger/sequence |
| **N3** | 写 E2E 验证脚本（Playwright / pytest） | 防回归 | 优先级 N3 是长期项，本次会话不做 |
| **N4** | 审阅 `frontend/src/views/MachineDetail.vue` 的最近变更 | 防前端 API 路径变更 | 用户最近改过，需要 lint 走一遍 |

---

## 3. 关键路径速查表（接手前先 cat 一下）

### 3.1 后端核心文件

| 路径 | 作用 | 接手必读 |
|---|---|---|
| `backend/main.py` | FastAPI 入口，启动时调 `init_db()` | 是 |
| `backend/database.py` | `init_db()` + `_ensure_missing_columns()`（自动建表 + 补 display_order 列） | ⭐ 必读 |
| `backend/models.py` | 24 张 ORM 模型定义 | ⭐ 必读 |
| `backend/seed_data.py` | Python 版种子数据（与 init_oracle_db.sql 同步） | 否（仅手动触发用） |
| `backend/routers/` | API 路由（按业务模块分） | 按需 |
| `backend/services/ai_middleware.py` | AI 调用中间件（Dify/N8N/Provider 调度） | ⭐ 改 AI 功能时必读 |

### 3.2 SQL 脚本（按执行顺序）

| 顺序 | 脚本 | 触发方式 | 关键点 |
|---|---|---|---|
| 1 | `sql/init_oracle_db.sql` | `deploy/init_db.bat` 自动 | **含 20 张平台表 + 204 种子数据**（2026-09-23 修后变 205 条，含 VPO-01） |
| 2 | `sql/create_ai_tables.sql` | **手工 sqlplus**（init_db.bat 不调） | **必跑**，否则 AI 全 500；2026-09-23 改幂等 |
| 3 | `sql/create_dt_tables.sql` | **不需要手工跑**（ORM 自动建） | init_db() 自动 create_all 已覆盖 |

### 3.3 ⚠️ 不要跑的脚本（已废弃 / 增量已并入）

| 脚本 | 状态 | 替代 |
|---|---|---|
| `sql/v2.0_upgrade_animation_config.sql` | **已废弃**（已并入 init_oracle_db.sql） | 用主脚本 |
| `sql/v2.1_add_mcp_config.sql` | **已废弃**（已并入 create_ai_tables.sql lines 182-193） | 用 create_ai_tables.sql |
| `sql/v2.6_add_machine_external_link.sql` | 旧环境增量升级用 | 新环境主脚本已含 |
| `sql/v2.7_add_display_order.sql` | 旧环境增量升级用（**新环境主脚本已含，且 backend _ensure_missing_columns 自动补**） | 用主脚本 |

### 3.4 前端路径

```
frontend/
├── src/
│   ├── views/
│   │   ├── Dashboard.vue           # 主仪表盘
│   │   ├── MachineDetail.vue       # 机台详情（含 AI 自动路由入口，v2.9.1）
│   │   ├── MachineManagement.vue   # 机台管理（38 台主数据 CRUD）
│   │   ├── AIConfigView.vue        # AI 配置中心（Provider / KV / MCP）
│   │   ├── ModelEditor.vue         # 工艺编辑器
│   │   ├── UserManagement.vue      # 用户管理
│   │   └── Login.vue
│   ├── api/                        # axios 封装
│   └── router/                     # Vue Router
```

### 3.5 文档目录

```
docs/
├── HANDOFF_NOTES.md                 ← 本文件
├── README.md                       ← docs 导航
├── DEPLOY_SOP.md                   ← ⭐ 端到端部署 SOP
├── 系统架构说明书.md               ← 架构总览
├── 变更更改版记录.md               ← 跨版本变更日志
├── business/                       ← 业务文档（对接 / OXE 接入 / 新机台 SOP）
├── integration/                    ← AI 子系统文档（Dify/n8n/db_proxy）
└── archive/                        ← 归档（过期/历史）
```

---

## 4. ⚠️ 禁止事项（接手必读）

1. **禁止重跑** `sql/v2.0_upgrade_animation_config.sql` — 内容已并入主脚本
2. **禁止重跑** `sql/v2.1_add_mcp_config.sql` — 内容已并入 `create_ai_tables.sql`
3. **禁止删除** `archive/` 目录任何文件 — 历史留底
4. **禁止把** `init_db.bat` 的 ORACLE_HOME 检测逻辑改回老 `deploy.bat` 的版本 — 2026-09-23 已重写
5. **禁止手工改** `MACHINES` 表里 RECIPES 引用的机台名 — 会断外键关联（v2.9.x 加 VPO-01 是有依据的，不要再改）
6. **禁止单独跑** `sql/create_ai_tables.sql` 后再让后端启动 — **会**因 ORA-00955 报"对象已存在"，新版本已经做幂等兜底，不会再报错，但请保持顺序：先 `init_db.bat` → 再手工 `create_ai_tables.sql` → 再启动后端
7. **不要把** `docs/PROJECT_STATUS.md`（已移到 archive/ 或被删除）当作权威 — 它已经被 docs/README.md 替代

---

## 5. 接手后第一个 commit 应包含什么

如果你要继续开发，建议第一个 commit 至少做这些检查：

```bash
# 1. 看 git 状态
cd "C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro"
git status
git log --oneline -5

# 2. 检查依赖（如有 requirements.txt / package.json）
# （按当前文件来）

# 3. 看本次会话的变更点
git diff HEAD~1 --stat

# 4. 看 N1/N2/N4 哪条要继续做
cat docs/HANDOFF_NOTES.md   # 即本文件
```

---

## 6. 联系信息 / 上次会话锚点

- **上次 commit 锚点**：`a649045`（从这往后接）
- **上次会话关键人物**：TRAE Solo Agent（开发协作）+ 用户 A（需求方）
- **协作节奏**：每个 commit 后立即 `git push origin test1`（避免本地堆积）
- **用户语言**：简体中文（产品/业务沟通）+ 英文（技术名词）

---

## 7. 一句话总结

**项目处于 v2.9.x 稳定期，DB 恢复机制已修，3 个 SQL 脚本已优化；下一步是验证幂等性 + 写 E2E 测试 + 审阅 MachineDetail.vue 最近变更。**