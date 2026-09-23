# FabTwin Pro 上线部署 SOP

> 最后更新：2026-09-23
> 适用版本：ver2.10.21
> 维护人：项目组
> 文档位置：`docs/DEPLOY_SOP.md`（旧名 `deploy-sop.md` 已废弃）

---

## 〇、读我

这份 SOP 是 FabTwin Pro 的**唯一**端到端部署指南，目标场景：

- **从 0 开始**：在一台**联网机器**上完成开发 → 打包 → 把包带到**离线量产机**安装 → 启动 → 验证
- **已经部署过**：每台离线机器**重启后启动**、**环境变量改动**、**schema 升级**、**AI 子系统独立安装**等
- 整个流程分 **3 大段、9 个步骤**，每步有明确产物和验证命令

**如果你要看每个脚本的功能**，请读 [`../deploy/README.md`](../deploy/README.md)。

**如果你要部署 Dify / n8n / db_proxy 等 AI 子系统**，请读第 7 章并跳转到 [`./integration/DEPLOY_SOP.md`](./integration/DEPLOY_SOP.md)。

---

## 一、架构总览（30 秒看完）

```
┌───────────────────────────────────────────────────────────────┐
│ 浏览器（http://主机名）                                            │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────┐
│ IIS 站点（80/443）                  │
│  ├─ 静态文件 (frontend\dist)        │
│  ├─ /api/   → 转发到 :8002/api/    │   ← URL Rewrite
│  ├─ /uploads/ → 转发到 :8002/      │
│  └─ /ws/ 除外：前端直连后端         │   ← WS 不走 IIS
└────────────────────────┬────────────┘
                         │
                         ▼ (HTTP)
                ┌──────────────────┐         ┌──────────────────┐
                │ FastAPI 8002     │ ←─ WS ─ │ 浏览器           │
                │ (backend\main)   │         └──────────────────┘
                └────────┬─────────┘
                         │
        ┌────────────────┼─────────────────────┐
        ▼                ▼                     ▼
┌───────────────┐ ┌──────────────┐ ┌────────────────────┐
│ Oracle 1521   │ │ db_proxy 8001│ │ AI 子系统（可选） │
│ (生产库)      │ │ (db 转抛)    │ │ ├─ n8n 5678       │
└───────────────┘ └──────────────┘ │ └─ Dify 8088      │
                                   └────────────────────┘
```

**端口清单**（按启动顺序）：

| 端口 | 服务 | 启动命令 | 必选/可选 |
|---|---|---|---|
| 1521 | Oracle | 系统服务 | 必选 |
| 8001 | db_proxy | `services\db_proxy\start.bat` | AI 用，**否则可省** |
| 8002 | backend（FastAPI） | `deploy\start_iis.bat` | 必选 |
| 5173/4173 | frontend（开发/直连模式预览） | `deploy\start-dev.bat` 或 `start_direct.ps1` | 直连模式用 |
| 80/443 | IIS | `iisreset` | 必选（生产） |
| 5678 | n8n | `deploy\deploy_n8n.ps1 -Action start` | 可选 |
| 8088 | Dify | `deploy\deploy_dify.ps1 -Action start` | 可选 |

---

## 二、流程图（一图流）

```
[联网开发机]                                              [离线量产机]
                                               
Step 1. 准备代码 + npm install                               
        │                                                   
Step 2. npm run build → 生成 frontend\dist                  
        │                                                   
Step 3. deploy\package_offline.bat                          
        │  生成 fabtwin-deploy-YYYYMMDD-HHmm.zip               
        │                                                   
        │ 传输（U盘 / 内网）                                  
        ▼                                                   
                                                       Step 4. 解压 zip 到 D:\fabtwin\
                                                       Step 5. 安装 IIS + ASP + Windows Auth
                                                       Step 6. 修改 deploy\env.bat
                                                       Step 7. install_db.bat 初始化库
                                                       Step 8. deploy_iis_nt_final.bat
                                                       Step 9. start_iis.bat
                                                       Step 11. 验证 ✓
                                                       
                                               
Step 10.（可选）deploy_dify.ps1 + deploy_n8n.ps1
```

---

## 三、Step 1~3：在线机器上打包（开发机 / 联网打包机）

### Step 1. 准备代码

```powershell
# 在 fab-twin-pro 项目根
git checkout test1
git pull
```

确认版本号：

```powershell
# backend/config.py 或最新 commit 应反映目标版本
git log --oneline -3
```

### Step 2. 构建前端

```powershell
cd frontend
npm install
npm run build
cd ..
```

验证：

```powershell
# 必须存在 frontend\dist\index.html
Test-Path frontend\dist\index.html   # 应为 True
```

### Step 3. 打包离线部署包

```powershell
cd deploy
.\package_offline.bat
```

**做了什么**（详见 [deploy/README.md §A](../deploy/README.md)）：

1. 复制 `backend/`（含源码、routers、services）
2. `pip download` 把 Python 依赖拉到 `backend\wheels\`
3. 复制 `frontend\dist\` + `frontend\src\` + `frontend\node_modules\`
4. 复制 `services\db_proxy/`（8001 端口的 db 转抛）
5. 复制 `sql\`（Oracle 初始化脚本）
6. 复制 `deploy\`（15 个脚本 + env.bat + web.config + README）
7. 复制 `docs\` + `docs\integration\`
8. 复制 `scripts\archive\get_user.asp`（IIS Windows Auth 桥接）
9. 压缩成 `fabtwin-deploy-YYYYMMDD-HHmm.zip`

**产物**：

- `fabtwin-deploy-YYYYMMDD-HHmm.zip`（通常 200~500 MB，看 wheels 多少）
- `fabtwin-offline-YYYYMMDD-HHmm/`（解压前的中间目录，可保留做调试用）

**传输**：把 zip 拷贝到 U 盘 / 内部网络共享 / 离线服务器的任意临时位置。

---

## 四、Step 4~9：离线机器上安装与启动（量产环境）

### Step 4. 解压到离线机器

把 zip 拷贝到目标离线机器（例如 `D:\` 或 `C:\inetpub\` 旁的任意目录）。

```powershell
# 在离线机上
Expand-Archive D:\fabtwin-deploy-XXXXXXXX.zip -DestinationPath D:\fabtwin
cd D:\fabtwin
dir   # 应看到 backend/ frontend/ services/ sql/ deploy/ docs/
```

> **目录选择没有硬规定**。只要路径里没有空格 / 中文 / 太深（≤ 5 层），即可。推荐放在 `D:\fabtwin\` 或 `C:\apps\FabTwin\`。

### Step 5. 安装 IIS 与必需 feature（仅新机器）

以管理员运行 PowerShell：

```powershell
Install-WindowsFeature -Name Web-Server,Web-Asp,Web-Windows-Auth,Web-WebSocket -IncludeManagementTools
iisreset
```

**4 个 feature 都要装**：

| feature | 用途 | 缺了会怎样 |
|---|---|---|
| `Web-Server` | IIS 主程序 | 根本起不来 |
| `Web-Asp` | 运行 `get_user.asp`（Windows Auth 桥接） | 前端拿不到当前域用户 |
| `Web-Windows-Auth` | `get_user.asp` 读取 `LOGON_USER` | 同上 |
| `Web-WebSocket` | WS 握手支持（虽然我们走直连，但 feature 启用是惯例） | — |

### Step 6. 修改 deploy\env.bat

```bat
@echo off
REM === Oracle ===
set ORACLE_HOST=10.30.8.119
set ORACLE_PORT=1521
set ORACLE_SERVICE=APCDB
set ORACLE_USER=emuuser
set ORACLE_PASSWORD=<填入实际密码>
set ORACLE_DSN_TYPE=sid                  REM 11g/10g 填 sid，12c+ 填 service_name

REM === Oracle Client（仅 DSN_TYPE=sid 时必填，Thin 模式可空）===
set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1

REM === 应用端口 ===
set FABTWIN_BACKEND_PORT=8002
set FABTWIN_FRONTEND_PORT=5173
```

> **ORACLE_DSN_TYPE 怎么选**：
> - `sid` — 老库（10g/11g），需要装 Oracle Client（指向 `ORACLE_CLIENT_DIR`）
> - `service_name` — 新库（12c+），纯 Python oracledb，不需要 Client
>
> **ORACLE_PASSWORD 不要 commit 进 git**（已在 `.gitignore` 屏蔽 deploy\env.bat 的实际值）

### Step 7. 初始化 Oracle 库（仅新环境 / schema 变更时）

```powershell
cd deploy
.\init_db.bat
```

**做了什么**：用 sqlplus 执行 `sql\init_oracle_db.sql`，输出日志到 `init_db.log`。

**会创建**：所有 DT_EVENT_RAW / DT_LOT_HISTORY / DT_ALARMS 等核心表 + 索引 + 序列。

**若库已存在**：脚本会跳过已存在的对象（CREATE 加了 IF NOT EXISTS 兜底，但 Oracle 10g 没有这语法，必要时手动 DROP 后再跑）。

### Step 8. 部署 IIS 站点（仅新机器）

以管理员运行 PowerShell：

```powershell
cd deploy
.\deploy_iis_nt_final.bat
```

**做了什么**（详见 [deploy/README.md §B](../deploy/README.md)）：

1. 检查 4 个 IIS feature 是否齐全
2. 复制 `frontend\dist\` 到 `C:\inetpub\wwwroot\FabTwin\`
3. 复制 `scripts\archive\get_user.asp` + `deploy\web.config` 到 IIS 站点目录
4. 用 `appcmd` 创建应用池 `FabTwinPool`（无托管代码）+ 站点 `FabTwin`（80 端口）
5. 配置 Windows 认证 / 静态文件压缩 / SPA fallback
6. 对 `get_user.asp` **单独**关闭匿名认证、打开 Windows 认证（其他文件保持匿名）

**验证**：

```powershell
# 浏览器应能打开主页（哪怕后端没起，至少 HTML 出来了）
curl http://localhost/FabTwin/
```

### Step 9. 启动后端（IIS 模式）⭐ **每次重启后跑这个**

```powershell
cd deploy
.\start_iis.bat
```

`start_iis.bat` 是一个薄包装，会委托 `start_iis.ps1` 实际工作。

**start_iis.ps1 做了什么**（详见 [deploy/README.md §B](../deploy/README.md)）：

1. 解析 `env.bat`，把 Oracle 连接 + 端口注入环境变量
2. 动态生成 `backend\_run_iis.ps1`
3. 在新窗口里启动 `uvicorn`（`backend\main:app --host 0.0.0.0 --port 8002`）
4. 打印「已启动」「端口」「防火墙提示」

**架构**：浏览器 → IIS（静态 + /api/ /uploads/ 反代） → FastAPI 8002，WebSocket 直连 8002

**验证**：

```powershell
# 后端文档能打开（证明 FastAPI 起来了）
curl http://localhost:8002/docs

# 健康检查
curl http://localhost:8002/api/health    # 应返回 {"status":"ok"}
```

**防火墙**（首次部署需要）：

```powershell
netsh advfirewall firewall add rule name="FabTwin Backend" dir=in action=allow protocol=TCP localport=8002
```

---

## 五、Step 10（可选）：部署 AI 子系统

**默认情况不需要**，只有需要 AI 助手 / 智能查询时才装。详见 [`./integration/DEPLOY_SOP.md`](./integration/DEPLOY_SOP.md)。

| 子系统 | 用途 | 部署命令 | 端口 |
|---|---|---|---|
| **db_proxy** | n8n 调用 DB 的转抛层（必装 if AI） | `services\db_proxy\start.bat` | 8001 |
| **n8n** | 工作流引擎，AI 工具调用 | `deploy\deploy_n8n.ps1 -Action install` | 5678 |
| **Dify** | AI Agent 编排 | `deploy\deploy_dify.ps1 -Action install` | 8088 |

**集成章节概要**（详细见子 SOP）：

- **db_proxy** 部署 = 3 步：装 Python 依赖 → 改 `.env` → `start.bat`
- **n8n** 部署 = 4 步：跑 `deploy_n8n.ps1 -Action install` → 改 `.env` → 启动 → `-Action import` 自动导入 F1~F10 工作流
- **Dify** 部署 = 6 步：跑 `deploy_dify.ps1 -Action install` → 改 `.env` → 启动 → 配 AI Provider → 建应用 → 调工作流

---

## 六、Step 11：端到端验证清单

部署完毕后，按下表逐项打勾：

### 主程序

- [ ] `curl http://localhost/FabTwin/` 返回 HTML
- [ ] `curl http://localhost:8002/docs` 返回 Swagger UI
- [ ] `curl http://localhost:8002/api/health` 返回 ok
- [ ] 浏览器打开 `http://<服务器名>/FabTwin/` 能进主页和楼层
- [ ] WebSocket 通（任意页面有「实时数据」按钮能点开）

### IIS Windows 认证

- [ ] `curl -I http://localhost/FabTwin/get_user.asp` 返回 401（带 -u 域账号能 200）
- [ ] 浏览器登录后能在 `http://localhost/FabTwin/get_user.asp` 看到 `{"user":"<当前域账号>"}`

### Oracle

- [ ] `sqlplus <user>/<pass>@<host>:1521/<service>` 能连
- [ ] `SELECT COUNT(*) FROM DT_EVENT_RAW;` 能跑通

### AI（如果装）

- [ ] `curl http://localhost:5678/healthz` 返回 `{"status":"ok"}`（n8n）
- [ ] `curl http://localhost:8088/health` 返回 ok（Dify）
- [ ] `curl http://localhost:8001/health` 返回 ok（db_proxy）

---

## 七、常见操作速查

### 7.1 修改 Oracle 连接（不重启服务）

```powershell
# 编辑 deploy\env.bat，保存
# 重启后端
cd deploy
.\start_iis.bat
```

### 7.2 后端代码更新

```powershell
# 在新版 zip 解压覆盖 backend\ 后
cd deploy
.\start_iis.bat
# 进程会在旧窗口关闭后重新拉起
```

### 7.3 前端 dist 更新

```powershell
# 解压覆盖 frontend\dist\ 后，IIS 会自动重新读
# 若浏览器有缓存：Ctrl+F5 硬刷新，或改 web.config 加版本号
iisreset
```

### 7.4 schema 升级

```powershell
cd deploy
.\init_db.bat
# 看 init_db.log 确认所有 DDL 跑通
```

### 7.5 把后端注册成 Windows 服务（开机自启）

参考 [`integration/DEPLOY_SOP.md` 第 5 节 NSSM](./integration/DEPLOY_SOP.md)（用 NSSM 把 `start_iis.ps1` 注册成服务）。

### 7.6 看后端日志

```powershell
# 后端窗口关掉了就丢了。生产环境建议：
# 方案 A：NSSM 服务模式（启动时指定 stdout/stderr 文件）
# 方案 B：用 IIS ARR + 日志框架把 uvicorn 日志重定向到 D:\logs\
```

---

## 八、故障排查速查表

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 浏览器能进主页但点「实时数据」没反应 | WebSocket 没起 / 防火墙挡了 8002 | `netsh advfirewall firewall show rule name="FabTwin Backend"` |
| `get_user.asp` 返回空 user 或 401 | Windows Auth feature 没装 / `appcmd` 那条 ASP 单文件认证没配 | 重跑 `deploy_iis_nt_final.bat` |
| 后端能起但 `curl http://localhost:8002/api/health` 报「ORA-12541」 | `env.bat` 里 `ORACLE_HOST/PORT/SERVICE` 错了 | `tnsping <service>` 或 `sqlplus` 直连验证 |
| Oracle 10g/11g 报「ORA-28560」 | `ORACLE_DSN_TYPE` 没设 `sid`，或 `ORACLE_CLIENT_DIR` 不对 | `set ORACLE_DSN_TYPE=sid` + 验 `ORACLE_CLIENT_DIR` 下有 `oci.dll` |
| `init_db.bat` 报 ORA-00955（对象已存在） | 库已建过；跳过或先 DROP | 跳过；若想重跑：`DROP USER <name> CASCADE;` 后再跑 |
| Dify/n8n 起不来 | Docker Desktop 没启动 / WSL2 没装 | `wsl --status`；手动启 Docker Desktop |
| npm run build 报内存不够 | 机器内存 < 4 GB | 加 `--max-old-space-size=4096` |

---

## 九、附录

### 附录 A：环境变量完整清单（env.bat）

```bat
@echo off
REM === Oracle ===
set ORACLE_HOST=<IP>
set ORACLE_PORT=1521
set ORACLE_SERVICE=<服务名>     REM PDB 时填 service_name；CDB 时填 SID
set ORACLE_USER=<用户名>
set ORACLE_PASSWORD=<密码>      REM ⚠ 不进 git
set ORACLE_DSN_TYPE=sid         REM sid | service_name
set ORACLE_CLIENT_DIR=C:\app\client\...  REM 仅 sid 模式必填

REM === 应用端口 ===
set FABTWIN_BACKEND_PORT=8002
set FABTWIN_FRONTEND_PORT=5173

REM === AI（可选）===
set DIFY_PORT=8088
set N8N_PORT=5678
set DB_PROXY_PORT=8001
```

### 附录 B：端口清单

| 端口 | 服务 | 是否必须 |
|---|---|---|
| 80 / 443 | IIS | ✅ 必须 |
| 1521 | Oracle | ✅ 必须 |
| 8001 | db_proxy | AI 用 |
| 8002 | backend | ✅ 必须 |
| 5678 | n8n | AI 用 |
| 8088 | Dify | AI 用 |

### 附录 C：相关文档交叉索引

- 脚本功能分类：[`deploy/README.md`](../deploy/README.md)
- 系统架构总览：[`系统架构说明书.md`](./系统架构说明书.md)
- 架构图：[`FabTwin_系统架构图.svg`](./FabTwin_系统架构图.svg)
- AI 集成部署：[`docs/integration/DEPLOY_SOP.md`](./integration/DEPLOY_SOP.md)
- 业务文档（机台接入、新机台开发）：[`docs/business/`](./business/)
- 归档历史：[`docs/archive/`](./archive/)

---

## 十、变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-23 | ver2.10.21 | 项目整理：重写 SOP，整合 db_proxy + Dify + n8n；删除废弃 deploy.bat / one_click_deploy.bat；归档 WIN2022_DEPLOY_SOP / IIS_WINDOWS_AUTH_GUIDE；deploy/ 新增 README.md；新建 docs/business/、docs/archive/；package_offline.bat 重写补齐 start_iis.ps1 + db_proxy + integration |
| 2026-09-02 | ver2.10.17 | deploy-sop.md 上一次大改 |
| 2026-08-20 | ver2.10.0 | 第一次正式发布 |