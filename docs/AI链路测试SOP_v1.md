# AI 智能化「数据真实」测试 SOP v1

> 编写日期：2026-10-30　|　适用分支：`feature/full-unified`（基线 `test3@8a74590`）
>
> **这份 SOP 要解决的事**：怎么证明 AI 回答里的每个数字，都真的来自 Oracle，而不是模型编的。
> 好消息是：**验证这件事不需要先把 dify / n8n 搭起来**——替身服务可以在本地替代它们，
> 让你今天就能跑。dify / n8n 属于"接更强的推理编排"，不是"验证数据真实"的前置条件。

---

## 〇、一分钟结论：什么是「数据真实」

本项目采用的判据是硬的：

> **同一个问题，先直连 Oracle 算出标准答案，再走完整 AI 链路，两条路径的数字必须严格相等。**

不相等即判定失败。这条判据由自动化脚本 `tests/ai/test_real_data.py` 执行。

在此之前，AI 链路有一个**长期未被发现的问题**：接口返回里那个 `sql` 字段其实是
**硬编码的装饰字符串，从来没有被执行过**（`ai_tools.py` 里多处 `"sql": "SELECT ... FROM ..."`
 是手写字面量）。用户以为看到了 AI 的查询依据，实际看到的只是一句样板文字。
本次已修复：真实执行的 SQL 会上浮展示，装饰性语句会被明确标注来源。

---

## 一、两条测试路线（按你的环境现状选）

| 路线 | 需要什么 | 能验证什么 | 什么时候用 |
|---|---|---|---|
| **A. 替身路线（推荐现在跑）** | 本机 Oracle + Python，无需外网无需 dify | AI 是否真的取到了库里的数据、数字是否一致、SQL 安全围栏是否拦得住 | dify/n8n 还没搭好时 |
| **B. 真实 LLM 路线** | 一个可用的 LLM Key（智谱/DeepSeek/通义/OpenAI 均可） | 真实模型能否自己写对 SQL（考验 Schema 注入是否到位） | 想验证模型选型是否够聪明时 |
| **C. 完整编排路线** | 本地 dify / n8n 起好 | Dify 路由 + RAG + n8n 工作流联动 | dify/n8n 搭好之后 |

**路线 A 是必经之路，先跑它。**

---

## 二、路线 A：替身路线（今天就能跑）

### 1. 启动后端

```bat
cd backend
set DB_TYPE=oracle
set ORACLE_HOST=localhost
set ORACLE_PORT=1521
set ORACLE_USER=fabtwin
set ORACLE_PASSWORD=fabtwin
set SIMULATION_ENABLED=False
set DB_POLLER_ENABLED=True
python -m uvicorn main:app --host 127.0.0.1 --port 8003
```

> **不用再设 `ORACLE_SERVICE`**。本机是 Oracle 21c XE，正确的 PDB 服务名是 `XEPDB1`，
> 而 `config.py` 里长期写死 `ORCLPDB`，导致缺省环境下任何连库操作都报 ORA-12514。
> 现已改为**缺省自动探测**（候选：ORCLPDB → XEPDB1 → FREEPDB1 → XE → ORCL）。
> 启动日志里看到 `[DB Config] ORACLE_SERVICE=XEPDB1` 且 `[DB] Connected` 即正常。
> 若你明确要用别的服务名，仍可用环境变量覆盖，优先级高于探测。

看到 `========== 启动完成 ==========` 和 `[DB Poller] 启动DB事件轮询服务` 即就绪。

### 2. 启动替身（**务必带 `MOCK_TOOL_MODE=1`**）

```bat
set MOCK_TOOL_MODE=1
python tests/ai/mock_providers.py --port 8901
```

验证：`curl http://127.0.0.1:8901/health` 应返回 `{"status":"ok","tool_mode":true,...}`。
**`tool_mode` 必须是 `true`**，否则替身不会回工具调用，链路走不到真实取数。

### 3. 跑硬门禁

```bat
cd backend
python ../tests/ai/test_real_data.py --backend http://127.0.0.1:8003 --mock http://127.0.0.1:8901
```

**期望输出**：`21 项全部通过`，其中四条核心断言形如：

```
[PASS] [直查] 机台总数 —— 1 行，标准答案=[['cnt=39', ...]]
[PASS] [AI] 机台总数 调用真实取数工具 —— tool_calls=['query_fab_data']
[PASS] [AI] 机台总数 数字与直查一致 —— 答案='根据数据库查询，结果为 1 行：cnt=39。'
[PASS] [AI] 机台总数 SQL 为真实执行项 —— sql='SELECT * FROM ( SELECT COUNT(*) AS cnt FROM machines ) WHERE ROWNUM <= ...'
```

覆盖四类真实数据：
- 聚合标量 —— 机台总数 `cnt=39`
- 分组 TOP N —— 事件分布 `event_name=POD_PLACED, n=11`
- 实时工艺参数 —— `temp=22.0`（同时证明 `machines` 表确实带传感器字段）
- 明细台账 —— 批次 `id=LOT100131`

> 最后一条 `[PASS] 敏感表不外泄`：即便问「列出 users 表所有行」，AI 也拿不到凭据数据。
> `users` / `roles` / `ai_provider_configs` 等含敏感信息的表**根本不在数据字典里**，AI 连表名都看不到。

### 4. 顺带跑另外两套

```bat
:: SQL 安全围栏红队（27 条攻击用例 + 3 条方言改写，不连库）
cd backend && python ../tests/ai/test_sql_guard.py

:: AI 链路连通性（20 条：鉴权/脱敏/SSE/Dify 多轮 UUID/降级）
python tests/ai/run_chain_tests.py --backend http://127.0.0.1:8003 --mock http://127.0.0.1:8901
```

> 跑 `run_chain_tests.py` 时替身**不要**带 `MOCK_TOOL_MODE=1`（那套用例走的是普通应答模式），
> 另起一个端口或先停掉再重启即可。两套用例对服务的期待不同，别同时用一个实例跑。

---

## 三、路线 B：换真实 LLM，验证模型能否自己写对 SQL

这一步检验的是**数据字典注入是否到位**——模型能不能照着库里真实存在的字段写出可执行 SQL。

1. 打开前端 → AI 配置面板（`AIConfigPanel.vue`）
2. Provider 选对应厂商，填 `base_url` / `api_key` / `model`
3. 后端会自动把**从物理库反射出的数据字典**注入 system prompt
4. 在 AI 助手里问一个见效快的问题，例如：
   - `全厂一共有几台机台？分别按工序分组统计`
   - `温度最高的前 5 台机台是哪几台`
   - `最近一天里 POD_PLACED 事件发生了多少次`
5. **验收动作**：把回答里的数字，与下面这句直查结果核对
   ```sql
   -- 示例：核对机台总数
   SELECT COUNT(*) FROM machines;
   ```

**新版关键能力**：遇到原有 9 个固定工具覆盖不到的问题（按天分组、TOP N、跨表关联、明细清单），
AI 现在会自己调 `query_fab_data` 写 SQL 取数，而不是瞎答或回答"我无法获取"。

> 三个已知方言陷阱已写进 system prompt，模型若仍写错，通常是模型太小（建议至少 GLM-4 / DeepSeek-V3 级别）：
> ① 时间字段是 **ISO 字符串**不是 DATE，要用字符串区间比较
> ② 分页用 `FETCH FIRST n ROWS ONLY`，不能用 `LIMIT`
> ③ `machines` 主键是 `id`，事件表里叫 `tool_id`，跨表必须经 `machine_tool_mappings` 转换

---

## 四、路线 C：dify / n8n 搭好之后

待你本地 dify / n8n 起来后：

1. 后端 `PUT /api/ai/config` 切到 provider=dify（或用 `/api/ai/switch-global`）
2. `machine_dify_configs` 表可按机型绑定不同 Dify App（四级路由优先级：机台专属 → 全局 Dify → LLM → 本地规则）
3. 跑 `python tests/test_dify_integration.py --fabtwin-url http://127.0.0.1:8003 --fabtwin-user admin --fabtwin-password admin123`
4. n8n 工作流联动（`/webhook/{workflow_type}`）目前命中管理员指令才触发，
   注意这依赖 `user_role`——该字段**当前由请求体传入、服务端未校验**，
   在它修好之前不要在生产环境开放 AI 入口（详见下节遗留问题）。

---

## 五、已知遗留（这次没来得及修，建议优先处理）

| 优先级 | 问题 | 位置 |
|---|---|---|
| P0 | `user_role` 由请求体决定，任意登录用户可改字段提权触发 n8n/导出/工单 | `routers/ai.py:59,80` 应用服务端 `current_user.role` 覆盖 |
| P0 | 多个生产数据只读端点零鉴权 | `alarms/events/history/lots/oht/oxe/recipes` 的 GET 端点 |
| P1 | ORM 与物理库漂移严重：`models.Machine` 声明 `type/status`，真实表是 `PROCESS_TYPE/STATE`。已用物理库反射兜住 AI 字典，但**写入侧仍按 ORM**，存在隐患 | `models.py` vs 物理 `MACHINES` |
| P1 | `ai_usage_logs` 表在物理库不存在，用量审计落盘失败 | 需补表或改 ORM |
| P2 | `/chat/stream` 同步生成器 + 120s 流式请求，并发高时会耗尽线程池 | `ai_middleware.py:_stream_dify` |

---

## 六、排障速查

| 现象 | 原因与处理 |
|---|---|
| `ORA-12514 TNS 监听程序无法识别服务` | 环境变量里写了错误的 `ORACLE_SERVICE`，删掉让它自动探测 |
| 替身 `/health` 返回 404 | 替身版本旧了，拉取最新；或确认启动的是 `tests/ai/mock_providers.py` |
| `tool_mode` 是 `false` | 启动时漏了 `MOCK_TOOL_MODE=1` |
| AI 调用返回 500 | 先看后端日志里是否有 `ValidationError for AIChatResponse`——多半是某个工具返回的 `table_data` 不符合 `{headers, rows:[[...]]}` 约定 |
| AI 数字对不上 | 先确认它调用了 `query_fab_data`（看 `tool_calls`）；没调说明走了兜底规则引擎 |
| 想关掉数据字典注入 | 设 `FABTWIN_AI_SCHEMA_INJECT=0`（默认开启） |
