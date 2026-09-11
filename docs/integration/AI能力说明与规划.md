# FabTwin Pro — AI 能力说明与后续规划

> 版本：ver2.10.9 对应盘点（2026-09-11）
> 用途：① 向管理层说明「AI 现在能做什么」；② 明确「run 货历史查询」与「LOG 捞取」两项新能力的落地方案
> 关联文档：`docs/integration/DEPLOY_SOP.md`、`docs/integration/dify_n8n_format_reference.md`、`docs/变更更改版记录.md`

---

## 第一部分　AI 现在能做什么（现状能力清单）

### 1.1 一句话概括

FabTwin Pro 的 AI 助手是**接在真实机台事件数据库上的问答入口**。它不是通用聊天机器人，而是把「查机台状态、查告警、查批次、查腔体、查产出」这些原本要开报表、翻 LOG、问工程师的动作，变成一句自然语言提问，并且回答里带**可点击跳转的时间点**，能直接把 3D 数字孪生画面拉回到那一刻。

### 1.2 用户能在哪里用

| 入口 | 位置 | 特点 |
|---|---|---|
| 全局 AI 悬浮球 | 任意页面右下角 | 可跨机台提问，可切换不同 AI 模型 |
| 机台详情页「AI」页签 | 机台详情页右侧 | 自动带上当前机台上下文，无需重复说机台号 |
| Dify 独立对话 | Dify 平台侧 | 走 Dify Agent 编排，可挂更复杂的多轮流程 |

### 1.3 现有 10 项查询能力（业务语言版）

> 「10 项能力」说的是**业务能力**，不等于「10 个 Dify 工具」。
> 2026-09-11 起这 10 项能力在 Dify 侧已收敛成 **2 个工具**（读类 `fab_query` + 管理类 `fab_admin`），
> 靠一个 `action` 参数区分具体查哪一项，详见 1.7 节。能力本身一项没少。

| # | 能力 | 用户可以这样问 | 回答里包含 |
|---|---|---|---|
| 1 | **机台即时状态** | 「OXE-51 现在什么状态？」「哪几台现在是 Down？」 | 状态、当前事件、最后更新时间、是否在线 |
| 2 | **告警查询** | 「PODOPENER-1 最近有什么告警？」「今天全厂告警有哪些？」 | 告警码、告警文本、发生时间、可跳转时间点 |
| 3 | **事件时间线** | 「OXE-1 这段时间发生了什么？」 | 按时间倒序的事件流水，可点击回放 |
| 4 | **产出统计** | 「OXE-51 今天跑了多少片？」「产出情况怎么样？」 | 批次数、片数、完成时间分布 |
| 5 | **MES 批次信息** | 「LOT V394K 的 MES 资料？」 | 经 n8n MCP 打到 MES，返回工单/产品/站点信息 |
| 6 | **批次综合信息** | 「V394K 这批货在哪台机、跑到哪一步？」 | MES 资料 + 机台 VFEI 事件融合 |
| 7 | **配方信息** | 「OXE-1 现在用的什么 Recipe？」 | 配方名、参数、生效机台 |
| 8 | **晶圆流向（OXE 专用）** | 「这批 25 片走到第几片了？」 | 每片 slot 的进出腔时间与当前位置 |
| 9 | **腔体状态（OXE 专用）** | 「OXE-51 哪个腔体在忙？」 | 各 chamber 的占用/空闲/片号 |
| 10 | **OXE 批次汇总（OXE 专用）** | 「OXE-51 今天各批次跑得怎么样？」 | 按 LOT 汇总的开始/结束/片数/耗时 |

### 1.4 回答的统一形态

每次回答后端都返回同一套结构，前端据此渲染：

```
answer           自然语言回答
sql              本次查询实际执行的 SQL（可审计、可复核）
table_data       结构化表格 { headers, rows }，前端渲染成表
jump_timestamp   可点击的时间点 → 点了直接把回放拉到那一刻
jump_machine_id  可点击的机台 → 点了直接跳该机台详情页
machine_online   机台在线与否
```

**这一点是与普通 AI 问答最大的差别**：AI 的回答不是终点，是导航起点——问完「什么时候出的告警」，点一下就跳到那个时刻的 3D 动画现场。

### 1.5 底层是怎么保证「答得准」的

AI 不允许自由生成 SQL，而是走**预定义工具（Function Calling）**：模型只负责「听懂用户要什么、选哪个工具、填什么参数」，实际取数由后端写死的 10 个工具函数完成，SQL 固定、参数受控。

> 收敛之后模型多做了一步选择：先选 `fab_query` 还是 `fab_admin`，再在 `action` 里选具体哪一项。
> 后端那 10 个函数原封不动，只是入口从 10 个变成 2 个。

四级路由，按优先级自动选择由谁来答：

```
① 机台专属 Dify 配置   （某台机器单独挂了 Agent，就用它）
        ↓ 未配置
② 全局 Dify 配置       （统一 Agent）
        ↓ 未配置
③ 默认大模型配置       （OpenAI / 智谱 / DeepSeek / 通义 / 自建）
        ↓ 未配置
④ 本地规则引擎         （不依赖外网，关键词匹配直查 Oracle，断网可用）
```

第 ④ 层是兜底保障：**即使外网大模型全部不可用，常见问题仍可回答**。

### 1.6 已具备的管理能力

- 多模型配置管理（新增/切换/连通性测试）
- 按机台绑定不同 Dify Agent
- Token 用量统计与调用日志（谁问了什么、花了多少 token、耗时多少）
- 会话历史管理
- 语音提问（语音转文字后进入同一链路）
- MCP 协议对接（当前接入 MES 查询）

### 1.7 工具收敛：Dify 工具位从 10 个降到 2 个

**遇到的问题**

Dify 是按 OpenAPI 文件里的 **path 数量**来注册工具的。原来 F1~F10 每个能力一个 path，
导入后一次性占掉 Agent 的 10 个工具位，导致 LOG 捞取等其他工具**再也挂不上去**。
注意这不是「n8n 有 10 个工作流」造成的，而是「OpenAPI 声明了 10 个 path」造成的——
所以要改的是 OpenAPI 的形状，不是砍掉任何一项能力。

**做法：单 path + action 分发**

OpenAPI 只保留 2 个 path，具体查什么放进 `action` 参数：

| Dify 工具 | 覆盖能力 | action 取值 |
|---|---|---|
| `fab_query`（读类） | F1~F6、F10 | `machine_status`、`lot_info`、`machine_alarms`、`event_timeline`、`yield_stats`、`recipe_info`、`list_capabilities` |
| `fab_admin`（管理类） | F7、F8、F9 | `mes_lot_info`、`export_alarm_report`、`generate_work_order` |

**为什么按读/写拆成 2 个而不是压成 1 个**

- 读类是安全的高频操作，管理类会产生工单、导出报表等副作用，分开便于后续单独做权限控制
- 语义边界清晰，模型选参更稳：先判断「是查还是办」，再在小范围内挑 action，比在 10 个里直接挑准确率高
- 真压成 1 个工具、10 个 action 平铺，模型容易在相近 action 之间摇摆（比如 `lot_info` 与 `mes_lot_info`）

**后端改了什么**

`db_proxy` 新增 `POST /query/fab_query`、`POST /query/fab_admin` 两个分发端点，
读出 `action` 后转交给原来那 10 个 handler，**业务逻辑一行没动**。
原来的 10 个端点也**全部保留**，作用有二：一是出问题可随时回退，二是自测脚本拿它们当对照基准。

**结果**

Dify 工具位从 10 个降到 2 个，腾出 8 个位置给 LOG 捞取等新工具；
以后再加能力（比如下面第二部分的 run 货历史），**不再新增工具位**。

---

## 第二部分　新能力一：AI 查询 run 货历史

### 2.1 需求理解

老板要的「run 货历史」= 对某台机台或某个批次，回答「**这段时间跑了哪些货、每批什么时候进、什么时候出、跑了多久、多少片、有没有异常**」。

现状差距：
- 数据本身**已经在库里**（`DT_EVENT_RAW` 的 LotStart / LotEnd / WAFERUNLOADED 等事件）
- 前端回放页的 LOT 列表已经在做类似聚合，但**是前端 JS 派生的**，AI 侧拿不到
- 现有 `get_oxe_lot_summary` 只覆盖 OXE 机型，且限定单日

### 2.2 落地方案

**Step 1｜后端新增统一取数函数**

在 `backend/services/ai_tools.py` 新增：

```
get_lot_run_history(db, machine_id=None, lot_id=None,
                    start_time=None, end_time=None, limit=50)
```

- 支持三种问法：按机台查、按批次查、按时间段查
- 不限机型（PODOPENER / OXE 通用），内部按机型选事件名集合
- 把现在散在前端的 LOT 聚合逻辑**下沉到后端**，前端回放页与 AI 共用同一份口径，避免两处算出两个数

输出字段（表格列）：

| lot_id | machine_id | 开始时间 | 结束时间 | 耗时 | 片数 | 结束状态 | 期间告警数 |

**Step 2｜注册为 AI 工具**

- 加入 `TOOL_DEFINITIONS`（第 11 项），描述写清「查询批次生产履历/run 货历史」
- 加入 `TOOL_HANDLERS` 映射
- 同步加入本地规则引擎关键词：`run货`、`跑货`、`批次历史`、`生产履历`、`lot history`

**Step 3｜对外链路同步**

| 层 | 动作 |
|---|---|
| db_proxy | 新增 `POST /query/lot_run_history`（编号 F11），复用 `ok()/fail()` 统一响应；同时在 `_QUERY_ACTIONS` 字典里加一行 `"lot_run_history": f11_lot_run_history` |
| n8n | **无需改动**。`fab_query` 工作流是整体透传 body 的，新 action 自动走通 |
| Dify | `fabtwin-tools-openapi.yaml` 的 `action` enum 加一个值 `lot_run_history`，重新导入即可，**不占新的工具位** |

> 这就是 1.7 节工具收敛带来的直接收益：新增能力从「改三处、多占一个工具位」
> 变成「改两处、工具位不变」。

**Step 4｜前端**

- 回放页 LOT 聚合改为读后端返回（去掉前端 computed 派生）
- AI 回答中的 lot_id 做成可点击 → 点击后回放时间轴自动框到该批次区间

### 2.3 交付后用户可以问什么

- 「OXE-51 今天跑了哪几批货？」
- 「V394K 这批什么时候开始、什么时候结束的？」
- 「PODOPENER-1 上周跑货记录给我」
- 「最近哪批货跑得最慢？」

### 2.4 「从 Dify 直接问回」是怎么实现的（原 P3 的完整说明）

> 上一版把这件事拆成 P2/P3 两阶段，只写了「新增 F11 + n8n 工作流 + OpenAPI 条目」，
> 没讲清楚**一句话是怎么从 Dify 走到 Oracle 再走回来的**。这里补全。

**先厘清一个概念：Dify 自己不会查数据库。**

Dify 里的大模型只会做两件事：① 读懂你的问题 ② 决定「该调哪个工具、传什么参数」。
真正去 Oracle 取数的是我们自己的服务。所以「从 Dify 直接问回」的本质是：
**给 Dify 挂一个它能调用的 HTTP 工具，这个工具背后连着数据库。**

**完整链路（7 步）**

```
你在 Dify 对话框输入：「OXE-51 今天跑了哪几批货？」
        │
   ①    ▼  Dify Agent 的大模型读题
        判断意图 = 查 run 货历史
        决定调用工具 fab_query，action 选 lot_run_history
        抽出参数 { action: "lot_run_history", machine_id: "OXE-51", time_range: "today" }
        │
   ②    ▼  Dify 按 OpenAPI 定义发出 HTTP 请求
        POST http://10.30.116.151:5678/webhook/fab_query
        │
   ③    ▼  n8n 收到（纯转发，不含业务逻辑）
        整体透传 body，转发到 POST http://10.30.116.150:8001/query/fab_query
        带上 X-API-Key: fabtwin-proxy-2026
        │
   ④    ▼  db_proxy（Python FastAPI）
        按 action 分发到 f11 handler
        执行 SQL：从 DT_EVENT_RAW 聚合 LotStart / LotEnd 事件
        │
   ⑤    ▼  Oracle 11g 返回原始行
        │
   ⑥    ▼  db_proxy 组装成统一契约
        { ok, answer, table_data{headers,rows}, jump_timestamp, jump_machine_id, sources }
        │
   ⑦    ▼  原路返回 n8n → Dify
        大模型拿到 JSON，用自然语言把 answer + 表格讲给你听
```

**关键结论：要让 Dify 能「直接问回」，必须补齐两个环节，缺一不可**

| # | 环节 | 做什么 | 不做会怎样 |
|---|---|---|---|
| 1 | db_proxy 加 `POST /query/lot_run_history` + `_QUERY_ACTIONS` 注册 | 真正的取数逻辑（SQL 聚合），并让 `fab_query` 认得这个 action | 没人查库；或 action 认不出来，db_proxy 回「未知 action」，断在第 ④ 步 |
| 2 | `fabtwin-tools-openapi.yaml` 的 `action` enum 加值，Dify 重新导入 | 让大模型「知道有这个 action 可选」 | 模型压根不会去调它，断在第 ① 步 |

> 收敛之前这里是**三**个环节，中间那步「n8n 新建 F11 工作流」现在没有了——
> `fab_query` 工作流整体透传 body，加多少 action 都不用碰 n8n。

其中第 2 条最容易被忽略：**后端做好了，但没在 OpenAPI 里声明，Dify 就当它不存在**，
表现为「AI 答非所问 / 说自己查不到」，很容易被误判成后端有 bug。

**为什么中间要夹一个 n8n？能不能去掉？**

可以去掉。n8n 在这条链路里是纯转发（Webhook → HTTP Request → Respond，零业务逻辑）。
两种接法对比：

| 方案 | Dify 里 servers.url 填 | 优点 | 缺点 |
|---|---|---|---|
| A. 经 n8n（当前） | `http://10.30.116.151:5678/webhook` | 有可视化执行日志，排障快 | 多一跳，多一个故障点 |
| B. Dify 直连 db_proxy | `http://10.30.116.150:8001` + path 改 `/query/xxx` + Header 加 `X-API-Key` | 少一跳，更稳 | 出问题只能看服务端日志 |

**建议先 A 后 B**：现阶段联调频繁，n8n 的执行日志能省大量排查时间；
等 F1~F11 全部稳定跑通，再切 B 去掉这一跳。

**F11 的请求/响应样例（照此实现即可）**

请求：
```json
{ "action": "lot_run_history", "machine_id": "OXE-51", "time_range": "today" }
```

> 注意多了 `action` 参数——这是工具收敛后的统一格式，不再面向 `/query/lot_run_history` 这个 path 发请求。

响应：
```json
{
  "ok": true,
  "answer": "OXE-51 今天共跑 3 批货，其中 1 批异常结束。",
  "table_data": {
    "headers": ["Lot ID","机台","开始时间","结束时间","耗时","片数","结束状态","期间告警"],
    "rows": [["V394K","OXE-51","08:12:03","09:40:55","1h28m","25","正常","0"]]
  },
  "jump_timestamp": "2026-09-11 08:12:03",
  "jump_machine_id": "OXE-51",
  "sources": [{ "type": "db_proxy" }]
}
```

**验收方式**：在 Dify 对话框直接问「OXE-51 今天跑了哪几批货」，
能返回上面这张表 = 「从 Dify 直接问回」达成。
过程中若失败，用 `tests/test_n8n_f1_f10.py` 分层定位是哪一跳断的
（测合并版加 `--merged`：`python tests\test_n8n_f1_f10.py --merged`）。

---

## 第三部分　新能力二：LOG 捞取

> 本节已从「等接口」状态转为「已落地」状态。原先列的 5 条阻塞项（LOG 来源、认证方式、字段结构、行数上限、工具 schema）**已全部解除**，下面写的是实际接口与已交付的实现。

### 3.1 LOG 从哪来（已明确）

LOG 不在 Oracle 里，来自独立的 **EAP 日志服务**，地址 `http://10.30.8.243:8080`，用 Header `X-API-Key` 鉴权。
它对外只有 4 个端点，理解这 4 个就理解了整条 LOG 链路：

| 端点 | 方法 | 作用 | 关键入参 |
|---|---|---|---|
| `/api/ext/search` | GET | 查某机台某天有哪些日志文件 | `machine`、`date`、`message_type` |
| `/api/ext/fetch` | POST | 抓取**单个**文件，返回下载路径 | `machine`、`date`、`filename` |
| `/api/ext/bundle_batch_sync` | POST | **跨日期批量**打包成一个 zip | `machine`、`start_date`、`end_date` |
| `/api/ext/download` | GET | 按 `path` 参数真正下载文件 | `path`、`api_key` |

注意 `/api/ext/download` 的 `api_key` 是**放在 query string 里**的，不是 Header。
这一点和前 3 个端点不一样，是后面那个 SSRF 报错的直接诱因。

### 3.2 Dify 侧实现（本轮已交付）

工作流文件：`docs/integration/dify/eap-log-query.dsl.yml`，19 节点 / 18 边，两条主干：

```
开始 → 参数校验 → 单批分流
                    ├─ 单日 → search → 解析列表 → fetch  → 提取链接 → 返回 📄
                    └─ 跨日 → bundle_batch_sync → 提取链接 → 返回 📦
```

**关键改动（对照上一版）**

| # | 改了什么 | 为什么 |
|---|---|---|
| 1 | Header 从单引号字符串改成 YAML 块标量 `\|-` | 原写法里的 `\n` 不会被转义，两个 Header 粘成一行，`X-API-Key` 实际没送出去 → 401 |
| 2 | 删掉两个 base64 编码节点 | Dify 代码节点有 `CODE_MAX_STRING_LENGTH`（默认 80000 字符）上限，base64 放大 4/3，约 58KB 的日志文件就会炸 |
| 3 | 下载链接**只出图标不出文字** | 按你的要求：单文件用 `📄`，批量包用 `📦`，链接本身收进 `[⬇️](url)` |
| 4 | 提取链接的两个代码节点补 `api_key` + `/api/` 前缀守卫 + URL 归一化 | 见 3.3 |

**交付形态**：按你选的「只返回下载链接」，不把文件内容塞进对话框。

### 3.3 那个 SSRF 报错到底是什么（你问的第 3 点）

你贴的现象是：

```
单文件  /api/ext/download?path=OXE-51/2026-09-05/OXE-51_Vfei.20260905.001.log&api_key=...   ✅ 正常
批量    /api/ext/download?path=_bundles/BATCH_OXE-51_2026-09-05_to_2026-09-08_178908...      ❌ SSRF blocked
```

**先说结论：这不是真的 SSRF，是 Dify 把「上游返回非 2xx」误报成了 SSRF。**

Dify 1.15+ 的出站 HTTP 走 squid 代理。代理层拿到 401 / 403 / 407 这类响应时，
`ssrf_proxy.py` 会统一包装成 `ToolSSRFError`，抛出那句「may point to a private or local network address」。
所以看到 SSRF 别先怀疑网络，**先怀疑鉴权和 URL 本身**。

为什么单文件行、批量不行，差异在这三处：

| 差异点 | 单文件链接 | 批量链接 | 后果 |
|---|---|---|---|
| `api_key` | `search`/`fetch` 返回的 URL 自带 `&api_key=` | `bundle_batch_sync` 返回的 URL **不带** `api_key` | 批量请求无鉴权 → 401 → 被包装成 SSRF |
| path 形态 | `OXE-51/2026-09-05/xxx.log`，纯相对路径 | `_bundles/BATCH_...`，下划线开头 | 部分反代对 `_` 前缀路径有额外规则 |
| URL 长度 | 短 | 批量文件名含起止日期+时间戳，很长（你贴的被截断成 `...178908…`） | 超长 URL 可能被代理截断 |

**修复做法**（已写进 1008 / 1022 两个代码节点）：

```python
if not download_url.startswith('/api/'):      # 守卫：不是合法 API 路径就判定失败
    return {'has_files': 'NO', 'download_url': ''}
if 'api_key=' not in download_url:            # 补鉴权：批量链接缺什么补什么
    download_url += ('&' if '?' in download_url else '?') + 'api_key=' + API_KEY
full = BASE + download_url                    # 归一化：统一拼绝对地址，避免相对路径歧义
```

> 如果补了 `api_key` 仍报 SSRF，说明是真的网络层问题，
> 这时用 `curl -v "http://10.30.8.243:8080/api/ext/download?path=...&api_key=..."`
> 在 **Dify 容器内部**跑一次即可区分：容器内能通 = Dify 配置问题，容器内不通 = 网络/防火墙问题。

### 3.4 与 FabTwin 后端的衔接

Dify Agent 的 system prompt 里约定输出 `<FABTWIN>{...}</FABTWIN>` 结构化块，
后端 `ai_middleware.py`（L1475 附近）现有正则可直接解析，**这部分不需要改代码**。

若后续要让 FabTwin 前端也能直接捞 LOG（不经 Dify），再补 db_proxy 的 `POST /query/fetch_log`（编号 F12）即可，
入参与 `/api/ext/search` 对齐，返回沿用统一契约的 `ok()` 结构。这一步目前**不是必需的**。

---

## 第四部分　推进计划

| 阶段 | 内容 | 状态 / 依赖 |
|---|---|---|
| P0（已完成） | DB 备份/恢复机制、三台机台今日演示数据、详情页卡顿优化复验 | 已完成 |
| P1（已完成） | 本文档「第一部分」作为向老板汇报的 AI 能力说明 | 已交付内容，可按需整理成 PPT |
| P1.5（已完成） | Dify 工具收敛：10 个工具位 → 2 个（`fab_query` / `fab_admin`），腾出 8 个位置 | 见 1.7 节。待现场用 `--merged` 自测验证 |
| P2 | `get_lot_run_history` 后端实现 + AI 工具注册 + 本地规则关键词（完整方案见 2.4 节） | 需实现 db_proxy F11 + `_QUERY_ACTIONS` 加一行 + OpenAPI enum 加一个值；**n8n 无需改动**，无外部依赖 |
| P3 | 前端 LOT 聚合下沉、AI 回答 lot 可点击跳转 | 依赖 P2 完成后端就绪 |
| P4（原 LOG 捞取） | LOG 捞取流程已在 Dify 侧交付（工作流 yml + 图标式下载），FabTwin 端如需集成再加 F12 | 阻塞已解除，真实 EAP 接口已明确（见第三部分） |

---

## 第五部分　盘点中发现的既有问题（建议排期修复）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | `ai_mcp.py` 已成死代码，但 `main.py` 仍 import | 维护误导 | 确认无引用后移除 |
| 2 | MCP 注册表只注册 1 个工具，与 `TOOL_DEFINITIONS` 的 10 个并存两套体系 | 概念重复，新人易混 | 统一到一套工具定义 |
| 3 | 前端 MCP 配置绕过 api 封装裸 fetch，且硬编码内网地址 | 换环境要改代码 | 收敛进 `api/index.js` + 配置化 |
| 4 | 悬浮球与机台内嵌两个聊天组件的 jump 契约不一致（一个传对象、一个传裸时间戳） | 跳转行为不统一 | 统一为对象契约 |
| 5 | `get_mes_lot_info` 的 n8n workflow_id 硬编码 | 换 n8n 环境即失效 | 移入 `ai_configs` 配置项 |
| 6 | db_proxy 地址在生成脚本、10 个 n8n JSON、文档三处重复硬编码 | 改地址要改十几处 | 抽成统一配置/环境变量。**已缓解**：现役只剩 2 个合并版 workflow，实际要改的 n8n 侧从 10 处降到 2 处 |

---

## 附：技术架构速览（供技术评审）

```
前端 AIFloatingBall.vue / AiAssistant.vue
    │  POST /api/ai/chat
    ▼
backend/routers/ai.py（26 个端点，AI 唯一入口）
    │  ai_middleware.chat()
    ▼
backend/services/ai_middleware.py（路由分发中枢）
    ├─ local            → 本地规则引擎 → ai_tools.py 直查 Oracle
    ├─ openai/zhipu/…   → Function Calling → ai_tools.TOOL_HANDLERS
    ├─ dify             → SSE 流式 → Dify Agent → n8n Webhook → db_proxy:8001 → Oracle
    │                      └ Dify 侧只挂 2 个工具：fab_query（读）/ fab_admin（管理）
    │                        n8n 侧对应 2 个 webhook，db_proxy 按 action 分发到原 10 个 handler
    └─ n8n              → 触发工作流（仅 admin）
    另：ai_tools.get_mes_lot_info → mcp_client.py → n8n MCP Server → MES
```

> 说明：db_proxy(8001) 存在的原因是 n8n 的 Oracle 节点要求 12c+，本项目为 Oracle 11g，故用 Python FastAPI 中转。
>
> 补充：db_proxy 同时暴露两套入口——原来的 10 个 `/query/xxx` 端点（保留，供直连测试与回退）
> 和 2 个 `/query/fab_query`、`/query/fab_admin` 分发端点（现役，供 Dify 走）。
> 后者只做「读 action → 找 handler → 转交」，不含任何业务逻辑。
