# FabTwin + Dify + n8n 部署执行 SOP（手把手版）

> **适用版本：ver2.10.13（2026-09-11）**
> **你不需要懂 Dify/n8n 原理，照着下面每一步做就行。**
>
> 架构：Dify（AI 中枢）→ n8n（HTTP Request）→ DB Proxy（Python FastAPI）→ Oracle 11g

## 本版重大变更（老用户必读）

如果你之前按旧 SOP 部署过 10 个工作流，**这次必须重做第 2~4 步**，否则 AI 会调不到工具。

| 项目 | 旧版 | 本版 |
| --- | --- | --- |
| Dify 工具数 | 10 个（F1~F10 各一个 path，占满工具位） | **2 个**（`fab_query` / `fab_admin`），腾出 8 个位子挂 LOG 捞取等工具 |
| n8n 工作流 | 导入并激活 10 个 | **只需 2 个**（`FAB_QUERY_merged` / `FAB_ADMIN_merged`） |
| 调用方式 | 每个工具独立 | 统一 POST + **必传 `action` 参数**分发 |
| db_proxy 地址 | `10.30.116.150:8001` | **`10.30.5.216:8001`** |
| Dify 提示词 | 写死 10 个旧工具名 | 已重写为双工具 + action 枚举表，**必须重新导入** |

> **为什么要收敛**：Dify 按 OpenAPI 里的 path 数量注册工具，10 个 path 一次性把 Agent 工具位占满，
> 导致 EAP LOG 捞取等其他工具挂不上去。收敛为 2 个 path 后，用 `action` 参数区分具体能力。
>
> **旧的 10 个 db_proxy 端点没有删除**，仍可直连调用，方便随时回退。

***

## 环境地址速查

先把你现场的实际地址填进这张表，后面每一步都对照它填：

| 组件 | 本文档示例地址 | 你的实际地址 |
| --- | --- | --- |
| Dify | `http://10.30.116.68` | ______ |
| n8n | `http://10.30.116.151:5678` | ______ |
| DB Proxy | `http://10.30.5.216:8001` | ______ |
| Oracle 11g | `10.30.5.216:1521` | ______ |
| EAP 服务（LOG 捞取用） | `http://10.30.8.243:8080` | ______ |
| DB Proxy API Key | `fabtwin-proxy-2026` | ______ |

前置条件：Dify 与 n8n 均已部署且网页可访问；FabTwin 后端 server 上有 Oracle Client（DB Proxy 连 11g 需要）。

***

## 总览（8 大步）

| 步骤 | 在哪做 | 做什么 | 耗时参考 |
| --- | --- | --- | --- |
| 第 1 步 | FabTwin Server | 部署 / 重启 DB Proxy 服务 | 10 分钟 |
| 第 2 步 | n8n | 导入 **2 个合并工作流** + 激活 | 5 分钟 |
| 第 3 步 | 命令行 | 跑分层自测脚本，确认底座通了 | 3 分钟 |
| 第 4 步 | Dify | 重新导入应用模板 .yml | 3 分钟 |
| 第 5 步 | Dify | 配置 OpenAPI 工具（2 个工具） | 10 分钟 |
| 第 6 步 | Dify | 测试对话（验证 AI 会传 action） | 5 分钟 |
| 第 7 步 | FabTwin 后端 | 配置 .env（Dify 地址 + API Key） | 3 分钟 |
| 第 8 步 | FabTwin 网页 | 重新构建前端 + 端到端测试 | 10 分钟 |

***

## 第 1 步：部署 / 重启 DB Proxy

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
ORACLE_HOST=10.30.5.216
ORACLE_PORT=1521
ORACLE_SERVICE=ORCL
ORACLE_DSN_TYPE=sid
ORACLE_CLIENT_DIR=C:\app\client\product\11.2.0\client_1

# 代理服务
DB_PROXY_PORT=8001
DB_PROXY_API_KEY=fabtwin-proxy-2026
```

> **重要**：`ORACLE_DSN_TYPE=sid`（11g 用 SID 模式，不是 service_name）
> `ORACLE_CLIENT_DIR` 指向你的 Oracle Client 安装目录（要有 oci.dll）

### 1.4 启动（本版必须重启，才会有新端点）

```bash
python main.py
```

或双击 `start.bat`。

### 1.5 确认成功

```bash
# 健康检查
curl http://10.30.5.216:8001/health
# 期望：{"status":"ok","db":"connected"}
```

**关键：确认 2 个新分发端点存在**（这是本版新增的，没有就说明服务没重启）：

```bash
curl -X POST http://10.30.5.216:8001/query/fab_query ^
  -H "X-API-Key: fabtwin-proxy-2026" -H "Content-Type: application/json" ^
  -d "{\"action\":\"list_capabilities\"}"
```

期望返回 `ok=true` 且 `table_data` 里是 C1~C10 功能清单。

顺手验一下**错误自愈**能力（AI 传错 action 时靠这个纠正）：

```bash
curl -X POST http://10.30.5.216:8001/query/fab_query ^
  -H "X-API-Key: fabtwin-proxy-2026" -H "Content-Type: application/json" ^
  -d "{\"action\":\"xxx\"}"
```

期望返回 **HTTP 200** + `ok=false`，`answer` 里列出所有支持的 action（**不是** 500 报错）。
这个设计是故意的：Dify 拿到可读文本才能让模型自己改正重试。

### 1.6 设为后台服务（可选）

用 NSSM 或 Windows 任务计划程序设为开机自启。

***

## 第 2 步：在 n8n 导入 2 个合并工作流

### 2.1 停用旧的 10 个工作流

打开 n8n → Workflows，把 `F1_get_machine_status` ~ `F10_list_capabilities` 这 10 个的 **Active 开关关掉**。

> 不删除，只停用。万一新版有问题可以随时切回去。
> 如果你从没导入过旧版，跳过这一步。

### 2.2 导入 2 个新工作流

**Workflows** → **Import from File**，依次导入：

| 文件 | Webhook path | 转发到 |
| --- | --- | --- |
| `docs/integration/n8n/FAB_QUERY_merged.json` | `fab_query` | `http://10.30.5.216:8001/query/fab_query` |
| `docs/integration/n8n/FAB_ADMIN_merged.json` | `fab_admin` | `http://10.30.5.216:8001/query/fab_admin` |

每个工作流都是 3 个节点：**Webhook → Query DB Proxy → Respond**。

### 2.3 核对 DB Proxy 地址

双击 **Query DB Proxy** 节点，检查两处：

1. **URL** 是不是 `http://10.30.5.216:8001/query/fab_query`（admin 那个是 `/fab_admin`）
   —— 如果你的 DB Proxy 不在这个地址，改成实际的
2. **X-API-Key** 头的值是不是和 DB Proxy `.env` 里的 `DB_PROXY_API_KEY` 一致

另外确认 Body 是 `={{ JSON.stringify($json.body || {}) }}`——**这一句负责把 Dify 传来的 `action`
原样透传给 DB Proxy**，改错了会导致所有请求都报"缺少 action 参数"。

### 2.4 激活

两个工作流右上角 **Active** 开关打开（变绿色）。

### 2.5 确认成功

```bash
curl -X POST http://10.30.116.151:5678/webhook/fab_query ^
  -H "Content-Type: application/json" ^
  -d "{\"action\":\"machine_status\",\"machine_id\":\"OXE-1\"}"
```

期望返回 `ok=true` + OXE-1 的状态数据。

> 如果返回 404：工作流没激活，或者用了 `/webhook-test/` 而不是 `/webhook/`（前者只在你点了
> "Listen for test event" 后的 120 秒内有效，正式调用一律用 `/webhook/`）。

***

## 第 3 步：跑分层自测脚本

在接 Dify 之前，先用脚本确认「DB Proxy 直连」和「经 n8n」两层都通，这样出问题能立刻定位是哪一层。

> ⚠️ **注意脚本别选错**，项目里有两个名字很像的：
>
> | 脚本 | 用途 | 支持 `--merged` |
> | --- | --- | --- |
> | `tests/test_n8n_f1_f10.py` | **本步骤用这个**，F1~F10 分层自测 | ✅ |
> | `tests/test_n8n_integration.py` | 旧的 5 个业务工作流端到端测试 | ❌ |
>
> 传错了会看到 `error: unrecognized arguments: --merged`。

### 3.1 测合并版（本版用这条）

```powershell
cd E:\HJQ\deploy\fab-twin-pro
python tests\test_n8n_f1_f10.py --merged
```

`--proxy` 默认已是 `http://10.30.5.216:8001`，`--n8n` 默认 `http://10.30.116.151:5678`，
地址对得上就不用额外传参。

### 3.2 常用参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--merged` | 关 | **本版必加**。n8n 层改测 2 个合并 webhook；不加则测旧的 10 个 |
| `--proxy` | `http://10.30.5.216:8001` | DB Proxy 地址 |
| `--n8n` | `http://10.30.116.151:5678` | n8n 地址 |
| `--api-key` | `fabtwin-proxy-2026` | DB Proxy 的 X-API-Key |
| `--secret` | 空 | n8n Webhook secret（配了才填） |
| `--layer` | `both` | 只测某一层：`proxy` / `n8n` / `both` |
| `--machine` | `OXE-51` | 测试机台号 |
| `--lot` | `V47Q6` | 测试批号（F7 用） |
| `--json-out` | 空 | 结果写入 JSON 文件，便于回传 |

### 3.3 分层排错

```powershell
# 只测直连 DB Proxy —— 失败说明是 DB Proxy / Oracle 的问题，与 n8n 无关
python tests\test_n8n_f1_f10.py --layer proxy

# 只测经 n8n —— proxy 层过了但这层挂，问题就在 n8n 工作流配置
python tests\test_n8n_f1_f10.py --layer n8n --merged

# 导出结果便于回传
python tests\test_n8n_f1_f10.py --merged --json-out result.json
```

**确认成功**：10 个用例全绿。有失败的先解决，不要往下走。

***

## 第 4 步：在 Dify 重新导入应用模板

> **本版必须重新导入或手工替换提示词**。旧提示词里写死了 10 个已下线的工具名
> （`get_machine_status` 等），模型会凭记忆去调根本不存在的工具，而且不知道要传 `action`，必然失败。

### 4.1 选对文件

| 文件 | 用途 |
| --- | --- |
| `docs/integration/dify/fabtwin-ai-assistant.dsl.yml` | **通用版**，全局 AI 助手用这个 |
| `docs/integration/dify/fabtwin-ai-assistant-OXE.dsl.yml` | OXE 刻蚀机专用版，开头多一句 OXE 上下文 |
| `docs/integration/dify/eap-log-query.dsl.yml` | EAP LOG 捞取，独立应用，与本流程无关 |

### 4.2 两种导入方式

**方式 A：整体导入（推荐，全新部署或可以重建应用时）**

1. Dify → **Create App** → **Import DSL file**
2. 选择上面的 .yml
3. 导入后自动跳转到应用编排页面

**方式 B：只换提示词（已有应用、不想重配的话用这个）**

1. 用文本编辑器打开 .yml，找到 `pre_prompt:` 这一行
2. 复制它后面的完整字符串内容（**去掉外层双引号，把 `\n` 还原成真实换行**）
3. 粘贴进 Dify 应用编排页的「提示词」输入框，覆盖原内容
4. 保存并发布

> 方式 B 容易漏转义，能用方式 A 就用 A。

### 4.3 确认成功

- 应用名称 **FabTwin AI Assistant**，类型是 **Agent**（`mode: agent-chat`）
- 提示词里能搜到 `fab_query` 和 `fab_admin`，**搜不到** `get_machine_status` 这类旧工具名
- 提示词里有「工具列表（只有 2 个工具，全部能力靠 action 参数区分）」这段和两张 action 表
- Variables 能看到 `machine_id` 和 `user_role`

> **已知坑（本版已修）**：旧 .yml 第 12 行是 `value: plugin_unique_identifier: xxx`，
> 同一行两个冒号属于非法 YAML，Dify 导入会直接失败。本版已改成正确的缩进嵌套。
> 如果你手上还有旧文件导入报格式错误，就是这个原因。

***

## 第 5 步：在 Dify 配置 OpenAPI 工具

> **注意**：DSL 里 `tools: []` 是空的，**导入模板不会自动带上工具**，这一步必须手工做。

### 5.1 清理旧工具

如果之前配过 10 工具版的 Custom Tool，先在 **工具** 页面把它**删除**，
再回到应用编排页把已勾选的旧工具取消。不清理会残留 10 个占位。

### 5.2 上传 OpenAPI 规范

1. Dify → **工具** → **创建自定义工具**
2. 名称填 `FabTwin n8n Tools`
3. 把 `docs/integration/dify/fabtwin-tools-openapi.yaml` 的**全部内容**粘贴进 Schema 框
4. **唯一要改的地方**：把 `servers.url` 换成你自己的 n8n 地址

   文件里现在已经是可用的真实地址（不再是占位符）：

   ```yaml
   servers:
     - url: http://10.30.116.151:5678/webhook
   ```

   如果你的 n8n 不在这个地址，改这一行即可，其余不要动。
   注意末尾的 `/webhook` 必须保留，且不要写成 `/webhook-test`。

5. 鉴权方式：n8n 的 HTTP 节点里已经带了 `X-API-Key`，Dify 这层选 **None** 即可
6. 保存

> 该文件已用 `openapi-spec-validator` 通过 OpenAPI 3.0.3 正式校验，
> 可直接粘贴，不会出现「Schema 解析失败」。

### 5.3 挂到应用并启用

回到 FabTwin AI Assistant 应用编排页 → **工具** → 添加刚建的自定义工具，
勾选 **`fab_query`** 和 **`fab_admin`** 两个。

### 5.4 确认成功

- 工具列表里**只有 2 个**：`fab_query`、`fab_admin`
- 点开 `fab_query` 能看到 `action` 是必填（required），枚举值有 7 个
- 点开 `fab_admin` 能看到 3 个 action：`mes_lot_info` / `export_alarm_report` / `generate_work_order`
- 工具位还剩 8 个空位，可以继续挂 EAP LOG 捞取等其他工具

***

## 第 6 步：在 Dify 测试对话

点 **预览 / 调试**，按顺序测这几条：

| 输入 | 预期 AI 调用 | 预期结果 |
| --- | --- | --- |
| `你能帮我干什么` | `fab_query` + `{"action":"list_capabilities"}` | 返回 C1~C10 功能清单表格 |
| `OXE-1机台状态如何` | `fab_query` + `{"action":"machine_status","machine_id":"OXE-1"}` | 状态数据 + 结构化块里有 `jump_machine_id` |
| `最近7天有什么报警` | `fab_query` + `{"action":"machine_alarms","days":7}` | 全厂报警统计 |
| `OXE-1今天产量` | `fab_query` + `{"action":"yield_stats","machine_id":"OXE-1","time_range":"today"}` | 产量数据 |
| `导出OXE-1近7天报警报表` | `fab_admin` + `{"action":"export_alarm_report","machine_id":"OXE-1","days":7}` | 下载链接（需 `user_role=admin`） |

**重点检查**：展开 Dify 的工具调用日志，确认**每次请求的 JSON 里都带 `action` 字段**。
这是本版最容易出问题的地方——模型漏传 action，请求必失败。

**同时确认回答末尾有 `<FABTWIN>` 结构化块**，形如：

```
<FABTWIN>{"table_data":{...},"jump_timestamp":null,"jump_machine_id":"OXE-1","sources":[...]}</FABTWIN>
```

`jump_machine_id` 决定前端能不能渲染出跳转按钮，**只要回答涉及某台具体机台就必须有值**。

***

## 第 7 步：配置 FabTwin 后端

### 7.1 获取 Dify API Key

Dify 应用 → **发布** → **访问 API** → 复制 API Key（`app-` 开头）。

### 7.2 编辑后端 .env

```env
ENABLE_LOCAL_RULE_FALLBACK=false
DIFY_BASE_URL=http://10.30.116.68
DIFY_API_KEY=app-你的key
```

重启后端。

***

## 第 8 步：前端重新构建 + 端到端测试

### 8.1 重新构建前端（ver2.10.13 必做）

本版修了 AI 助手的下载链接渲染和跳转按钮，**不重新构建看不到效果**：

```powershell
cd frontend
npm run build
```

### 8.2 功能测试

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| 浮动球不带机台 | `今天产量` | 提示"请告诉我机台ID" |
| OXE-1 详情页 | `今天产量` | 产量表格 + 跳转按钮 |
| 全厂报警 | `最近7天有什么报警` | 全厂报警统计 |
| 普通用户导出 | `导出报警报表` | "需管理员权限" |
| 管理员导出 | `导出报警报表` | 返回下载链接 |

### 8.3 本版重点回归（ver2.10.13 修复项）

| 检查项 | 操作 | 预期 |
| --- | --- | --- |
| **下载链接渲染** | 问 `帮我捞取最近的OXE-2的log` | 显示 **⬇️ 图标**（可点击下载），**不是** `[⬇️](http://...)` 原文，也不显示冗长 URL |
| **表格渲染** | 同上 | markdown 表格渲染成真正的 HTML 表格，不是 `\| 机台 \| 日期 \|` 文本 |
| **跳转（带机台不带时间）** | 问 `OXE-1机台状态如何` → 点「跳转」 | 跳到 OXE-1 详情页 |
| **跨机台跳转** | 在 OXE-1 页问 OXE-2 → 点「跳转到OXE-2」 | 跳到 OXE-2 详情页 |
| **已在目标页** | 在 OXE-1 页问 OXE-1 → 点跳转 | 提示"已在机台 OXE-1 详情页" |
| **带时间戳跳转** | 问历史事件 → 点「跳转到历史回放」 | 跳到对应机台并定位到该时间点 |

> 这两个 bug 的根因：下载链接是 `AIFloatingBall.vue` 用纯插值 `{{ }}` 不解析 markdown；
> 跳转是 `App.vue` 的 `handleAIJump` 里 `if (!ts) return`，把只有机台 ID、没有时间戳的
> 跳转请求静默拦掉了。两者已分别修复。

***

## 架构图

```
用户在 FabTwin 网页提问
        │
        ▼
FabTwin 后端 (ai_middleware.py)
        │  POST /v1/chat-messages
        ▼
┌───────────────────────┐
│  Dify (AI 中枢)        │  理解自然语言 → 选工具 → 决定 action → 整理答案
│  工具位：2/10 已用      │
└───────┬───────────────┘
        │  调工具（HTTP Webhook，body 必带 action）
        ▼
┌───────────────────────┐
│  n8n (2 个工作流)       │  Webhook → HTTP Request → Respond
│  /webhook/fab_query    │  透传 body，不做业务逻辑
│  /webhook/fab_admin    │
└───────┬───────────────┘
        │  HTTP POST（X-API-Key 鉴权）
        ▼
┌───────────────────────┐
│  DB Proxy (8001)       │  Python FastAPI，Thick mode 连 Oracle 11g
│  /query/fab_query      │  ← _dispatch() 按 action 路由
│  /query/fab_admin      │
│  /query/F1~F10（保留）  │  ← 旧端点未删，可直连回退
└───────┬───────────────┘
        │  SQL
        ▼
    Oracle 11g DB
```

### action 分发全表

| 工具 | action | 用途 | 必填参数 |
| --- | --- | --- | --- |
| `fab_query` | `machine_status` | 机台状态/运行模式/全厂概览 | 无（machine_id 可空=全厂） |
| `fab_query` | `lot_info` | Lot 位置与进度 | lot_id 或 machine_id 至少一个 |
| `fab_query` | `machine_alarms` | 报警统计 | 无（可加 machine_id/severity/days） |
| `fab_query` | `event_timeline` | 事件时间线/温度趋势 | machine_id |
| `fab_query` | `yield_stats` | 产量/晶圆统计 | machine_id |
| `fab_query` | `recipe_info` | 工艺配方 | machine_id |
| `fab_query` | `list_capabilities` | 功能清单 | 无 |
| `fab_admin` | `mes_lot_info` | MES Lot 信息 | lot_id |
| `fab_admin` | `export_alarm_report` | 导出报警报表 | days（machine_id 可空） |
| `fab_admin` | `generate_work_order` | 生成故障工单（**写操作**） | machine_id、fault_type |

***

## 故障排查速查表

### 本版新增高频问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| DB Proxy 报"缺少 action 参数" | n8n 的 Body 表达式改坏了，没透传 | 检查 Query DB Proxy 节点 Body 是否为 `={{ JSON.stringify($json.body \|\| {}) }}` |
| DB Proxy 报"未知 action「xxx」" | Dify 提示词还是旧的，模型编了个工具名当 action | 重新导入 .yml（第 4 步） |
| Dify 里工具还是 10 个 | 旧的 Custom Tool 没删 | 工具页面删掉旧的，重建（第 5.1 步） |
| Dify 保存 Schema 报错 | `servers.url` 还是 `{{n8n_base_url}}` 占位符 | 改成真实 n8n 地址（第 5.2 步） |
| 调 `/query/fab_query` 404 | DB Proxy 没重启，还是旧代码 | 重启 DB Proxy（第 1.4 步） |
| 自测脚本 `unrecognized arguments: --merged` | 跑成 `test_n8n_integration.py` 了 | 改用 `python tests\test_n8n_f1_f10.py --merged` |
| AI 调工具时不传 action | 提示词没更新，或模型不是 function_call 模式 | 确认提示词已更新；Agent 策略选 Function Calling |

### 通用问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| DB Proxy /health 返回 503 | Oracle Client 未安装或路径错 | 检查 `ORACLE_CLIENT_DIR` 指向 oci.dll 所在目录 |
| DB Proxy 报 ORA-03134 | 11g 不支持 Thin 模式 | 确认 `ORACLE_DSN_TYPE=sid`，安装 Oracle Client |
| n8n 调 DB Proxy 报 401 | API Key 不匹配 | 核对 X-API-Key 头与 `DB_PROXY_API_KEY` |
| n8n 调 DB Proxy 超时 | Oracle 查询慢或网络问题 | 查 DB Proxy 日志，确认 SQL 能执行 |
| Dify 调 n8n 404 | 工作流未激活，或用了 `/webhook-test/` | 打开 Active；正式调用用 `/webhook/` |
| Dify 导入 .yml 报格式错 | 旧文件第 12 行 YAML 语法错误 | 用本版修好的文件 |
| 回答里有 SQL 代码 | 提示词未生效 | 检查 pre_prompt 是否完整保存 |
| 下载链接显示成 `[⬇️](http://...)` | 前端没重新构建 | `cd frontend && npm run build` |
| 跳转按钮点了没反应 | 前端没重新构建，或回答缺 `jump_machine_id` | 重新构建；检查 `<FABTWIN>` 块内容 |

***

## 回退方案

新版有问题要退回 10 工具版：

1. n8n：停用 `FAB_QUERY_merged` / `FAB_ADMIN_merged`，重新激活 F1~F10
2. Dify：Custom Tool 的 Schema 换回旧版 OpenAPI（10 个 path），提示词换回旧版
3. DB Proxy **不用动**——旧的 10 个端点一直保留着

***

## 文件清单

| 文件 | 用途 |
| --- | --- |
| `services/db_proxy/main.py` | DB Proxy 服务（10 个原端点 + 2 个分发端点） |
| `services/db_proxy/requirements.txt` | Python 依赖 |
| `services/db_proxy/.env.example` | 配置模板 |
| `services/db_proxy/start.bat` | Windows 启动脚本 |
| `docs/integration/n8n/FAB_QUERY_merged.json` | **n8n 合并工作流（读类）** |
| `docs/integration/n8n/FAB_ADMIN_merged.json` | **n8n 合并工作流（管理类）** |
| `docs/integration/n8n/F1~F10*.json` | 旧版 10 个工作流（保留备用） |
| `docs/integration/n8n/backup_oracle_direct/` | 更早的 Oracle 直连版备份 |
| `docs/integration/dify/fabtwin-ai-assistant.dsl.yml` | **Dify 应用模板（通用版）** |
| `docs/integration/dify/fabtwin-ai-assistant-OXE.dsl.yml` | Dify 应用模板（OXE 专用版） |
| `docs/integration/dify/fabtwin-tools-openapi.yaml` | **OpenAPI 工具定义（2 工具版）** |
| `docs/integration/dify/eap-log-query.dsl.yml` | EAP LOG 捞取应用（独立） |
| `tests/test_n8n_f1_f10.py` | **F1~F10 分层自测脚本（支持 --merged）** |
| `tests/test_n8n_integration.py` | 旧的 5 业务工作流端到端测试 |

***

## 安全提醒

`DB_PROXY_API_KEY` 目前是默认值 `fabtwin-proxy-2026`，明文写在本文档、
12 个 n8n JSON 和 `.env.example` 里，且已进入 git 历史。

正式上线前建议：

1. 改成随机强口令
2. n8n 里改用 Credentials 存储，不要硬编码在 JSON
3. DB Proxy 只监听内网网段，不要暴露到公网
