# FabTwin 上线部署 SOP（标准操作流程）

> **适用场景**：将 FabTwin 系统从开发环境部署到量产服务器（离线/内网），并连接量产 Oracle 数据库
> **目标读者**：IT 运维人员、系统管理员
> **生成日期**：2026-07-20
> **最后更新**：2026-09-02（v3.0，覆盖 ver2.9.0 A/B/C/D/E/F/G 七批变更）

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
11. [ver2.9.0 变更摘要（本次部署必读）](#11-ver290-变更摘要本次部署必读)
12. [Prod 环境变量配置注意事项（必读）](#12-prod-环境变量配置注意事项必读)

---

## 11. ver2.9.0 变更摘要（本次部署必读）

> 本节汇总 ver2.9.0（2026-09-01~09-02）A/B/C/D/E/F/G 七批全部变更，部署前**务必**确认 SQL 脚本和 env 配置已同步更新。

### 11.1 数据库结构变更

| 变更 | 影响表 | 处理方式 | SQL 脚本 |
|------|--------|----------|----------|
| 新增 `DISPLAY_ORDER` 列（图层置顶/置底功能） | `MACHINES`、`FLOOR_AREAS` | **已内置**于 `init_oracle_db.sql`（新建库自动含此列）；旧库由后端启动时 `_ensure_missing_columns()` 自动 ALTER 补齐 | `sql/init_oracle_db.sql`、`sql/v2.7_add_display_order.sql`（手动兜底） |
| AI 相关 3 张表（D 批前已存在） | `AI_CONFIGS`、`AI_PROVIDER_CONFIGS`、`AI_USAGE_LOGS` | **必须单独执行** `sql/create_ai_tables.sql` 建表 | `sql/create_ai_tables.sql` |

**关键提醒**：
- `init_oracle_db.sql` 已在 ver2.9.0 更新，新建库的 `MACHINES`/`FLOOR_AREAS` 表会自动包含 `DISPLAY_ORDER` 列（DEFAULT 0）
- **旧库升级**（已有数据）：后端启动时 `database.py` 的 `_ensure_missing_columns()` 会自动检测并 ALTER 补齐，无需手动执行升级脚本；如需留审计痕迹，可手动执行 `sql/v2.7_add_display_order.sql`
- **AI 表**不在 `init_oracle_db.sql` 中，**必须**单独执行 `sql/create_ai_tables.sql`（新建库和旧库升级都要执行）

### 11.2 功能变更（A~G 批）

| 批次 | 变更内容 | 部署影响 |
|------|----------|----------|
| A | 平面图区域 resize/多选框选 + 机台管理页 + 机台搜索 | 前端构建产物需更新 |
| B | 机台实时状态推导 + KPI 真实统计（读 DT 量产表） | 后端 `machines.py` 更新；依赖 DT 表（量产在用，无需初始化） |
| C | Dify 提示词修复 + AI URL 拼接透明化 | 后端 `ai_middleware.py` 更新 |
| D | 平面图手动输入尺寸 + 批量复制 + 置顶/置底图层管理 | 后端 `floors.py` 新增 4 个端点；前端 `FloorPlan.vue` 更新；需 `DISPLAY_ORDER` 列 |
| E | 自动补 `DISPLAY_ORDER` 列修复 ORA-00904 | 后端 `database.py` 新增 `_ensure_missing_columns()`；启动时自动 ALTER |
| F | AI 配置接口 500 + AI 用量 ORA-00979 + 平面图错误可读化 | 后端 `schemas.py`/`ai_middleware.py`/`floors.py` 更新 |
| G | 平面图批量复制/置顶置底"假失败"修复 | 前端 `FloorPlan.vue` 修复 `loadFloor()`→`loadFloorData()` 函数名 |

### 11.3 部署前检查清单

- [ ] `sql/init_oracle_db.sql` 已更新到 ver2.9.0（含 `DISPLAY_ORDER` 列）
- [ ] `sql/init_oracle_aqua.sql` 已同步更新
- [ ] `sql/create_ai_tables.sql` 已包含在离线包中
- [ ] `sql/v2.7_add_display_order.sql` 已包含（旧库手动升级兜底）
- [ ] 后端代码已包含 `database.py` 的 `_ensure_missing_columns()` 自动补列逻辑
- [ ] 前端 `dist/` 已重新构建（包含 G 批 `loadFloorData` 修复）
- [ ] `env.bat` 已按 prod 实际 Oracle 连接信息配置（见第 12 节）

---

## 12. Prod 环境变量配置注意事项（必读）

> Prod 服务器离线部署，所有环境变量必须在 `env.bat` 或 NSSM `AppEnvironmentExtra` 中显式设置，不依赖默认值。

### 12.1 必须配置的环境变量（6 项）

| 变量名 | 说明 | prod 示例值 | 配置位置 |
|--------|------|------------|----------|
| `DB_TYPE` | 数据库类型（仅支持 oracle） | `oracle` | `env.bat` + NSSM |
| `ORACLE_HOST` | Oracle 主机 IP（DB 组提供） | `10.30.8.119` | `env.bat` + NSSM |
| `ORACLE_PORT` | Oracle 端口 | `1521` | `env.bat` + NSSM |
| `ORACLE_SERVICE` | Oracle PDB 服务名/SID（DB 组提供） | `APCDB` | `env.bat` + NSSM |
| `ORACLE_USER` | Oracle 业务用户名（DB 组创建） | `emuuser` | `env.bat` + NSSM |
| `ORACLE_PASSWORD` | Oracle 业务用户密码 | `********` | `env.bat` + NSSM |

### 12.2 关键兼容性环境变量（2 项，按 Oracle 版本决定）

| 变量名 | 何时需要 | prod 示例值 | 不设的后果 |
|--------|----------|------------|-----------|
| `ORACLE_DSN_TYPE` | **10g/11g 必须设为 `sid`**；12c+ 设为 `service_name`（默认） | `sid`（10g/11g） | 10g/11g 不设会连接失败或 ORA-03134 |
| `ORACLE_CLIENT_DIR` | **10g/11g 必须设**（指向 64-bit Oracle Client 19c+ 安装目录）；12c+ 不需要 | `C:\app\client\c11463\product\19.0.0\client_1` | 10g/11g 不设会 ORA-03134/ORA-28040 |

**判断 Oracle 版本的方法**（向 DB 组确认）：
- Oracle 10g / 11g → `ORACLE_DSN_TYPE=sid` + `ORACLE_CLIENT_DIR=<path>`（Thick 模式）
- Oracle 12c / 18c / 19c / 21c+ → 默认 `service_name`，无需 `ORACLE_CLIENT_DIR`（Thin 模式，纯 Python）

### 12.3 可选环境变量（AI / 模拟 / 语音）

| 变量名 | 默认值 | 说明 | prod 建议 |
|--------|--------|------|----------|
| `SIMULATION_ENABLED` | `False` | 模拟器开关 | prod 设 `False` |
| `DB_POLLER_ENABLED` | `True` | DB 事件轮询开关 | prod 设 `True`（读取 DT 表实时数据） |
| `AI_PROVIDER` | `local` | AI 提供方（local/openai/dify） | prod 默认 `local`；如需 LLM 在前端「AI配置管理」面板添加（持久化到 DB），**无需** env 配置 |
| `AI_BASE_URL` | （空） | OpenAI 兼容 API 地址 | 仅当 env 级配置 LLM 时设；推荐用前端面板配置 |
| `AI_API_KEY` | （空） | API Key | 同上 |
| `AI_MODEL` | `glm-5.2` | 模型名称 | 同上 |
| `DIFY_ENABLED` | `False` | Dify 开关 | prod 默认 `False`；如需在 AI 配置面板开启 |
| `N8N_ENABLED` | `False` | N8N 开关 | prod 默认 `False` |
| `WHISPER_MODEL_SIZE` | `tiny` | 语音识别模型大小 | prod 离线环境保持 `tiny`（避免下载大模型） |
| `WHISPER_DEVICE` | `cpu` | 语音识别设备 | prod 设 `cpu`（无 GPU） |

**AI 配置策略**（prod 离线环境）：
- 默认使用「本地规则引擎」（`AI_PROVIDER=local`），无需联网，开箱可用
- 如需接入 LLM（智谱 GLM/OpenAI 等），**不要**在 env 中硬编码 API Key
- 在前端「AI 配置管理」面板（用户管理旁边）添加 Provider 配置，会持久化到 `AI_PROVIDER_CONFIGS` 表
- 前端面板支持配置管理、删除、禁用、设为默认、Token 用量统计
- AI 使用日志记录在 `AI_USAGE_LOGS` 表（可在前端查看执行日志）

### 12.4 完整 `env.bat` 模板（prod 离线环境）

```bat
@echo off
REM FabTwin Prod Environment Configuration
REM IMPORTANT: Do NOT use Chinese characters in this file

REM ===== 数据库（必填，DB 组提供）=====
set DB_TYPE=oracle
set ORACLE_HOST=10.30.8.119
set ORACLE_PORT=1521
set ORACLE_SERVICE=APCDB
set ORACLE_USER=emuuser
set ORACLE_PASSWORD=apcuser

REM ===== Oracle 版本兼容（10g/11g 必填，12c+ 删除以下两行）=====
set ORACLE_DSN_TYPE=sid
set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1

REM ===== 运行模式（prod 固定）=====
set SIMULATION_ENABLED=False
set DB_POLLER_ENABLED=True

REM ===== AI（默认本地规则引擎，无需联网）=====
set AI_PROVIDER=local

REM ===== 语音识别（prod 离线保持 tiny + cpu）=====
set WHISPER_MODEL_SIZE=tiny
set WHISPER_DEVICE=cpu
```

### 12.5 NSSM 服务注册时的环境变量传递

NSSM 注册 Windows 服务时，`AppEnvironmentExtra` 会追加到系统环境变量之后。**必须**把 6 项必填 + 2 项兼容性变量全部传入：

```cmd
nssm install FabTwinBackend "D:\deploy\fab-twin-pro\backend\venv\Scripts\python.exe" "D:\deploy\fab-twin-pro\backend\main.py"
nssm set FabTwinBackend AppDirectory "D:\deploy\fab-twin-pro\backend"
nssm set FabTwinBackend AppEnvironmentExtra ^
  "DB_TYPE=oracle" ^
  "ORACLE_HOST=10.30.8.119" ^
  "ORACLE_PORT=1521" ^
  "ORACLE_SERVICE=APCDB" ^
  "ORACLE_USER=emuuser" ^
  "ORACLE_PASSWORD=apcuser" ^
  "ORACLE_DSN_TYPE=sid" ^
  "ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1" ^
  "SIMULATION_ENABLED=False" ^
  "DB_POLLER_ENABLED=True" ^
  "AI_PROVIDER=local" ^
  "WHISPER_MODEL_SIZE=tiny" ^
  "WHISPER_DEVICE=cpu"
nssm set FabTwinBackend Start SERVICE_AUTO_START
nssm start FabTwinBackend
```

**常见坑**：
- NSSM 服务**不读取** `env.bat`（bat 文件只在 cmd 会话中生效），必须用 `AppEnvironmentExtra` 传参
- `ORACLE_DSN_TYPE` 和 `ORACLE_CLIENT_DIR` 在 10g/11g 环境**必须**传入 NSSM，否则服务启动后连接 Oracle 失败
- 如用 `start_backend.bat`（cmd 启动而非服务），则会先 `call env.bat` 加载环境变量，无需重复传参

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
| Oracle 版本 | 10g / 11g / 12c / 19c 等 | 决定连接模式（见 1.2.1） |

**DB 组需确保该业务用户具有以下权限：**
- `CREATE SESSION` - 连接数据库
- `CREATE TABLE` / `CREATE SEQUENCE` / `CREATE TRIGGER` - 建表和自增主键支持
- `UNLIMITED TABLESPACE`（或对应表空间配额） - 数据存储

**应用部署方需确保：**
- 量产服务器能访问 DB 组的 Oracle 端口（默认 1521）
- 防火墙规则已开通（如跨网段）

#### 1.2.1 Oracle 版本兼容性（关键）

后端使用 Python `oracledb` 包连接 Oracle，支持两种模式：

| Oracle 版本 | 连接模式 | 是否需要 Oracle Client | 配置 |
|------------|----------|----------------------|------|
| **12.1+**（12c/18c/19c/21c/23ai） | Thin 模式（默认） | 否 | 无需额外配置 |
| **10g / 11g** | Thick 模式 | 是（Instant Client 11.2+） | 需设置 `ORACLE_CLIENT_DIR` |

**如量产 Oracle 是 10g / 11g，必须：**

1. 在量产服务器安装 Oracle Instant Client（11.2 或 19c 版本均可，19c 客户端可向下连接 9.2+）
   - 下载地址：https://www.oracle.com/database/technologies/instant-client.html
   - 选择 `instantclient-basic-windows.x64-19.x.0.0.0dbru.zip`
   - 解压到 `C:\oracle\instantclient_19_x`（路径无空格、无中文）

2. 设置环境变量 `ORACLE_CLIENT_DIR` 指向 Instant Client 目录：
   ```cmd
   setx ORACLE_CLIENT_DIR "C:\oracle\instantclient_19_x"
   ```

3. 后端 `database.py` 会自动检测并切换到 Thick 模式（无需改代码）

**报错对照表：**

| 错误码 | 含义 | 解决方案 |
|--------|------|----------|
| ORA-03134 | 连接到旧版本数据库被拒绝 | 切换到 Thick 模式（设置 `ORACLE_CLIENT_DIR`） |
| ORA-28040 | No matching authentication protocol | 同上，Thick 模式 + 高版本 Instant Client |
| DPI-1072 | Oracle Client 已初始化 | 忽略，正常现象 |

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
│   ├── init_oracle_db.sql      # 数据库初始化SQL（20张平台表，含 DISPLAY_ORDER 列，不含DT表/AI表）
│   ├── init_oracle_aqua.sql    # Aqua Data Studio 兼容版（无 SQL*Plus 命令）
│   ├── create_ai_tables.sql    # AI 相关 3 张表建表脚本（必须单独执行）
│   ├── v2.7_add_display_order.sql  # 旧库手动升级补 DISPLAY_ORDER 列（兜底，一般无需手动执行）
│   └── cleanup_db.sql          # 数据清理脚本
├── deploy.bat                  # 一键部署（开发/测试）
├── deploy_iis_nt_final.bat     # IIS NT认证部署（量产推荐）
├── start_backend.bat           # 仅启动后端
├── start-dev.bat               # 开发启动（前后端）
├── check_deployment.bat        # 部署诊断工具
├── init_db.bat                 # DB初始化
├── create_user.bat             # Oracle建用户
├── get_user.asp                # ASP桥接文件（Windows认证）
├── web.config                  # IIS配置文件
├── env.bat                     # 环境变量配置
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

**方式 3：用 Aqua Data Studio 执行**（适合 DB 组日常工具）

仓库已提供 Aqua Data Studio 兼容版本 `sql/init_oracle_aqua.sql`（由 `gen_aqua_sql.py` 从 `init_oracle_db.sql` 自动生成，移除了所有 SQL*Plus 特定命令）。

**操作步骤：**
1. 打开 Aqua Data Studio
2. 连接到 Oracle（DB 组提供的连接信息）
3. `File → Open` 打开 `sql/init_oracle_aqua.sql`
4. `Query → Execute All`（或 F5）执行整个脚本
5. 检查执行日志，确认无错误

**Aqua Data Studio 兼容性说明：**
- 已移除：`PROMPT`、`SET DEFINE OFF`、`SET SQLBLANKLINES ON`、`EXIT`、`SPOOL` 等 SQL*Plus 命令
- 保留：标准 SQL（CREATE TABLE / INSERT / DROP 等）+ PL/SQL 块（CREATE TRIGGER ... END; / ）
- 兼容工具：Aqua Data Studio、DBeaver、SQL Developer、Toad

**如需重新生成 Aqua 版本**（修改 init_oracle_db.sql 后）：
```cmd
cd /d D:\deploy\fab-twin-pro
python gen_aqua_sql.py
```

**该脚本会完成：**
- 删除旧表（如存在）
- 创建 20 张平台表（不含 DT 表、不含 AI 表）
- 导入基础数据（机台定义、角色、权限、用户等）
- 创建 11 个 SEQUENCE + TRIGGER（模拟 IDENTITY 自增主键）
- ver2.9.0：MACHINES / FLOOR_AREAS 表已内置 `DISPLAY_ORDER` 列（DEFAULT 0）

**重要说明：**
- DT 开头的 5 个表（DT_EVENT_RAW, DT_EVENT_RAW_CUR, DT_EVENT_STD, DT_ALARM_EVENT, DT_STATE_SNAPSHOT）**不在 init_oracle_db.sql 中**，由量产环境自行管理
- 应用首次启动时，ORM `create_all` 会自动创建这 5 个 DT 表（如不存在）
- 11 个 SEQUENCE+TRIGGER 用于替代 Oracle IDENTITY 列（因 ALTER TABLE MODIFY 不支持改为 IDENTITY，参见 ORA-30673），覆盖以下表：
  - CHAMBER_SNAPSHOTS, OHT_POSITIONS, AI_INSIGHTS, MACHINE_EVENTS, ALARMS
  - DASHBOARD_KPI, FLOOR_AREAS, TRACKS, ROLE_PERMISSIONS
  - MACHINE_TOOL_MAPPINGS, EVENT_ACTION_MAPPINGS

### 5.2.1 执行 AI 表建表脚本（必须，新建库和旧库升级都要执行）

> **AI 相关 3 张表不在 `init_oracle_db.sql` 中**，必须单独执行 `sql/create_ai_tables.sql`。此脚本幂等（DROP...PURGE + CREATE），重复执行不会报错。

**方式 1：sqlplus 执行（推荐）**

```cmd
REM 设置 Oracle 连接环境变量（如未设置）
set ORACLE_HOST=192.168.x.x
set ORACLE_PORT=1521
set ORACLE_SERVICE=ORCLPDB
set ORACLE_USER=fabtwin
set ORACLE_PASSWORD=********

REM 执行 AI 表建表脚本
sqlplus -S "%ORACLE_USER%/%ORACLE_PASSWORD%@%ORACLE_HOST%:%ORACLE_PORT%/%ORACLE_SERVICE%" @sql\create_ai_tables.sql
```

**方式 2：Aqua Data Studio / DBeaver 执行**

打开 `sql/create_ai_tables.sql`，整段执行（F5 / Execute All）。

**方式 3：Python 远程执行（无需 sqlplus）**

```cmd
cd /d D:\deploy\fab-twin-pro\backend
venv\Scripts\python.exe -c "import oracledb; conn=oracledb.connect(user='fabtwin', password='********', dsn='192.168.x.x:1521/ORCLPDB'); cur=conn.cursor(); sql=open('../sql/create_ai_tables.sql').read(); cur.execute(sql); conn.commit(); print('AI表建表完成')"
```

> 注：`create_ai_tables.sql` 包含 PL/SQL 块（TRIGGER...END;/），Python `execute` 可能无法整段执行。推荐用方式 1（sqlplus）或方式 2（Aqua/DBeaver）。

**该脚本会完成：**
- 创建 3 张 AI 表：`AI_CONFIGS`（键值对配置）、`AI_PROVIDER_CONFIGS`（LLM 多配置）、`AI_USAGE_LOGS`（Token 用量日志）
- 创建 3 个 SEQUENCE + 3 个 TRIGGER
- 导入默认配置：1 条「本地规则引擎」Provider + 12 条 Dify/N8N/MCP 键值对

**旧库升级注意**：如库中已有 AI 表数据，`create_ai_tables.sql` 会先 `DROP...PURGE` 再重建，**会清空 AI 配置数据**。如需保留现有 AI 配置，请在执行前备份 `AI_PROVIDER_CONFIGS` 和 `AI_CONFIGS` 表数据。

### 5.3 验证数据库（远程连接）

```sql
REM 使用 DB 组提供的连接信息
sqlplus fabtwin/********@192.168.x.x:1521/ORCLPDB

-- 检查平台表数量（不含 DT 表，含 AI 表）
SELECT COUNT(*) FROM user_tables WHERE table_name NOT LIKE 'DT_%';
-- 预期: 23（20 张平台表 + 3 张 AI 表）

-- 检查 SEQUENCE 数量
SELECT COUNT(*) FROM user_sequences;
-- 预期: 14（11 个平台表 + 3 个 AI 表）

-- 检查 TRIGGER 数量
SELECT COUNT(*) FROM user_triggers WHERE trigger_name LIKE 'TRG_%_ID';
-- 预期: 14（11 个平台表 + 3 个 AI 表）

-- 检查关键表数据
SELECT COUNT(*) FROM machines;          -- 机台定义（预期: 38）
SELECT COUNT(*) FROM users;             -- 用户
SELECT COUNT(*) FROM roles;             -- 角色（预期: 3 - admin/engineer/user）
SELECT COUNT(*) FROM perm_data;         -- 权限（预期: 10）
SELECT COUNT(*) FROM role_permissions;  -- 角色权限映射

-- ver2.9.0 新增：检查 DISPLAY_ORDER 列是否存在
SELECT column_name FROM user_tab_columns WHERE table_name='MACHINES' AND column_name='DISPLAY_ORDER';
SELECT column_name FROM user_tab_columns WHERE table_name='FLOOR_AREAS' AND column_name='DISPLAY_ORDER';
-- 预期: 各返回 1 行

-- 检查 AI 表（create_ai_tables.sql 执行后）
SELECT COUNT(*) FROM ai_provider_configs;  -- 预期: 1（本地规则引擎默认配置）
SELECT COUNT(*) FROM ai_configs;          -- 预期: 12（Dify/N8N/MCP 键值对）
SELECT COUNT(*) FROM ai_usage_logs;        -- 预期: 0（使用后才有数据）

EXIT;
```

---

## 6. 应用部署

### 6.1 IIS + Windows NT 认证部署（推荐，量产环境）

量产环境推荐使用 IIS 反向代理 + ASP 桥接获取 Windows 用户名，实现单点登录。

**前置条件：**
- Windows Server 已安装 IIS（含 ASP、Windows Authentication、URL Rewrite、ARR 模块）
- 前端已构建（`frontend\dist\` 存在）
- 后端 venv 已创建

**部署步骤：**

```cmd
REM 1. 构建前端（如已有 dist 可跳过）
cd /d D:\deploy\fab-twin-pro\frontend
npm install
npm run build

REM 2. 部署 IIS 站点（管理员权限）
cd /d D:\deploy\fab-twin-pro
deploy_iis_nt_final.bat
```

**deploy_iis_nt_final.bat 会完成：**
1. 检查 IIS、ASP、Windows Authentication 功能是否安装（未安装自动安装）
2. 复制 `frontend\dist\` 到 `C:\inetpub\wwwroot\FabTwin\`
3. 复制 `get_user.asp`（ASP 桥接文件）和 `web.config`（IIS 配置）到站点目录
4. 创建 IIS 应用程序池和站点（端口 80）
5. 停止 Default Web Site 释放端口 80
6. 用 `appcmd` 配置认证：站点匿名+Windows 认证，`get_user.asp` 仅 Windows 认证
7. 启用 ARR 反向代理
8. 启动 FabTwin 站点

**认证工作原理（ASP 桥接）：**
- IIS 独立运行，无法直接将 Windows 认证信息传递给 Python 后端
- `get_user.asp` 文件由 IIS 原生 ASP 引擎执行，直接读取 `LOGON_USER`
- 前端登录页调用 `/get_user.asp` → IIS 触发 Windows 认证 → 返回用户名
- 前端将用户名发送到 `/api/auth/login-windows` → 后端创建会话
- 每个用户使用自己的 Windows 工号登录，不再使用部署机器的账号

**启动后端：**
```cmd
cd /d D:\deploy\fab-twin-pro
start_backend.bat
```

**访问地址：** `http://<服务器IP>`（端口 80）

### 6.2 传统部署（deploy.bat，开发/测试用）

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

### 6.3 手动分步部署

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

**IIS 部署环境启动（推荐）：**
```cmd
REM 仅启动后端（前端由 IIS 提供）
cd /d D:\deploy\fab-twin-pro
start_backend.bat
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
- IIS 部署：浏览器访问 `http://<服务器IP>`（端口 80）
- 开发模式：浏览器访问 `http://localhost:5173`
- 应看到登录页面

**登录验证：**
- IIS 部署：点击"登录系统"，IIS 自动获取 Windows 工号完成登录
- 点击"管理员登录"使用 `admin` / `admin123`
- 部署诊断：运行 `check_deployment.bat` 检查前后端和 IIS 状态

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

**NT 用户自动登录行为（ASP 桥接模式）：**
- 用户访问登录页 → 前端调用 `/get_user.asp` → IIS 触发 Windows 认证
- 用户输入自己的 Windows 工号密码 → ASP 返回 `DOMAIN\工号`
- 前端将工号发送到 `/api/auth/login-windows` → 后端创建/更新用户会话
- 首次登录 → 自动在 `users` 表创建账号（`username = 工号`，`role = "user"`）
- 后续登录 → 更新 `last_login_at`，权限按 `user` 角色
- 每个用户使用自己的工号登录，不再共享部署机器的账号
- NT 用户**不能**编辑模型、平面图，**不能**访问用户管理界面
- 如无法获取 Windows 用户名，可点击"管理员登录"使用 `admin` / `admin123`

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

将后端注册为 Windows 服务，实现开机自启和后台运行。前端由 IIS 管理，无需注册服务。

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

### 8.3 IIS 站点自启动

IIS 站点默认随 Windows 服务 WAS（Windows Process Activation Service）自动启动，无需额外配置。

如需手动管理：
```cmd
REM 启动/停止 IIS 站点
%windir%\system32\inetsrv\appcmd.exe start site "FabTwin"
%windir%\system32\inetsrv\appcmd.exe stop site "FabTwin"

REM 确保 WAS 服务自启动
sc config WAS start= auto
sc config W3SVC start= auto
```

### 8.4 服务管理

```cmd
REM 查看后端状态
sc query FabTwinBackend

REM 停止/启动/重启后端
nssm stop FabTwinBackend
nssm start FabTwinBackend
nssm restart FabTwinBackend

REM 卸载后端服务
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

### 10.6 Windows Server 编码问题（UTF-8 / GBK）

**常见症状：**
- `.bat` 文件运行闪退（窗口一闪即关）
- 中文注释显示为乱码
- `chcp 65001` 后命令行无法正常输入
- SQL 文件执行报错 ORA-00911 invalid character

**原因：**
- Windows Server 中文版默认编码是 GBK（CP936），不是 UTF-8
- 文件保存为 UTF-8 with BOM 时，BOM 字节会被当作 SQL 内容导致 ORA-00911
- `.bat` 文件包含中文且编码不匹配时，cmd 解析失败导致闪退

**本项目已采取的规避措施：**

1. **所有 `.bat` 文件仅使用英文**（deploy.bat / init_db.bat / start_prod.bat / create_user.bat / package_offline.bat）
   - 移除了 `chcp 65001`（中文 Windows Server 上易导致解析问题）
   - 所有提示信息、注释、错误消息均为英文
   - 文件以 ANSI/GBK 编码保存（cmd 原生支持）

2. **SQL 文件保存为 UTF-8 无 BOM**
   - `init_oracle_db.sql` 和 `init_oracle_aqua.sql` 均为 UTF-8 无 BOM
   - 可用以下命令验证：
     ```cmd
     powershell -Command "$b=[IO.File]::ReadAllBytes('sql\init_oracle_db.sql')[0..2]; if($b[0]-eq0xEF-and$b[1]-eq0xBB-and$b[2]-eq0xBF){'UTF-8 with BOM'}else{'No BOM'}"
     ```

3. **如仍遇到编码问题：**
   - 用 Notepad++ 打开 `.bat` 文件 → `Encoding → Convert to ANSI`
   - 用 Notepad++ 打开 SQL 文件 → `Encoding → Convert to UTF-8 without BOM`
   - Windows Server 设置：`Control Panel → Region → Administrative → Change system locale → 取消勾选 Beta: Use Unicode UTF-8`

### 10.7 bat 脚本闪退排查

**所有 bat 脚本末尾均有 `pause`**，正常完成或出错都会等待用户按键。如仍出现闪退：

**排查步骤：**

1. **在 cmd 中手动运行**（不要双击）：
   ```cmd
   cd /d D:\deploy\fab-twin-pro
   deploy.bat
   ```
   这样即使脚本退出，cmd 窗口也不会关闭，可以看到错误信息。

2. **检查文件编码**：
   ```cmd
   powershell -Command "Get-Content deploy.bat -Encoding Byte -TotalCount 3"
   ```
   如返回 `239 187 191`（EF BB BF），说明是 UTF-8 with BOM，需另存为 ANSI。

3. **检查文件路径是否含中文/空格**：
   - 部署目录建议用纯英文路径，如 `D:\deploy\fab-twin-pro`
   - 避免使用 `D:\部署\` 或 `C:\Users\张三\` 等路径

4. **以管理员身份运行**：
   - 右键 `deploy.bat` → `以管理员身份运行`
   - 部分环境（如安装 venv、写入 Program Files）需要管理员权限

5. **打开 echo 调试**：
   - 编辑 bat 文件，第二行加 `@echo on`
   - 重新运行，会显示每条命令的执行过程

**常见闪退原因：**

| 原因 | 解决方案 |
|------|----------|
| 文件编码 UTF-8 with BOM | 另存为 ANSI 编码 |
| 路径含中文/空格 | 改用纯英文路径 |
| 缺少 `setlocal` / `endlocal` | 检查脚本结构（本项目已修复） |
| `setlocal enabledelayedexpansion` 配合 `!var!` 使用不当 | 检查变量引用（本项目已修复） |
| 调用 `npm` / `vite` 等 PowerShell 脚本被拦截 | 使用 `cmd /c "npm ..."` 绕过执行策略 |
| 权限不足（无法创建 venv） | 以管理员身份运行 |

---

## 附录 A：环境变量完整清单

> 详见第 12 节「Prod 环境变量配置注意事项」的分组说明和配置策略。

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| DB_TYPE | oracle | 是 | 数据库类型（仅支持 oracle） |
| ORACLE_HOST | localhost | 是 | Oracle 主机（**DB 组提供**） |
| ORACLE_PORT | 1521 | 是 | Oracle 端口（**DB 组提供**） |
| ORACLE_SERVICE | ORCLPDB | 是 | Oracle PDB 服务名/SID（**DB 组提供**） |
| ORACLE_USER | fabtwin | 是 | Oracle 用户名（**DB 组创建**） |
| ORACLE_PASSWORD | fabtwin | 是 | Oracle 密码（**DB 组创建**） |
| ORACLE_DSN_TYPE | service_name | **10g/11g 必填** | DSN 类型：`sid`（10g/11g）或 `service_name`（12c+，默认） |
| ORACLE_CLIENT_DIR | （空） | **10g/11g 必填** | 64-bit Oracle Client 19c+ 安装目录（如 `C:\app\client\...\client_1`），12c+ 不需要 |
| SIMULATION_ENABLED | False | 否 | 模拟器（prod 关闭） |
| DB_POLLER_ENABLED | True | 否 | DB 事件轮询（prod 开启，读 DT 表实时数据） |
| AI_PROVIDER | local | 否 | AI 提供方（prod 默认 local；LLM 配置走前端面板持久化到 DB） |
| AI_BASE_URL | （空） | 否 | OpenAI 兼容 API 地址（推荐用前端面板配置） |
| AI_API_KEY | （空） | 否 | AI API Key（推荐用前端面板配置） |
| AI_MODEL | glm-5.2 | 否 | AI 模型名称 |
| AI_TEMPERATURE | 0.7 | 否 | 生成温度 |
| AI_MAX_TOKENS | 2048 | 否 | 最大 token 数 |
| DIFY_ENABLED | False | 否 | Dify 开关 |
| DIFY_BASE_URL | （空） | 否 | Dify API 地址 |
| DIFY_API_KEY | （空） | 否 | Dify API Key |
| DIFY_APP_ID | （空） | 否 | Dify 应用 ID |
| N8N_ENABLED | False | 否 | N8N 开关 |
| N8N_BASE_URL | （空） | 否 | N8N 服务地址 |
| N8N_WEBHOOK_SECRET | （空） | 否 | N8N Webhook 密钥 |
| WHISPER_MODEL_SIZE | tiny | 否 | 语音识别模型（prod 离线保持 tiny） |
| WHISPER_DEVICE | cpu | 否 | 语音识别设备（prod 设 cpu） |
| WHISPER_COMPUTE_TYPE | int8 | 否 | 语音识别计算类型 |
| NLS_LANG | （空） | 否 | Oracle NLS 字符集（中文乱码时设 `SIMPLIFIED CHINESE_CHINA.AL32UTF8`） |

## 附录 B：端口清单

| 端口 | 服务 | 归属 | 说明 |
|------|------|------|------|
| 80 | IIS (前端) | 应用部署方 | 量产环境统一入口 |
| 5173 | Vite (前端) | 应用部署方 | 开发模式/preview |
| 8002 | FastAPI (后端) | 应用部署方 | API + WebSocket |
| 1521 | Oracle DB | **DB 组** | 数据库（DB 组管理） |
| 6379 | Redis (可选) | 应用部署方 | 缓存 |

## 附录 C：联系人

- 应用技术支持：（请填写）
- DB 组（Oracle 运维）：（请填写）
- 网络管理员：（请填写）

---

### 10.8 IIS 部署问题排查

**问题：HTTP 500.19 Internal Server Error（web.config 配置错误）**

```
Config Error: This configuration section cannot be used at this path.
```

> 原因：web.config 中使用了 `<location>` 节点或 locked 的 authentication 配置。
> 解决方案：本项目已移除 web.config 中的 authentication 配置，改用 `appcmd` 在 applicationhost.config 中配置。重新运行 `deploy_iis_nt_final.bat`。

**问题：HTTP 500（web.config 内容损坏）**

> 原因：PowerShell 动态生成 web.config 时引号被吞掉。
> 解决方案：本项目已改为直接 copy 预写好的 web.config 文件。重新运行 `deploy_iis_nt_final.bat`。

**问题：访问网站显示 IIS 欢迎页而非 FabTwin**

> 原因：Default Web Site 未停止，占用端口 80。
> 解决方案：
> ```cmd
> %windir%\system32\inetsrv\appcmd.exe stop site "Default Web Site"
> %windir%\system32\inetsrv\appcmd.exe start site "FabTwin"
> ```

**问题：登录提示"无法获取 Windows 用户名"**

> 原因：`get_user.asp` 匿名访问未禁用，IIS 未触发 Windows 认证。
> 解决方案：重新运行 `deploy_iis_nt_final.bat`，确保 appcmd 正确配置 `get_user.asp` 的认证。
> 验证：在浏览器中直接访问 `http://<服务器IP>/get_user.asp`，应弹出 Windows 认证对话框。

**问题：登录后页面不跳转，停留在登录页**

> 原因：前端 401 拦截逻辑导致登录成功后跳回登录页。
> 解决方案：清除浏览器缓存，重新构建前端 `npm run build` 后重新部署。

**问题：所有用户登录后都显示同一个工号**

> 原因：IIS 反向代理无法传递 Windows 认证信息给独立 Python 进程。
> 解决方案：本项目使用 ASP 桥接方案（`get_user.asp`），确保每个用户通过自己的工号登录。重新运行 `deploy_iis_nt_final.bat`。

**问题：API 请求返回 404 或 502**

> 原因：IIS 反向代理规则未正确配置，或后端未启动。
> 解决方案：
> 1. 确认后端运行在 8002 端口：`curl http://localhost:8002/health`
> 2. 确认 ARR 代理已启用：`%windir%\system32\inetsrv\appcmd.exe list config -section:system.webServer/proxy`
> 3. 运行 `check_deployment.bat` 诊断

**问题：bat 脚本运行报错 'xxx' is not recognized as an internal or external command**

> 原因：bat 文件换行符为 LF（Linux），Windows cmd 无法正确解析。
> 解决方案：用 Notepad++ 打开 → 编辑 → 文档格式转换 → 转为 Windows (CRLF) 格式。
> 或在 Git 中设置：`git config core.autocrlf true` 后重新 pull。

---

**文档版本**：v3.0
**最后更新**：2026-09-02
**变更说明**：
- v3.0 (2026-09-02): 覆盖 ver2.9.0 A/B/C/D/E/F/G 七批变更；新增第 11 节「ver2.9.0 变更摘要」；新增第 12 节「Prod 环境变量配置注意事项」；`init_oracle_db.sql` 更新含 `DISPLAY_ORDER` 列；新增 5.2.1 节「AI 表建表脚本执行」；更新离线包清单（含 `create_ai_tables.sql`、`v2.7_add_display_order.sql`）；更新数据库验证清单（表 23 张、SEQUENCE 14 个、TRIGGER 14 个、DISPLAY_ORDER 列检查、AI 表数据检查）；更新附录 A 环境变量清单
- v2.0 (2026-07-22): 重构部署方案，IIS + ASP 桥接 Windows NT 认证作为推荐量产部署方式；新增 `deploy_iis_nt_final.bat` 和 `start_backend.bat`；移除 `start_prod.bat`、`start_full.bat`、`start_proxy.bat` 等中间版本脚本；新增 IIS 部署问题排查章节；更新端口清单（端口 80 由 IIS 使用）；更新服务注册章节（前端由 IIS 管理）；清理 31 个临时调试脚本
- v1.3 (2026-07-20): 新增 Oracle 10g/11g 兼容性说明（Thick 模式 + ORACLE_CLIENT_DIR）；新增 Aqua Data Studio 初始化 SQL 使用方式；新增 Windows Server UTF-8/GBK 编码问题处理；新增 bat 脚本闪退排查章节；所有 bat 文件改为纯英文避免编码问题
- v1.2 (2026-07-20): 明确 Oracle 数据库由 DB 组搭建运维，应用部署方仅需索取连接信息；移除"安装 Oracle Client"要求；业务用户/表空间创建改为由 DB 组执行；init_db.bat 支持远程执行或由 DB 组在 DB 服务器执行；故障排查章节调整为联系 DB 组
- v1.1 (2026-07-20): 修复 init_db.bat 自动检测 ORACLE_HOME；deploy.bat 改用 vite preview 生产模式 + SQL 脚本初始化；补充 SEQUENCE+TRIGGER、RBAC 权限控制、NT 用户自动登录说明
- v1.0 (2026-07-20): 初版 SOP
**审核人**：（待填写）
