# FabTwin 上线部署 SOP（标准操作流程）

> **适用场景**：将 FabTwin 系统从开发环境部署到量产服务器，并连接量产 Oracle 数据库
> **目标读者**：IT 运维人员、系统管理员
> **生成日期**：2026-07-20

---

## 目录

1. [环境前置检查](#1-环境前置检查)
2. [联网环境准备离线部署包](#2-联网环境准备离线部署包)
3. [传输到内网量产服务器](#3-传输到内网量产服务器)
4. [量产服务器环境准备](#4-量产服务器环境准备)
5. [Oracle 数据库配置](#5-oracle-数据库配置)
6. [应用部署](#6-应用部署)
7. [启动与验证](#7-启动与验证)
8. [Windows 服务注册（推荐）](#8-windows-服务注册推荐)
9. [Nginx 反向代理（可选）](#9-nginx-反向代理可选)
10. [常见问题排查](#10-常见问题排查)

---

## 1. 环境前置检查

### 1.1 量产服务器最低配置

| 项目 | 要求 | 验证命令 |
|------|------|----------|
| 操作系统 | Windows Server 2016+ 或 Windows 10/11 | `winver` |
| Python | 3.10+ | `python --version` |
| Node.js | 16+（仅构建时需要，运行时可选） | `node --version` |
| Oracle Client | **可选**（仅初始化 SQL 时需要 sqlplus） | `sqlplus -V` |
| 内存 | 4GB+ | `systeminfo` |
| 磁盘空间 | 5GB+（含 node_modules） | `dir` |
| 端口 | 8002（后端）、5173（前端）可用 | `netstat -ano \| findstr ":8002 "` |

> **说明**：Oracle 数据库由 DB 组搭建，量产服务器无需安装 Oracle Server。如需在量产服务器执行 `init_db.bat` 初始化表结构，则需要 sqlplus 客户端（可由 DB 组远程执行，见 5.2）。应用运行时通过 `oracledb` Python 包连接，无需 Oracle Client。

### 1.2 量产 Oracle 数据库（由 DB 组提供）

> **重要**：Oracle 数据库由 DB 组负责搭建、运维。应用部署方**无需**安装 Oracle Server 或 Client，只需向 DB 组索取连接信息并填入配置即可。

**应用部署方需要向 DB 组索取以下信息：**

| 项目 | 示例值 | 用途 |
|------|--------|------|
| 主机 IP | 192.168.x.x 或 localhost | `ORACLE_HOST` |
| 端口 | 1521 | `ORACLE_PORT` |
| 服务名 | ORCLPDB | `ORACLE_SERVICE` |
| 业务用户名 | fabtwin | `ORACLE_USER`（DB 组创建） |
| 业务用户密码 | ******** | `ORACLE_PASSWORD`（DB 组创建） |

**DB 组需确保该业务用户具有以下权限：**
- `CREATE SESSION` - 连接数据库
- `CREATE TABLE` / `CREATE SEQUENCE` / `CREATE TRIGGER` - 建表和自增主键支持
- `UNLIMITED TABLESPACE`（或对应表空间配额） - 数据存储

**应用部署方需确保：**
- 量产服务器能访问 DB 组的 Oracle 端口（默认 1521）
- 防火墙规则已开通（如跨网段）

### 1.3 网络策略

- **能联网服务器**（用于打包）：可访问公网下载 Python/Node.js 依赖
- **量产服务器**（内网）：需访问 DB 组的 Oracle 端口 1521 + 应用端口 8002/5173

---

## 2. 联网环境准备离线部署包

### 2.1 在开发机/联网服务器上执行

```cmd
cd C:\path\to\fab-twin-pro
package_offline.bat
```

**该脚本会完成：**
1. 复制后端代码到 `fabtwin-offline-deploy\backend\`
2. 复制前端代码 + 构建产物（dist/）到 `fabtwin-offline-deploy\frontend\`
3. 复制 SQL 脚本到 `fabtwin-offline-deploy\sql\`
4. 下载 Python 依赖离线包（wheels）到 `backend\wheels\`
5. 复制 node_modules（如已存在）到 `frontend\node_modules\`
6. 打包为 `fabtwin-deploy-YYYYMMDD.zip`

### 2.2 验证离线包内容

```
fabtwin-deploy-YYYYMMDD.zip
├── backend/
│   ├── *.py                    # 后端代码
│   ├── requirements.txt        # 依赖清单
│   ├── routers/                # 路由模块
│   ├── services/               # 服务模块
│   └── wheels/                 # 离线pip包
├── frontend/
│   ├── src/                    # 前端源码
│   ├── public/                 # 静态资源
│   ├── dist/                   # 构建产物（生产用）
│   ├── node_modules/           # 依赖（避免内网npm install）
│   ├── package.json
│   └── vite.config.js
├── sql/
│   ├── init_oracle_db.sql      # 数据库初始化SQL（不含DT表）
│   └── cleanup_db.sql          # 数据清理脚本
├── deploy.bat                  # 一键部署
├── start_prod.bat              # 生产启动
├── start-dev.bat               # 开发启动
├── init_db.bat                 # DB初始化
├── create_user.bat             # Oracle建用户
├── README.md
└── deploy-sop.md               # 本文档
```

### 2.3 文件大小预估

- ZIP 压缩包：约 200-400 MB
- 解压后：约 500MB-1GB

---

## 3. 传输到内网量产服务器

### 3.1 传输方式（任选其一）

1. **U盘/移动硬盘**：最简单，直接拷贝 ZIP 文件
2. **内网文件共享**：通过 SMB 共享文件夹
3. **SCP/SFTP**：如量产服务器开启 SSH

### 3.2 接收端操作

```cmd
REM 假设传输到 D:\deploy\
mkdir D:\deploy
REM 将 fabtwin-deploy-YYYYMMDD.zip 复制到 D:\deploy\
cd /d D:\deploy
powershell -Command "Expand-Archive -Path fabtwin-deploy-*.zip -DestinationPath . -Force"
cd fab-twin-pro  REM 或解压后的目录名
```

---

## 4. 量产服务器环境准备

### 4.1 安装 Python 3.10+

如未安装，从 https://www.python.org/downloads/ 下载（可联网时）或离线安装包。

**验证：**
```cmd
python --version
REM 输出: Python 3.10.x 或更高
```

### 4.2 获取 Oracle 连接信息（向 DB 组索取）

> **重要**：Oracle 数据库由 DB 组搭建。应用部署方只需向 DB 组索取以下连接信息，**无需安装 Oracle Server 或 Client**。

| 配置项 | 示例 | 备注 |
|--------|------|------|
| `ORACLE_HOST` | 192.168.x.x | DB 组提供 |
| `ORACLE_PORT` | 1521 | 默认 1521 |
| `ORACLE_SERVICE` | ORCLPDB | DB 组提供 |
| `ORACLE_USER` | fabtwin | DB 组已创建的业务用户 |
| `ORACLE_PASSWORD` | ******** | DB 组已创建的业务用户密码 |

**应用运行时无需 Oracle Client**：后端通过 Python `oracledb` 包（Thin 模式）连接数据库，纯 Python 实现，不依赖 Oracle Client 库。

**验证连接（可选）**：
```cmd
REM 方式1：使用 Python 验证（推荐，无需 Oracle Client）
cd /d D:\deploy\fab-twin-pro\backend
venv\Scripts\python.exe -c "import oracledb; conn=oracledb.connect(user='fabtwin', password='********', dsn='192.168.x.x:1521/ORCLPDB'); print('连接成功'); conn.close()"

REM 方式2：使用 sqlplus（需 Instant Client，可选）
sqlplus fabtwin/********@192.168.x.x:1521/ORCLPDB
```

### 4.3 安装 Node.js（可选）

仅当需要在量产服务器重新构建前端时需要。如使用预构建的 `dist/`，则不需要。

---

## 5. Oracle 数据库配置

### 5.1 业务用户与表空间（由 DB 组完成）

> **重要**：业务用户、表空间、权限授予由 DB 组在 Oracle 服务器上完成。应用部署方只需将以下 SQL 发给 DB 组执行即可。

**将以下 SQL 提供给 DB 组执行**（需 sysdba 权限）：

```sql
-- 1. 创建表空间（如 DB 组未单独指定路径，请按实际 Oracle 数据文件目录调整）
CREATE TABLESPACE fabtwin_data
  DATAFILE 'fabtwin_data01.dbf'
  SIZE 500M AUTOEXTEND ON NEXT 100M MAXSIZE 2G;

CREATE TEMPORARY TABLESPACE fabtwin_temp
  TEMPFILE 'fabtwin_temp01.dbf'
  SIZE 100M AUTOEXTEND ON NEXT 50M MAXSIZE 500M;

-- 2. 创建业务用户
CREATE USER fabtwin IDENTIFIED BY <强密码>
  DEFAULT TABLESPACE fabtwin_data
  TEMPORARY TABLESPACE fabtwin_temp;

-- 3. 授权（应用所需权限）
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE TRIGGER TO fabtwin;
GRANT UNLIMITED TABLESPACE TO fabtwin;
-- 或：GRANT RESOURCE, DBA TO fabtwin;（DBA 权限较宽松，按公司安全策略选择）
```

**应用部署方需向 DB 组确认：**
- 业务用户 `fabtwin`（或 DB 组指定的用户名）已创建
- 密码已设置并告知应用部署方
- 表空间配额充足（至少 2GB）
- 网络防火墙已开通 1521 端口访问

**附：仓库中提供 `create_user.bat` + `create_user.sql`**，如 DB 组希望由应用方执行（需 sysdba 权限），可使用此脚本。但通常 DB 组会在 DB 服务器上自行执行。

### 5.2 执行数据库初始化（建表 + 基础数据）

> **说明**：此步骤在 DB 组创建的业务用户下创建 20 张平台表并导入基础数据。可由应用部署方或 DB 组执行，二选一。

**方式 1：由应用部署方执行**（需量产服务器能访问 Oracle，且本机有 sqlplus）

修改 `init_db.bat` 中的连接串为 DB 组提供的远程地址，或先设置环境变量：

```cmd
REM 设置 Oracle 连接信息（DB 组提供）
set ORACLE_HOST=192.168.x.x
set ORACLE_PORT=1521
set ORACLE_SERVICE=ORCLPDB
set ORACLE_USER=fabtwin
set ORACLE_PASSWORD=********

REM 如本机有 sqlplus，执行初始化
init_db.bat
```

如本机无 sqlplus，可使用 Python 远程执行（无需 Oracle Client）：

```cmd
cd /d D:\deploy\fab-twin-pro\backend
venv\Scripts\python.exe -c "import oracledb; conn=oracledb.connect(user='fabtwin', password='********', dsn='192.168.x.x:1521/ORCLPDB'); cur=conn.cursor(); sql=open('../sql/init_oracle_db.sql').read(); [cur.execute(stmt) for stmt in sql.split(';') if stmt.strip() and not stmt.strip().startswith('--')]; conn.commit(); print('初始化完成')"
```

**方式 2：由 DB 组在 DB 服务器上执行**（推荐）

将 `sql/init_oracle_db.sql` 文件提供给 DB 组，由其在 Oracle 服务器上用业务用户执行：

```cmd
sqlplus fabtwin/********@ORCLPDB @init_oracle_db.sql
```

**该脚本会完成：**
- 删除旧表（如存在）
- 创建 20 张平台表（不含 DT 表）
- 导入基础数据（机台定义、角色、权限、用户等）
- 创建 11 个 SEQUENCE + TRIGGER（模拟 IDENTITY 自增主键）

**重要说明：**
- DT 开头的 5 个表（DT_EVENT_RAW, DT_EVENT_RAW_CUR, DT_EVENT_STD, DT_ALARM_EVENT, DT_STATE_SNAPSHOT）**不在 init_oracle_db.sql 中**，由量产环境自行管理
- 应用首次启动时，ORM `create_all` 会自动创建这 5 个 DT 表（如不存在）
- 11 个 SEQUENCE+TRIGGER 用于替代 Oracle IDENTITY 列（因 ALTER TABLE MODIFY 不支持改为 IDENTITY，参见 ORA-30673），覆盖以下表：
  - CHAMBER_SNAPSHOTS, OHT_POSITIONS, AI_INSIGHTS, MACHINE_EVENTS, ALARMS
  - DASHBOARD_KPI, FLOOR_AREAS, TRACKS, ROLE_PERMISSIONS
  - MACHINE_TOOL_MAPPINGS, EVENT_ACTION_MAPPINGS

### 5.3 验证数据库（远程连接）

```sql
REM 使用 DB 组提供的连接信息
sqlplus fabtwin/********@192.168.x.x:1521/ORCLPDB

-- 检查平台表数量（不含 DT 表）
SELECT COUNT(*) FROM user_tables WHERE table_name NOT LIKE 'DT_%';
-- 预期: 20

-- 检查 SEQUENCE 数量
SELECT COUNT(*) FROM user_sequences;
-- 预期: 11

-- 检查 TRIGGER 数量
SELECT COUNT(*) FROM user_triggers WHERE trigger_name LIKE 'TRG_%_ID';
-- 预期: 11

-- 检查关键表数据
SELECT COUNT(*) FROM machines;          -- 机台定义（预期: 38）
SELECT COUNT(*) FROM users;             -- 用户
SELECT COUNT(*) FROM roles;             -- 角色（预期: 3 - admin/engineer/user）
SELECT COUNT(*) FROM perm_data;         -- 权限（预期: 10）
SELECT COUNT(*) FROM role_permissions;  -- 角色权限映射

EXIT;
```

---

## 6. 应用部署

### 6.1 一键部署（推荐）

```cmd
cd /d D:\deploy\fab-twin-pro
deploy.bat
```

**该脚本会自动完成 5 个步骤：**
1. **检查环境** - 验证 Python 3.10+ / Node.js 16+ 已安装
2. **部署后端** - 创建 venv，优先使用 `wheels/` 离线安装（内网），否则在线 `pip install`
3. **初始化数据库** - 优先执行 `sql/init_oracle_db.sql`（含基础数据），sqlplus 不可用时回退到 ORM `create_all`
4. **部署前端** - 如已存在 `dist/` 跳过构建，否则用 `vite.cmd build` 构建（绕过 PowerShell 执行策略）
5. **启动服务** - 后端 `python main.py`（设置生产环境变量）+ 前端 `vite preview --port 5173 --host`（生产预览模式）

**与开发模式区别：**
- 前端使用 `vite preview`（生产构建预览），非 `vite`（开发热更新）
- 自动设置 `DB_TYPE=oracle`、`SIMULATION_ENABLED=False`、`DB_POLLER_ENABLED=True`
- 关闭命令行窗口即停止服务

### 6.2 手动分步部署

**步骤 1：后端依赖**

```cmd
cd /d D:\deploy\fab-twin-pro\backend

REM 创建虚拟环境
python -m venv venv

REM 离线安装（使用 wheels，内网推荐）
venv\Scripts\pip.exe install --no-index --find-links wheels -r requirements.txt

REM 或在线安装（如有网络）
REM venv\Scripts\pip.exe install -r requirements.txt
```

**步骤 2：数据库初始化**（如未在 deploy.bat 中执行）

```cmd
cd /d D:\deploy\fab-twin-pro
init_db.bat
```

**步骤 3：前端构建**（如已有 dist/ 可跳过）

```cmd
cd /d D:\deploy\fab-twin-pro\frontend

REM 如有 node_modules，跳过 install
if not exist "node_modules" cmd /c "npm install"

REM 构建（使用 vite.cmd 绕过 PowerShell 执行策略）
node_modules\.bin\vite.cmd build
```

**步骤 4：配置环境变量**（可选，deploy.bat 已默认设置）

```cmd
REM Oracle 连接（如非默认）
setx DB_TYPE "oracle"
setx ORACLE_HOST "localhost"
setx ORACLE_PORT "1521"
setx ORACLE_SERVICE "ORCLPDB"
setx ORACLE_USER "fabtwin"
setx ORACLE_PASSWORD "fabtwin"

REM 生产环境关闭模拟器
setx SIMULATION_ENABLED "False"
setx DB_POLLER_ENABLED "True"

REM 如需 AI 功能
setx AI_PROVIDER "local"
REM setx AI_BASE_URL "https://open.bigmodel.cn/api/paas/v4"
REM setx AI_API_KEY "your-api-key"
REM setx AI_MODEL "glm-5.2"
```

---

## 7. 启动与验证

### 7.1 启动服务

**生产环境启动：**
```cmd
cd /d D:\deploy\fab-twin-pro
start_prod.bat
```

**开发模式启动（带热更新）：**
```cmd
start-dev.bat
```

### 7.2 验证服务

**检查后端：**
```cmd
curl http://localhost:8002/health
REM 预期: {"status":"ok","service":"fabtwin"}
```

**检查前端：**
- 浏览器访问 `http://localhost:5173`
- 应看到登录页面

**登录验证：**
- 默认 NT 登录会自动识别 Windows 用户（首次登录自动创建 `user` 角色账号）
- 点击"管理员登录"使用 `admin` / `admin123`

**功能验证清单：**
- [ ] 主页看板能显示机台列表
- [ ] 点击机台进入详情页
- [ ] 3D 视图正常加载
- [ ] 平面图正常显示
- [ ] 历史回放能选择日期
- [ ] admin 登录后顶部显示"模型编辑器"和"用户管理"菜单
- [ ] user 登录后顶部**不显示**"模型编辑器"和"用户管理"菜单
- [ ] user 角色尝试编辑平面图返回 403

### 7.3 数据库连接验证

访问 `http://localhost:8002/docs`，测试以下接口：
- `GET /api/machines` - 应返回 38 台机台
- `GET /api/floors` - 应返回楼层信息
- `GET /api/auth/permissions` - 应返回 10 个权限
- `GET /api/users` - 应返回用户列表（需 admin 登录）

### 7.4 权限控制验证（RBAC）

系统采用 RBAC 三级角色权限模型，前端 v-if 隐藏 UI + 后端 Depends 强制校验双层防护。

**角色权限矩阵：**

| 角色 | 权限数 | 权限范围 | 可见菜单 |
|------|--------|----------|----------|
| admin | 10 | 全部权限（短路返回 `["*"]`） | 所有菜单 + 模型编辑器 + 用户管理 |
| engineer | 9 | 除 user_manage 外全部权限 | 所有菜单 + 模型编辑器（无用户管理） |
| user | 5 | 仅查看权限（machine_view/floor_view/model_view/history_view/alarm_view） | 所有菜单（无模型编辑器、无用户管理） |

**10 个权限 ID：**
- `machine_view` / `machine_edit` - 机台查看/编辑
- `floor_view` / `floor_edit` - 平面图查看/编辑
- `model_view` / `model_edit` - 模型查看/编辑
- `history_view` - 历史查看
- `ai_analysis` - AI 分析
- `alarm_view` - 告警查看
- `user_manage` - 用户管理（仅 admin）

**NT 用户自动登录行为：**
- 首次 NT 登录 → 自动在 `users` 表创建账号（`username = hostname\windows_user`，`role = "user"`）
- 后续登录 → 更新 `last_login_at`，权限按 `user` 角色
- NT 用户**不能**编辑模型、平面图，**不能**访问用户管理界面

**验证方法：**
```cmd
REM 1. 用 admin 登录，添加平面图区域 → 应成功
REM 2. 退出，用 NT 用户登录，尝试编辑平面图 → 前端按钮不显示
REM 3. 直接调用 API 测试后端校验:
curl -X POST http://localhost:8002/api/floors/1/areas -H "Authorization: Bearer <user_token>"
REM 预期: 403 {"detail":"无权限：需要 floor_edit 权限"}
```

---

## 8. Windows 服务注册（推荐）

将前后端注册为 Windows 服务，实现开机自启和后台运行。

### 8.1 安装 NSSM

```cmd
REM 下载 nssm.exe 到 C:\Windows\System32\
REM https://nssm.cc/release/nssm-2.24.zip
```

### 8.2 注册后端服务

```cmd
nssm install FabTwinBackend "D:\deploy\fab-twin-pro\backend\venv\Scripts\python.exe" "D:\deploy\fab-twin-pro\backend\main.py"
nssm set FabTwinBackend AppDirectory "D:\deploy\fab-twin-pro\backend"
nssm set FabTwinBackend AppEnvironmentExtra "DB_TYPE=oracle" "SIMULATION_ENABLED=False" "DB_POLLER_ENABLED=True"
nssm set FabTwinBackend Start SERVICE_AUTO_START
nssm start FabTwinBackend
```

### 8.3 注册前端服务

```cmd
nssm install FabTwinFrontend "D:\deploy\fab-twin-pro\frontend\node_modules\.bin\vite.cmd" "preview --port 5173 --host"
nssm set FabTwinFrontend AppDirectory "D:\deploy\fab-twin-pro\frontend"
nssm set FabTwinFrontend Start SERVICE_AUTO_START
nssm start FabTwinFrontend
```

### 8.4 服务管理

```cmd
REM 查看状态
sc query FabTwinBackend
sc query FabTwinFrontend

REM 停止/启动/重启
nssm stop FabTwinBackend
nssm start FabTwinBackend
nssm restart FabTwinBackend

REM 卸载服务
nssm remove FabTwinBackend confirm
```

---

## 9. Nginx 反向代理（可选）

生产环境推荐使用 Nginx 统一端口访问。

### 9.1 安装 Nginx

下载 Nginx for Windows：http://nginx.org/en/download.html

解压到 `C:\nginx\`

### 9.2 配置 nginx.conf

编辑 `C:\nginx\conf\nginx.conf`：

```nginx
worker_processes  1;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout  65;

    # 前端静态资源
    server {
        listen       80;
        server_name  localhost;

        # 前端
        location / {
            root   "D:/deploy/fab-twin-pro/frontend/dist";
            try_files $uri $uri/ /index.html;
        }

        # API 反代到后端
        location /api/ {
            proxy_pass http://127.0.0.1:8002;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 300s;
        }

        # WebSocket 反代
        location /ws/ {
            proxy_pass http://127.0.0.1:8002;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }
    }
}
```

### 9.3 启动 Nginx

```cmd
cd /d C:\nginx
start nginx.exe
REM 重载配置: nginx -s reload
REM 停止: nginx -s stop
```

访问 `http://localhost` 即可使用。

---

## 10. 常见问题排查

### 10.1 后端启动失败

**问题：`ModuleNotFoundError: No module named 'oracledb'`**

```cmd
cd /d D:\deploy\fab-twin-pro\backend
venv\Scripts\pip.exe install oracledb
```

**问题：`ORA-12541: TNS:no listener`**

> Oracle 数据库由 DB 组管理，请按以下顺序排查：

```cmd
REM 1. 检查网络连通性（应用服务器 → DB 服务器）
ping 192.168.x.x
REM 2. 检查 1521 端口是否可达
powershell -Command "Test-NetConnection -ComputerName 192.168.x.x -Port 1521"
REM 3. 如以上都通，联系 DB 组检查 Oracle 监听器状态
REM    DB 组在 DB 服务器执行: lsnrctl status / lsnrctl start
```

**问题：`ORA-01017: invalid username/password`**

```cmd
REM 1. 确认连接信息（DB 组提供）
sqlplus fabtwin/********@192.168.x.x:1521/ORCLPDB
REM 2. 如失败，联系 DB 组确认用户名密码或重置密码
REM    DB 组执行: ALTER USER fabtwin IDENTIFIED BY <新密码>;
```

**问题：`ORA-12514: TNS:listener does not currently know of service requested`**

```cmd
REM 服务名错误，联系 DB 组确认正确的服务名
REM 常见: ORCLPDB / ORCL / XEPDB1
REM 验证可用服务名（需 DB 组配合）:
REM   lsnrctl status  → 查看 "Services Summary" 部分
```

**问题：`ORA-01109: database not open` 或 `ORA-01033`**

数据库未启动或未打开，**联系 DB 组处理**（应用部署方无 sysdba 权限）。

DB 组在 DB 服务器执行：
```cmd
sqlplus /nolog
CONN / AS SYSDBA
SHUTDOWN IMMEDIATE
STARTUP
ALTER DATABASE OPEN;
ALTER PLUGGABLE DATABASE ALL OPEN;
EXIT;
```

### 10.2 前端启动失败

**问题：`vite: command not found`**

```cmd
cd /d D:\deploy\fab-twin-pro\frontend
npm install
```

**问题：API 请求 404**

检查 `vite.config.js` 中的代理配置：
```js
proxy: {
  '/api': 'http://localhost:8002',
  '/ws': { target: 'ws://localhost:8002', ws: true }
}
```

### 10.3 数据库相关问题

**问题：DT 表数据丢失**

DT 表是量产在用，**初始化 SQL 不会创建或导入 DT 表数据**。如需重建：
- 应用首次启动时 ORM 会自动创建空表
- 历史数据需从生产备份恢复

**问题：中文乱码**

```cmd
REM 设置 NLS_LANG
setx NLS_LANG "SIMPLIFIED CHINESE_CHINA.AL32UTF8"
REM 重启应用
```

### 10.4 权限相关

**问题：普通用户看不到"模型编辑器"菜单**

这是设计如此。只有 `admin` 和 `engineer` 角色才有 `model_edit` 权限。
- admin 登录 → 可看到"模型编辑器"和"用户管理"
- engineer 登录 → 只能看"模型编辑器"
- user 登录 → 两个都看不到

**问题：用户管理菜单不显示**

确认当前用户角色为 `admin`，且 `ROLE_PERMISSIONS` 表中 admin 角色有 `user_manage` 权限（admin 默认短路返回 `["*"]`）。

### 10.5 日志查看

**后端日志：** 直接看启动后端的命令行窗口输出

**Oracle 日志：** 由 DB 组管理（位于 DB 服务器 `$ORACLE_BASE/diag/rdbms/<db_unique_name>/<sid>/trace/alert_<sid>.log`），应用部署方如需排查 Oracle 错误，请联系 DB 组提供日志

**Nginx 日志：** `C:\nginx\logs\error.log` 和 `access.log`

---

## 附录 A：环境变量完整清单

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| DB_TYPE | oracle | 是 | 数据库类型 |
| ORACLE_HOST | localhost | 是 | Oracle 主机（**DB 组提供**） |
| ORACLE_PORT | 1521 | 是 | Oracle 端口（**DB 组提供**） |
| ORACLE_SERVICE | ORCLPDB | 是 | Oracle PDB 服务名（**DB 组提供**） |
| ORACLE_USER | fabtwin | 是 | Oracle 用户名（**DB 组创建**） |
| ORACLE_PASSWORD | fabtwin | 是 | Oracle 密码（**DB 组创建**） |
| SIMULATION_ENABLED | False | 否 | 模拟器（生产环境关闭） |
| DB_POLLER_ENABLED | True | 否 | DB 事件轮询 |
| AI_PROVIDER | local | 否 | AI 提供方 |
| AI_API_KEY | - | 否 | AI API Key |
| AI_MODEL | glm-5.2 | 否 | AI 模型 |

## 附录 B：端口清单

| 端口 | 服务 | 归属 | 说明 |
|------|------|------|------|
| 5173 | Vite (前端) | 应用部署方 | 开发模式/preview |
| 8002 | FastAPI (后端) | 应用部署方 | API + WebSocket |
| 1521 | Oracle DB | **DB 组** | 数据库（DB 组管理） |
| 80 | Nginx (可选) | 应用部署方 | 统一入口 |
| 6379 | Redis (可选) | 应用部署方 | 缓存 |

## 附录 C：联系人

- 应用技术支持：（请填写）
- DB 组（Oracle 运维）：（请填写）
- 网络管理员：（请填写）

---

**文档版本**：v1.2
**最后更新**：2026-07-20
**变更说明**：
- v1.2 (2026-07-20): 明确 Oracle 数据库由 DB 组搭建运维，应用部署方仅需索取连接信息；移除"安装 Oracle Client"要求；业务用户/表空间创建改为由 DB 组执行；init_db.bat 支持远程执行或由 DB 组在 DB 服务器执行；故障排查章节调整为联系 DB 组
- v1.1 (2026-07-20): 修复 init_db.bat 自动检测 ORACLE_HOME；deploy.bat 改用 vite preview 生产模式 + SQL 脚本初始化；补充 SEQUENCE+TRIGGER、RBAC 权限控制、NT 用户自动登录说明
- v1.0 (2026-07-20): 初版 SOP
**审核人**：（待填写）
