# FabTwin Win2022 部署 SOP

## 一、部署前准备

### 1.1 必备软件清单

| 软件 | 版本 | 用途 | 下载 |
|------|------|------|------|
| Python | 3.11+ (64bit) | 后端运行时 | https://www.python.org/downloads/ |
| Node.js | 18+ (LTS) | 前端构建 | https://nodejs.org/ |
| Oracle Client | 19c+ (64bit) | Oracle Thick 模式 | https://www.oracle.com/database/technologies/instant-client.html |
| Visual C++ 2013 Redistributable (x64 + x86) | - | Oracle Client 依赖 | https://www.microsoft.com/download/details.aspx?id=40784 |
| Visual C++ 2022 Redistributable (x64) | - | Oracle 19c Client 依赖 | https://aka.ms/vs/17/release/vc_redist.x64.exe |
| IIS | Windows 内置 | Web 服务器（可选） | 服务器管理器 → 添加角色 |
| URL Rewrite Module 2.1 | - | IIS 反向代理 | https://www.iis.net/downloads/microsoft/url-rewrite |

### 1.2 网络要求

- 服务器需能访问 Oracle DB `10.30.8.119:1521`
- 服务器需开放端口：
  - **8002**（后端 API + WebSocket，IIS 模式必须开放给客户端）
  - **80**（IIS，IIS 模式）
  - **5173**（Vite preview，直连模式）

### 1.3 env.bat 配置

部署前必须确认 `env.bat` 内容正确（路径：项目根目录）：

```batch
@echo off
set DB_TYPE=oracle
set ORACLE_HOST=10.30.8.119
set ORACLE_PORT=1521
set ORACLE_SERVICE=APCDB
set ORACLE_USER=emuuser
set ORACLE_PASSWORD=apcuser
set ORACLE_DSN_TYPE=sid
set ORACLE_CLIENT_DIR=C:\app\client\c11463\product\19.0.0\client_1
set SIMULATION_ENABLED=False
set DB_POLLER_ENABLED=True
```

**注意**：
- `ORACLE_CLIENT_DIR` 必须指向 Oracle Client 根目录（含 `bin\oci.dll`）
- `ORACLE_DSN_TYPE=sid` 用于 Oracle 10g/11g；12c+ 用 `service_name`
- 文件中**禁止使用中文字符**（GBK 编码会导致 cmd 解析失败）

---

## 二、两版部署方案

### 方案 A：直连模式（推荐，最简单可靠）

**架构**：浏览器 → Vite:5173 → 后端:8002（HTTP + WebSocket 全部走 Vite proxy）

**优点**：不需要 IIS，不需要 ARR，WebSocket 原生支持，与开发环境行为完全一致

```cmd
:: 1. 拉取代码
git pull origin test1

:: 2. 一键启动（自动创建 venv + 安装依赖 + 构建前端 + 启动服务）
start_direct.bat
```

**验证**：
- 浏览器访问 `http://SERVER-IP:5173`
- API 文档 `http://SERVER-IP:8002/docs`
- 健康检查 `http://SERVER-IP:8002/health`

---

### 方案 B：IIS 模式

**架构**：
- HTTP API：浏览器 → IIS:80 → URL Rewrite → 后端:8002
- WebSocket：浏览器 → 后端:8002（直连，绕过 IIS）
- 静态文件：IIS 直接提供 `frontend/dist`

```cmd
:: 1. 拉取代码
git pull origin test1

:: 2. 安装 IIS 角色（服务器管理器 → 添加角色和功能 → Web 服务器 IIS）
::    必须勾选：
::    - WebSocket 协议（万维网服务 → 应用开发 → WebSocket 协议）
::    - URL Rewrite（需单独下载安装）

:: 3. 部署前端到 IIS（管理员身份运行）
deploy_iis_nt_final.bat

:: 4. 启动后端服务（管理员身份运行）
start_iis.bat

:: 5. 开放 8002 端口防火墙（WebSocket 直连需要）
netsh advfirewall firewall add rule name="FabTwin Backend" dir=in action=allow protocol=TCP localport=8002
```

**验证**：
- 浏览器访问 `http://SERVER-IP`
- 浏览器 F12 → Console 应看到 `[WS] Connecting to: ws://SERVER-IP:8002/ws/realtime (IIS mode, direct to backend)`
- 浏览器 F12 → Network → WS 标签页应看到 101 Switching Protocols

---

## 三、常见问题排查

### 3.1 pip install 失败

**现象**：`UnicodeDecodeError: 'gbk' codec can't decode byte`

**根因**：requirements.txt 含中文注释，pip 用 GBK 读取 UTF-8 文件

**修复**：已移除所有中文注释。若仍出错，检查是否有其他 .txt 文件含中文

---

**现象**：离线安装 fastapi 找不到

**根因**：脚本未使用 `--no-index --find-links=wheels` 离线模式

**修复**：已统一所有 bat 检测 `wheels` 目录，存在则离线安装。确保 `backend/wheels/` 目录存在且包含所有依赖的 .whl 文件

**离线包制作**（在有网机器上执行）：
```cmd
cd backend
mkdir wheels
pip download -r requirements.txt -d wheels
```

---

### 3.2 Oracle 连接失败

**现象**：`DPI-1047: Cannot locate a 64-bit Oracle Client library`

**根因**：Oracle Client 未安装或 ORACLE_CLIENT_DIR 路径错误

**修复**：
1. 安装 Oracle 19c Client（64bit）
2. 安装 Visual C++ 2013 + 2022 Redistributable
3. 确认 `ORACLE_CLIENT_DIR` 指向 `client_1` 根目录（含 `bin\oci.dll`）

---

**现象**：`ORA-12504: TNS:listener was not given the SERVICE_NAME`

**根因**：Oracle 10g/11g 用 sid 模式，但 DSN 类型设为 service_name

**修复**：env.bat 设置 `ORACLE_DSN_TYPE=sid`

---

**现象**：`ORA-01843: not a valid month`

**根因**：Oracle 字符串日期比较，月份格式不匹配

**修复**：已全部改为 Python 层 `parse_ts` 解析，不在 SQL 层做时间比较

---

### 3.3 IIS 500 错误

**现象**：部署后网页直接 500

**根因**：web.config 中 `<webSocket>` 配置节被 IIS 锁定（overrideModeDefault="Deny"）

**修复**：已从 web.config 移除 `<webSocket>` 节，改用 appcmd 在站点级别设置

---

### 3.4 WebSocket 连接失败

**现象**：前端实时事件流无内容，F12 Console 显示 `[WS] 连接关闭，准备重连...`

**根因**：URL Rewrite 模块不能代理 WebSocket 升级握手

**修复**：前端检测 IIS 环境（port 80/443）后直连后端 8002，绕过 IIS

**验证**：
1. 确认后端 8002 端口已开放防火墙
2. 确认 `start_iis.bat` 或 `start_backend.bat` 已启动后端
3. F12 Console 应看到 `[WS] 已连接实时事件流`

---

### 3.5 回放/事件无数据

**现象**：Lots 可导出，但回放和事件流为空

**根因**：history.py 用 `LIKE '2026-07-23 %'` 匹配，但 DB 时间格式可能是 `2026-07-23T08:00:00`（T 分隔）或 `2026-7-23 下午12:01:14`（NLS 中文）

**修复**：已全部改为 Python 层 `parse_ts` 解析过滤，不在 SQL 层做时间过滤

---

### 3.6 实时事件流时间只显示 `2026-7-`

**根因**：前端 `formatTime` 直接 slice 字符串，遇到 NLS 中文格式截断错误

**修复**：前端改用 `new Date()` 解析 + `padStart` 格式化

---

## 四、项目清理记录

### 4.1 已删除的本地遗留文件

| 文件 | 删除原因 |
|------|----------|
| `env_local.bat` | 本地 SQLite 配置，量产不再需要 |
| `init_local_db.bat` | 本地 SQLite 初始化脚本 |
| `setup_local_oracle.sql` | 本地 Oracle 测试脚本 |
| `sync_from_production.py` | 量产数据同步脚本，已无用 |

### 4.2 SQLite 残留清理

| 文件 | 修改内容 |
|------|----------|
| `backend/config.py` | 移除 SQLite 分支，DB_TYPE 非 oracle 时 sys.exit(1) |
| `backend/database.py` | 移除 DB_IS_SQLITE 判断，无条件执行 Oracle Thick 模式 |
| `backend/main.py` | 移除 `DB_IS_SQLITE` 导入和日志 |
| `backend/requirements.txt` | 移除 `aiosqlite` 依赖 |
| `env.bat` | 注释改为 "oracle only" |
| 所有 `start_*.bat` | env.bat 缺失时报错退出，不再 fallback SQLite |

### 4.3 时间格式统一

| 文件 | 修改内容 |
|------|----------|
| `backend/services/time_utils.py` | 新建公共模块，提供 `parse_ts`/`normalize_ts`/`extract_date` |
| `backend/routers/history.py` | 移除内联 `_parse_ts`，改用 `time_utils.parse_ts` |
| `backend/routers/lots.py` | 移除 SQL LIKE 时间过滤和字符串比较，改用 Python 层 `parse_ts` |
| `backend/routers/alarms.py` | 移除 SQL LIKE 时间过滤，改用 Python 层 `parse_ts` |
| `backend/routers/events.py` | 移除 SQL LIKE 时间过滤，改用 Python 层 `parse_ts` |
| `backend/routers/rvmessages.py` | 移除 `func.coalesce` + `ORDER BY VARCHAR2`，改用 `raw_id` 排序 |
| `backend/services/db_poller.py` | 移除内联 `_parse_ts`，改用 `time_utils.parse_ts` |
| `backend/services/ai_middleware.py` | 修复 `ORDER BY event_ts_utc.desc()` → `raw_id.desc()`；修复 `lot.priority`/`lot.recipe` 字段错误 |

### 4.4 部署脚本修复

| 文件 | 修改内容 |
|------|----------|
| `one_click_deploy.bat` | pip 安装检测 wheels 目录离线安装 |
| `start_backend.bat` | env.bat 缺失报错退出，pip 检测 wheels 目录 |
| `start-dev.bat` | env.bat 缺失报错退出，pip 检测 wheels 目录 |
| `start_iis.bat` | 新建，IIS 模式启动（HTTP 走 IIS，WS 直连 8002） |
| `start_direct.bat` | 新建，直连模式启动（全走 Vite proxy） |
| `frontend/src/composables/useWebSocket.js` | 检测 IIS 环境（port 80/443），WS 直连后端 8002 |

---

## 五、部署验证清单

部署完成后逐项验证：

- [ ] `http://SERVER-IP:5173`（直连模式）或 `http://SERVER-IP`（IIS 模式）能打开登录页
- [ ] admin/admin123 登录成功
- [ ] Dashboard 显示机台列表（44台）
- [ ] 点击机台进入详情页
- [ ] **历史回放**：选择日期 → 时间轴显示事件分布 → 点击事件能跳转
- [ ] **实时事件流**：F12 Console 看到 `[WS] 已连接实时事件流`，EventList 显示事件
- [ ] **Lot 列表**：能导出当天 Lot
- [ ] **告警统计**：显示告警数量
- [ ] 后端日志看到 `[DB Poller] 启动推送 50 条历史事件`（说明 db_poller 工作正常）
