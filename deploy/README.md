# FabTwin Pro — deploy/ 目录说明

> 最后更新：2026-11-07
> 适用分支：ver3
> 本目录是「FabTwin 上线部署」专用脚本集合，按用途分 6 类。
> 完整的端到端说明见 [`../docs/sops/DEPLOY_SOP.md`](../docs/sops/DEPLOY_SOP.md)（在线打包 → 离线安装 → 离线启动 全流程）。
> 上线前请先读本文第 7 节「安全上线三件事」（SSO 共享密钥、管理员恢复、AI 会话迁移预检）。

---

## 1. 总体分类

| 分类 | 文件数 | 主要用途 | 你常用的入口 |
|---|---|---|---|
| A. **在线打包** | 1 | 在联网机器上把项目打成离线部署包 | `package_offline.bat` |
| B. **离线启动（生产环境）** | 8 | 在离线/量产机上启动后端 + 前端 | `deploy_iis_nt_final.bat` → `start_iis.bat` |
| C. **离线启动（开发模式）** | 1 | 带热更新的开发启动（Vite dev + FastAPI，并尝试启动 db_proxy） | `start-dev.bat` |
| D. **数据库初始化** | 1 | 用 sqlplus 初始化 Oracle 库 | `init_db.bat` |
| E. **AI 子系统部署** | 2 | Dify / n8n 的 Docker Compose 一键部署 | `deploy_dify.ps1` / `deploy_n8n.ps1` |
| F. **共享资源** | 2 | 环境变量 / IIS 反代配置 | `env.bat` / `web.config` |
| **合计** | **15** | — | — |

---

## 2. 每个文件详细功能

### A. 在线打包（1 个）

#### `package_offline.bat`
- **作用**：在**联网的开发机**上把整个 FabTwin 项目打成离线 zip 部署包 `fabtwin-deploy-YYYYMMDD.zip`
- **包含**：后端代码 + 前端 dist + node_modules + Python wheels + SQL + IIS 配置 + db_proxy + docs/integration/（Dify/n8n 工作流）
- **输出**：`fabtwin-deploy-YYYYMMDD.zip`（位于项目根）
- **使用场景**：新版功能完成后，准备发版到量产服务器前
- **注意**：仅在**联网机**运行；生成的 zip 可拷到任何离线机解包使用
- **见 SOP**：[docs/DEPLOY_SOP.md 第 2 章](../docs/sops/DEPLOY_SOP.md)

---

### B. 离线启动 — 生产模式（8 个）

#### `deploy_iis_nt_final.bat`
- **作用**：**全新部署 IIS 站点**（含 Windows 认证 + ASP 桥接 + WebSocket 启用）
- **做了什么**：
  1. 检查 IIS / ASP / Windows Auth / WebSocket 4 个 feature
  2. 把 `frontend\dist\` 整个拷到 `C:\inetpub\wwwroot\FabTwin`
  3. 拷 `get_user.asp` + `web.config` 到 IIS 站点目录
  4. 用 `appcmd` 建站点 + 应用池 + 配认证
  5. 设置 IIS 站点访问 `get_user.asp` 时使用 Windows 认证
- **何时用**：第一次在新服务器上部署；或 IIS 配置被改坏后想重建
- **不**启动后端 — 由 `start_iis.bat` 负责
- **见 SOP**：[docs/DEPLOY_SOP.md 第 6 章](../docs/sops/DEPLOY_SOP.md)

#### `start_iis.bat`
- **作用**：**薄包装**，委托给 `start_iis.ps1`（避免 PowerShell 执行策略问题）
- **何时用**：每次启动后端时（IIS 模式生产环境）
- **快捷方式**：建议在桌面建一个指向此文件的快捷方式

#### `start_iis.ps1` ⭐ **你目前的主启动入口**
- **作用**：在 IIS 模式下**启动后端进程**
- **做了什么**：
  1. 解析 `env.bat`（Oracle 连接信息）
  2. 动态生成 `backend\_run_iis.ps1`
  3. 在新窗口里启动 FastAPI（端口 8002）
  4. 打印端口 + 防火墙提示
- **架构**：浏览器 → IIS（静态+API 反代）→ FastAPI 8002
- **WebSocket 走法**：前端**直连** 8002，不经 IIS（IIS URL Rewrite 不支持 WebSocket 握手）
- **何时用**：每次服务器重启后启动后端
- **见 SOP**：[docs/DEPLOY_SOP.md 第 7 章](../docs/sops/DEPLOY_SOP.md)

#### `start_direct.bat`
- **作用**：薄包装，委托给 `start_direct.ps1`

#### `start_direct.ps1`
- **作用**：**直连模式**启动（无需 IIS），同时启动 Vite preview（脚本未传端口，默认 4173）+ FastAPI (8002)
- **做了什么**：
  1. 解析 `env.bat`
  2. 自动检测 `backend\wheels\` 目录（若有则离线 pip install）
  3. 在两个新窗口里分别启动前后端
- **架构**：浏览器 → Vite preview（默认 4173，同时代理 /api + /ws 到 FastAPI 8002）
- **何时用**：不想装 IIS；或在内网做临时部署
- **见 SOP**：[docs/DEPLOY_SOP.md 第 7 章（直连模式）](../docs/sops/DEPLOY_SOP.md)

#### `start_backend.bat`
- **作用**：薄包装，委托给 `start_backend.ps1`

#### `start_backend.ps1`
- **作用**：**只启动后端**（前端由外部 Nginx / 别的容器管理）
- **何时用**：与 Nginx 反代配套；或后端调试时只想看后端日志

#### `web.config`
- **作用**：IIS URL Rewrite 配置
- **规则**：
  - `^api/(.*)` → `http://127.0.0.1:8002/api/{R:1}`
  - `^ws/(.*)` → `http://127.0.0.1:8002/ws/{R:1}`
  - `^uploads/(.*)` → `http://127.0.0.1:8002/uploads/{R:1}`
  - SPA fallback：其它请求 → `index.html`
- **何时用**：被 `deploy_iis_nt_final.bat` 自动拷贝到 IIS 站点目录
- **不要手动改这个文件，除非 IIS 端口或后端端口变了**

---

### C. 离线启动 — 开发模式（1 个）

#### `start-dev.bat`
- **作用**：**开发模式**启动（带热更新），同时启动 Vite dev (5173) + FastAPI (8002)，并尝试启动 db_proxy (8001)
- **与 start_direct.ps1 的区别**：用 `npm run dev` 而非 `npm run build && npx vite preview`
- **何时用**：本地写代码、调前端 Vue 组件时
- **不要在生产服务器上用**

---

### D. 数据库初始化（1 个）

#### `init_db.bat`
- **作用**：用 **sqlplus** 执行 `sql\init_oracle_db.sql` 初始化 Oracle 库
- **做了什么**：
  1. 自动探测 `ORACLE_HOME`（注册表 + 常见路径 + Instant Client 目录）
  2. 从 `env.bat` 读 Oracle 连接串
  3. 调 sqlplus 执行 SQL 脚本
  4. 输出日志到 `init_db.log`
- **何时用**：第一次部署新环境；或 schema 变更后
- **见 SOP**：[docs/DEPLOY_SOP.md 第 5 章](../docs/sops/DEPLOY_SOP.md)

---

### E. AI 子系统部署（2 个）— **可选**

#### `deploy_dify.ps1`
- **作用**：**Dify** Docker Compose 一键部署（postgres + redis + weaviate + sandbox + api + worker + web）
- **支持 action**：`install | start | stop | restart | status | logs | uninstall`
- **默认端口**：8088（Web UI）、5433（postgres）、6380（redis）
- **何时用**：需要 AI Agent 编排能力时
- **见 SOP**：[docs/integration/DEPLOY_SOP.md 第 2~6 步](../docs/integration/DEPLOY_SOP.md)

#### `deploy_n8n.ps1`
- **作用**：**n8n** Docker Compose 一键部署（postgres + n8n 主容器）
- **支持 action**：`install | start | stop | restart | status | logs | uninstall | import`
- **额外能力**：`-Action import` 自动导入 10 个 F1~F10 工作流（来自 `docs/integration/n8n/*.json`）
- **默认端口**：5678（Web UI）、5434（postgres）
- **默认账号**：admin / `FabTwin#2026!N8n`
- **何时用**：需要 n8n 工作流编排（AI 工具调用靠它）
- **见 SOP**：[docs/integration/DEPLOY_SOP.md 第 2~3 步](../docs/integration/DEPLOY_SOP.md)

---

### F. 共享资源（2 个）

#### `env.bat` ⭐ **每个部署都要读它**
- **作用**：**环境变量配置**（Oracle 连接 + DSN 类型 + Client 路径）
- **当前内容**（示例）：
  ```bat
  set DB_TYPE=oracle
  set ORACLE_HOST=10.30.8.119
  set ORACLE_PORT=1521
  set ORACLE_SERVICE=APCDB
  set ORACLE_USER=emuuser
  set ORACLE_PASSWORD=...
  set ORACLE_DSN_TYPE=sid
  set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1
  set SIMULATION_ENABLED=False
  set DB_POLLER_ENABLED=True
  ```
- **被谁读**：`start_iis.ps1` / `start_direct.ps1` / `start_backend.ps1` / `init_db.bat` / `package_offline.bat`
- **何时改**：换数据库 / 换端口 / 换 Client 路径时
- **不要把真实密码提交到 git**（已经在 .gitignore 里）
- **SSO 部署还需追加两个变量**：`FABTWIN_SSO_TRUSTED_PROXIES` 和 `FABTWIN_SSO_SHARED_KEY`，详见第 7 节。

#### `web.config`
- 见上面 B 节「离线启动」中的说明。

---

## 3. 你目前「每次启动」会碰到的 3 个文件

按你之前说的「`deploy_iis_nt_final.bat` + `start_iis.ps1` 是主入口」：

| 场景 | 跑哪个 | 频率 |
|---|---|---|
| **服务器重启后第一次部署** | `deploy_iis_nt_final.bat` | 一次性 |
| **每次启动后端服务** | `start_iis.bat`（或 `start_iis.ps1`） | 每次 |
| **临时改个 Oracle 连接串** | 编辑 `env.bat`，再跑 `start_iis.bat` | 不定期 |

---

## 4. 不在本目录的相关组件

| 组件 | 位置 | 端口 | 说明 |
|---|---|---|---|
| **db_proxy**（db 转抛服务） | `../services/db_proxy/` | 8001 | AI 集成用，独立部署，详见 [docs/integration/DEPLOY_SOP.md](../docs/integration/DEPLOY_SOP.md) 第 1 步 |
| **后端** | `../backend/` | 8002 | FastAPI 主服务 |
| **前端** | `../frontend/` | 5173 (dev) / 4173 (preview 默认) | Vue 3 + Vite |
| **Dify**（可选） | Docker Compose | 8088 | AI Agent 编排 |
| **n8n**（可选） | Docker Compose | 5678 | 工作流引擎 |

---

## 5. 已归档的旧脚本（见 `archive/2026-09-23-pre-cleanup/deploy/`）

下面两个脚本因已被替代，已删除（备份在 archive/）：

- ~~`deploy.bat`~~ — 通用部署脚本，与 `deploy_iis_nt_final.bat` 重复度高，且引用了不存在的 `_test_db.py`
- ~~`one_click_deploy.bat`~~ — 与 `deploy.bat` 80% 相同

---

## 6. 完整流程速查

```
[在线机器]                                              [离线量产机]
                                               
package_offline.bat  ──生成──►  fabtwin-deploy-XXX.zip
                                               
                                          │ 传输（U盘/内网）
                                          ▼
                                         解压
                                          │
                                          ▼
                                  deploy_iis_nt_final.bat   ← 装 IIS
                                          │
                                          ▼
                                  init_db.bat                ← 装库（如果新环境）
                                          │
                                          ▼
                                  编辑 env.bat              ← 配连接
                                          │
                                          ▼
                                  start_iis.bat             ← 启动后端
                                          │
                                          ▼
                                     ✅ 上线
```

详见 [`docs/sops/DEPLOY_SOP.md`](../docs/sops/DEPLOY_SOP.md)。

---

## 7. 安全上线三件事

ver3 起后端对认证做了强制收紧（见 `backend/modules/system_admin/routes/auth.py`）。上线前务必完成下面三项，否则会直接影响登录。

### 7.1 SSO 共享密钥配置（IIS 模式必做）

后端只接受**同时满足**两个条件的 Windows SSO 请求：

1. 请求来源 IP 在 `FABTWIN_SSO_TRUSTED_PROXIES` 白名单内（逗号分隔，填 IIS 服务器本机地址，如 `127.0.0.1`）；
2. 请求头 `X-FabTwin-SSO-Key` 与环境变量 `FABTWIN_SSO_SHARED_KEY` 完全一致（恒定时间比较）。

`env.bat` 追加示例（**真实密钥不要提交 git**）：

```bat
set FABTWIN_SSO_TRUSTED_PROXIES=127.0.0.1
set FABTWIN_SSO_SHARED_KEY=换成一段足够长的随机串
```

- 两个变量任一未配置，后端对 Windows SSO 直接返回 403「Windows SSO 未配置」；密钥不匹配返回 401。
- **当前限制（未验证项）**：`scripts/archive/get_user.asp` 与 `web.config` 的反代链路**尚未注入** `X-FabTwin-SSO-Key` 头，真实 IIS 环境下的端到端 SSO 未验证。在未完成 IIS 侧改造前，请让用户走密码登录（直连模式本就走密码登录，不受影响）。
- IIS 侧改造方向：由 IIS 在转发到后端时注入 `X-FabTwin-SSO-Key` 与 `X-Forwarded-User` 两个头，并确保外部客户端无法自行伪造这两个头到达后端（后端只信任白名单 IP，但不要在边界上再开缺口）。

### 7.2 管理员恢复流程

- **预防**：上线时保留**至少两个**已验证可登录的管理员账号；旧弱密码账号逐个安全重置。
- **全部管理员失锁时**（应急恢复，在数据库服务器上操作）：
  1. 用后端同款算法离线生成新密码哈希（需要后端环境的 Python）：
     ```bat
     python -c "import sys; sys.path.insert(0, 'backend'); from core.services.security import hash_password; print(hash_password('新密码'))"
     ```
  2. 用 sqlplus 更新目标管理员账号：
     ```sql
     UPDATE USERS SET PASSWORD_HASH = '<上一步输出的 pbkdf2_sha256$... 串>'
     WHERE USERNAME = 'admin';
     COMMIT;
     ```
  3. 用新密码登录后，立即在用户管理页再改一次密码，并核查其他账号权限。
- 注意：`PASSWORD_HASH` 为空（NULL/空串）的账号**无法本地登录**（后端显式拒绝），不要把清空密码当作恢复手段。

### 7.3 AI 会话迁移预检（从旧版本升级必做）

ver3 对 `AI_CONVERSATIONS` 做了属主隔离整改（`USER_ID` 列 + 新索引）。升级脚本为 [`../sql/v2.14_ai_conversations_owner.sql`](../sql/v2.14_ai_conversations_owner.sql)，脚本头部自带预检 SQL：

1. **先跑预检**（脚本注释内的 SELECT）：确认 `SESSION_ID` 无重复、`USER_ID` 无 NULL 残留；预检不通过不要执行后续 ALTER。
2. 按脚本顺序执行前向迁移（加 `USER_ID_NEW` → 回填 → 换列 → 建索引）。
3. 跑脚本尾部的验证 SQL 确认行数与索引。
4. 参考记录：本仓库在 2026-11-04 已在真实 Oracle 核验过 `AI_CONVERSATIONS` 迁移（含四个平台索引与目标列宽），详见 `PROJECT_STATUS.md`。
- 未执行该迁移就启动新版后端时，历史会话会被视为"无属主"，用户侧表现为旧会话不可见（属主隔离策略，属预期行为而非数据丢失）。