# FabTwin AI 功能完整说明

> 版本：v2.0（整合版）
> 更新时间：2026-07-29
> 替代文档：AI_Architecture_Design.md / AI_Phase1_Tech_Detail.md / AI_INTEGRATION_GUIDE.md

---

## 一、AI 能做什么（用户视角）

### 1.1 已实现功能

| 功能 | 示例问题 | 数据来源 |
|------|----------|----------|
| 机台状态查询 | "PODOPENER-1状态" / "全厂机台状态" | Oracle DT_EVENT_RAW |
| Lot 追溯 | "查PC00H.29的lot信息" | MES(通过N8N MCP) + 设备事件 |
| MES Lot 详情 | "PC00H.29是什么产品" | MES(通过N8N MCP) |
| 告警查询 | "今日报警统计" | Oracle DT_EVENT_RAW |
| 事件时间线 | "PODOPENER-1事件" | Oracle DT_EVENT_RAW |
| 产量统计 | "今天run了多少lot" | Oracle DT_EVENT_RAW |
| 工艺配方 | "PODOPENER-1的recipe" | 当前无数据，返回提示 |
| 跳转回放 | 点击AI回答中的表格行 | 前端路由跳转 |

### 1.2 两种 AI 模式

| 模式 | 说明 | 优势 | 劣势 |
|------|------|------|------|
| **本地规则引擎** | 关键词匹配 → 调用工具 → 直接返回 | 零延迟、零成本、无需API | 无自然语言理解能力，问题格式必须包含关键词 |
| **第三方LLM** | 用户问题 → LLM理解意图 → Function Calling调用工具 → LLM生成回答 | 自然语言理解强、回答更灵活 | 有延迟、有成本、依赖外部API可用性 |

### 1.3 交互闭环

```
用户提问 → AI回答（含表格数据）→ 点击表格行 → 跳转机台详情页 + 自动定位回放时间点
```

---

## 二、整体架构

### 2.1 请求链路

```
前端 AIFloatingBall.vue
  │
  ▼ POST /api/ai/chat {question, session_id, config_id}
后端 routers/ai.py
  │
  ▼ ai_middleware.chat()
AIMiddleware（编排器）
  │
  ├─ 路由决策：provider == "local" → 本地规则引擎
  │              provider in {"openai","zhipu","custom",...} → LLM调用
  │
  ├─ 本地规则引擎：关键词匹配 → 调用 ai_tools 工具 → 返回结果
  │
  └─ LLM 调用：发送问题 + 工具定义 → LLM 返回 tool_calls
                → 执行工具（ai_tools）→ 结果回传 LLM → LLM 生成自然语言回答
```

### 2.2 代码文件职责

| 文件 | 职责 | 行数(约) |
|------|------|----------|
| `routers/ai.py` | API 路由层，接收请求，返回响应 | 300 |
| `services/ai_middleware.py` | **核心编排器**：路由决策、LLM调用、本地规则引擎、会话管理、日志记录 | 1400 |
| `services/ai_tools.py` | **工具实现层**：6个工具函数 + 工具定义 + MES MCP调用 | 950 |
| `services/mcp_client.py` | MCP HTTP 客户端（调N8N） | 150 |
| `services/mcp_registry.py` | MCP 工具注册表 | 60 |
| `models.py` | AIUsageLog / AIProviderConfig / AIConfig 数据模型 | 50 |

### 2.3 数据库表

| 表名 | 用途 |
|------|------|
| `AI_CONFIGS` | 键值对配置（Dify/N8N/MCP 开关和参数） |
| `AI_PROVIDER_CONFIGS` | LLM 多配置管理（provider/url/key/model） |
| `AI_USAGE_LOGS` | 调用日志（token消耗、工具调用、执行日志、错误信息） |
| `DT_EVENT_RAW` | 设备事件流（VFEI事件，AI主要数据源） |

---

## 三、本地规则引擎 vs 第三方 AI

### 3.1 本地规则引擎

**工作流程**：
```
用户问题 → 转小写 → 关键词匹配 → 提取实体(机台ID/Lot ID) → 调用对应工具 → 返回结果
```

**关键词路由表**：

| 关键词 | 调用工具 | 备注 |
|--------|----------|------|
| lot/批次 | get_lot_info | 需要提取 Lot ID |
| 报警/告警/alarm | get_machine_alarms | |
| 温度/趋势/事件/时间线 | get_event_timeline | |
| 产量/晶圆/yield | get_yield_stats | |
| 工艺/配方/recipe | get_recipe_info | 当前无真实数据 |
| (默认) | get_machine_status | |

**实体提取正则**：
- 机台 ID：`PODOPENER-1`、`OXE-01` → `[A-Z]{2,}[-_]?\d+`
- Lot ID：`NT938`、`PC00H.29` → `[A-Z]+\d+(\.\d+)?`

### 3.2 第三方 LLM（OpenAI 兼容）

**工作流程**：
```
用户问题 + System Prompt + 工具定义
  → LLM 返回 tool_calls（选择工具 + 提取参数）
  → 执行工具
  → 工具结果回传 LLM
  → LLM 生成自然语言回答
```

**支持的 Provider**：智谱GLM、OpenAI、DeepSeek、通义千问、自定义兼容接口

**工具定义**（Function Calling）：

| 工具名 | 参数 | 说明 |
|--------|------|------|
| get_machine_status | machine_id? | 机台状态 |
| get_machine_alarms | machine_id? | 告警记录 |
| get_event_timeline | machine_id? | 事件时间线 |
| get_yield_stats | machine_id? | 产量统计 |
| get_lot_info | lot_id?, machine_id? | Lot 追溯(MES+设备) |
| get_mes_lot_info | lot | MES Lot 详情 |
| get_recipe_info | machine_id? | 工艺配方 |

### 3.3 MES 数据获取（N8N MCP）

```
get_lot_info / get_mes_lot_info
  → mcp_client.call_tool("execute_workflow", {...})
  → N8N MCP Server (http://10.30.116.137/mcp-server/http)
  → N8N 工作流执行 MES SQL 查询
  → 返回 Lot 的 product/process/route/step/status/quantity 等
```

配置存储在 `AI_CONFIGS` 表：
- `mcp_n8n_enabled` - 是否启用
- `mcp_n8n_url` - N8N MCP 地址
- `mcp_n8n_token` - Bearer Token
- `mcp_n8n_timeout` - 超时秒数

---

## 四、当前已知问题

### 4.1 P0：500 错误（datetime 序列化失败）

**位置**：`ai_middleware.py` 第 894 行

```python
# 第885行有 default=str 保护 ✅
tool_content = json.dumps(result, ensure_ascii=False, default=str)
# 第894行缺少 default=str ❌
tool_content += f"\n[META] {json.dumps(extra, ensure_ascii=False)}"
```

`extra` 包含 `jump_timestamp`，来自数据库的 `received_ts_utc`，可能返回 datetime 对象导致序列化失败。

**影响**：LLM 模式下所有有返回数据（含 jump_timestamp）的查询都报 500。

### 4.2 P0：本地规则引擎正则提取失败

**位置**：`ai_middleware.py` 第 704/718/722 行

**问题 A**：`\b` 词边界在中文环境下失效
- Python 3 中 CJK 字符属于 `\w`，所以 `"PODOPENER-1狀態"` 中 "1" 和 "狀" 之间没有词边界
- 导致 `PODOPENER-1狀態` → machine_id=null

**问题 B**：Lot ID 正则不匹配实际格式
- 正则 `[A-Z]+\d+` 期望"纯字母+纯数字"（如 NT938）
- 实际 Lot ID：`V3WTG`、`PN70C`、`V42FQ` 是字母数字混合，不匹配

**影响**：本地规则引擎模式下，机台和 Lot 查询全部退化为全厂概览。

### 4.3 P1：LLM 失败后回退本地规则，本地规则也失败

连锁反应：LLM 正确提取了 lot_id → 工具返回数据 → datetime 序列化失败 → 回退本地规则 → 本地规则提取不到 lot_id → 返回错误答案。

### 4.4 P1：使用统计日志记录不稳定

**已修复**：AI_USAGE_LOGS 表已创建，新增 tool_calls/execution_log 字段。
**遗留**：ORA-24816 CLOB 字段顺序问题已修复，待部署验证。

---

## 五、使用方式

### 5.1 配置入口

**前端**：AI 配置管理面板（AIConfigPanel.vue）
- LLM 配置 Tab：添加/编辑/删除 Provider 配置，设置默认
- Dify/N8N Tab：MCP Server 配置（URL/Token/开关）

### 5.2 切换 AI 模式

- **用本地规则引擎**：在 AI 配置面板设置 "本地规则引擎" 为默认
- **用第三方 AI**：添加 Provider 配置（填入 base_url / api_key / model），设为默认
- **前端悬浮球**：可通过下拉菜单切换 Provider

### 5.3 使用统计

- **API**：`GET /api/ai/usage/logs` → 返回每条调用日志（含 tool_calls、execution_log）
- **API**：`GET /api/ai/usage/stats` → 返回聚合统计（按 provider/按天）
- **前端**：AI 配置面板 Token 使用统计 Tab

---

## 六、代码是否冗余

### 6.1 冗余点

| 问题 | 说明 |
|------|------|
| `ai_mcp.py` 未使用 | 存在但未被引用 |
| `mcp_registry.py` 实际未使用 | 工具注册表定义了，但代码中直接用 TOOL_DEFINITIONS |
| Dify 集成代码过重 | `chat()` 方法中有 dify/hybrid 分支，但实际从未启用 |
| `_call_dify` 方法 | 完整的 Dify 调用逻辑，但当前架构中 Dify 不是重点 |
| 旧版 `_extract_lot_id` 正则 | 文档中提到的正则和实际代码不一致 |

### 6.2 可简化方向

1. **删除 `ai_mcp.py`**：未被引用
2. **合并 `mcp_registry.py` 到 `ai_tools.py`**：工具定义已在 TOOL_DEFINITIONS 中
3. **精简 Dify 分支**：当前不用，可保留入口但简化逻辑
4. **统一工具调用记录**：本地规则引擎和 LLM 的工具调用记录格式已统一

---

## 七、后续规划

### 阶段 1（当前）：修复稳定性
- [ ] 修复 datetime 序列化（P0）
- [ ] 修复正则提取（P0）
- [ ] 验证日志记录功能

### 阶段 2：优化体验
- [ ] 优化 System Prompt，减少 LLM 重复工具调用
- [ ] 本地规则引擎增加更多意图识别
- [ ] 前端展示执行日志详情

### 阶段 3：扩展能力
- [ ] 接入更多 N8N MCP 工具（报警详情、工单生成等）
- [ ] Dify RAG 知识库（文档问答）
- [ ] 主动推送（告警自动触发 AI 分析）
