# FabTwin AI 功能架构与开发规划

> 版本：v1.1（第一阶段开发完成）
> 更新时间：2026-07-28
> 状态：第一阶段（MVP）已开发完成，等待部署验证

---

## 一、现状与核心痛点

### 1.1 当前 AI 表现
- **后端架构**：中间件已就绪，支持多 Provider（含 GPT-4o）、Function Calling、会话管理。
- **数据源**：对接了 Oracle 数据库中的 `DT_EVENT_RAW` 表，可解析 VFEI 事件流。
- **痛点**：问答“空壳感”严重，GPT-4o 调用了工具，但返回的数据无法支撑业务场景。

### 1.2 问题根因
1.  **数据源不足**：仅有设备事件（开盖/关盖），缺乏 MES 系统中的**产品信息、工艺步骤、Lot 状态、晶圆数量**。
2.  **工具路由缺失**：没有机制让 AI 自动识别该调哪个 N8N 工具（Tool），导致只能走本地规则或瞎猜。
3.  **交互闭环断裂**：AI 无法直接把查询结果定位到 3D 模型或历史回放时间线。

---

## 二、AI 架构选型与定位

针对你关于 "Dify vs 自建 RAG" 的困惑，这里给出明确的分层设计：

### 2.1 架构分层图

```mermaid
graph TD
    subgraph 前端交互层
        AIFloatingBall[AI 悬浮助手] -->|1. 用户输入| Orchestrator[FabTwin AI 编排器]
        AIFloatingBall -->|5. 点击跳转| Visualization[3D可视化/历史回放]
    end

    subgraph 业务中台层 (FabTwin Backend)
        Orchestrator -->|2. 意图识别 & 工具路由| Router{路由决策}
        Router -->|简单/通用问答| LocalLLM[本地 LLM GPT-4o]
        Router -->|知识/文档问答| Dify[Dify RAG 知识库]
        Router -->|业务数据查询| MCP[MCP 协议适配层]
    end

    subgraph 外部系统
        MCP -->|3. Tool 调用| N8N[N8N 工作流]
        N8N -->|4. SQL/API| MES[(MES 数据库)]
        N8N -->|4. SQL/API| DB[(Oracle/其他)]
        Dify -->|检索增强| VectorDB[(向量库)]
    end
```

### 2.2 角色划分

#### 🟢 FabTwin (主编排者)
-   **定位**：AI 的“大脑”和“神经中枢”。
-   **职责**：
    1.  **意图识别**：判断用户是要查数据、看文档、还是闲聊。
    2.  **工具路由（Tool Routing）**：决定调用哪个 MCP 工具。
    3.  **数据融合**：将 MCP 返回的结构化数据（如 JSON）与 FabTwin 内部数据（如设备坐标）融合。
    4.  **交互控制**：控制最终的“跳转”行为。

#### 🟢 N8N + MCP (数据管道)
-   **定位**：AI 的“手和脚”。
-   **职责**：执行具体的数据获取动作（查库、调 API）。
-   **接入方式**：通过 MCP (Model Context Protocol) 协议暴露为工具（Tools）。

#### 🟢 Dify (可选的知识问答层)
-   **定位**：AI 的“记忆”和“知识参考书”。
-   **职责**：处理非结构化的知识问答（如“新机台怎么接入”、“系统架构是什么”）。
-   **优势**：Dify 自带优秀的 RAG（检索增强生成）功能，直接配置文档即可，无需自己从零搭建 Embedding 模型和向量数据库。
-   **建议**：如果你需要让 AI 回答操作手册类的问题，用 Dify；如果只是问业务数据，完全可以不用 Dify。

### 2.3 结论
-   **不要搞混**：数据查询走 **FabTwin+N8N(MCP)**；文档问答走 **Dify**。
-   **当前优先级**：先把 **MCP 工具链**打通，解决“查不到业务数据”的问题。

---

## 三、核心技术实现：MCP 工具路由

### 3.1 问题：AI 如何知道该调用哪个 N8N Tool？
你提到 N8N 里有很多功能（比如 `MES_LotInfo_Query`、可能还有 `MES_AlarmQuery` 等）。要让 AI 自动调用，需要以下机制：

#### 方案 A：基于 LLM Function Calling 的动态路由（推荐）
1.  **配置工具列表**：在 FabTwin 的 `config.py` 或数据库中，维护一份 MCP 工具清单。
    ```json
    [
      {
        "name": "get_mes_lot_info",
        "description": "查询 MES 系统中的 Lot 详细信息，包括产品、工艺步骤、状态、晶圆数量等",
        "keywords": ["lot", "批次", "产品", "工艺", "状态"],
        "mcp_endpoint": "http://10.30.116.137/mcp-server/http",
        "mcp_tool_name": "MES_LotInfo_Query",
        "params": {"lot": "{query}"}
      },
      {
        "name": "get_mes_alarm_info",
        "description": "查询 MES 系统中的报警记录",
        "keywords": ["报警", "告警", "alarm"],
        "mcp_endpoint": "http://10.30.116.137/mcp-server/http",
        "mcp_tool_name": "MES_AlarmQuery",
        "params": {"alarm_id": "{query}"}
      }
    ]
    ```
2.  **注入 System Prompt**：在调用 GPT-4o 时，把这份清单（特别是 `description`）作为 Tool Definitions 传给 LLM。
3.  **自动执行**：GPT-4o 会根据用户的提问，自动选择合适的 Tool 并提取参数（Function Calling）。后端收到参数后，通过 MCP 协议去请求 N8N。

#### 方案 B：基于关键词匹配的硬编码路由（兜底/简单场景）
如果有些场景 LLM 选不准，可以用简单的关键词匹配做优先级路由。
-   用户输入包含 "Lot" 或 "批次" -> 优先调用 `get_mes_lot_info`
-   用户输入包含 "报警" -> 优先调用 `get_mes_alarm_info`

### 3.2 关于 Token 管理
-   **占位符处理**：目前代码中的 `Bearer <YOUR_ACCESS_TOKEN_HERE>` 需要替换为环境变量或数据库配置。
-   **实现方案**：在 AI 配置管理页面增加 "MCP Server Token" 输入框，保存到 `ai_configs` 表中，后端动态读取。

---

## 四、Lot ID 格式解析规则

### 4.1 规则定义
根据你的描述，总结 Lot ID 格式如下：

| 类型 | 格式 | 示例 | 说明 | 正则表达式 |
| :--- | :--- | :--- | :--- | :--- |
| **主 Lot** | 字母+数字 | `NT938`, `VC001`, `P0093` | P 开头为控片/测试 | `\b([A-Z]+\d+)\b` |
| **分片 Lot** | 主Lot+.+序号 | `NT938.15` | 从主 Lot 分出的单片 | `\b([A-Z]+\d+\.\d+)\b` |

### 4.2 更新逻辑
需要在 `ai_middleware.py` 的 `_extract_lot_id` 方法中更新正则表达式：
```python
# 新的正则：匹配 NT938, VC001, P0093, NT938.15
match = re.search(r'\b([A-Z]+\d+(?:\.\d+)?)\b', question.upper())
```

---

## 五、功能开发路线图

### 阶段 1：MCP 工具链打通 (MVP)
**目标**：AI 能查 MES 数据，完成 Lot 追溯跳转闭环。

1.  [x] 整理需求文档 (本文档)
2.  [x] **MCP 客户端开发**：
    -   手写轻量 HTTP 客户端 [mcp_client.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/services/mcp_client.py)（基于 requests，100 行内）。
    -   支持 JSON-RPC 2.0 的 `tools/list` 和 `tools/call`。
    -   Token 从 `ai_configs` 表动态读取。
3.  [x] **工具路由实现**：
    -   [mcp_registry.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/services/mcp_registry.py) 工具注册表，注册 `MES_LotInfo_Query`。
    -   [ai_tools.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/services/ai_tools.py) 新增 `get_mes_lot_info` 工具 + 改造 `get_lot_info` 双源融合。
    -   GPT-4o 通过 Function Calling 自动调用。
4.  [x] **数据融合与跳转**：
    -   `get_lot_info` 先调 N8N MES 拿产品/工艺/状态，再查 `DT_EVENT_RAW` 拿设备事件时间线。
    -   前端 [AIFloatingBall.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/components/AIFloatingBall.vue) 表格行可点击跳转。
    -   [App.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/App.vue) 路由携带 `ts` 参数。
    -   [MachineDetail.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/views/MachineDetail.vue) 自动定位回放游标。
5.  [x] **Lot ID 解析更新**：
    -   正则升级为 `\b([A-Z]+\d+(?:\.\d+)?)\b`，支持 NT938/VC001/P0093/NT938.15。
6.  [x] **MCP 配置 UI**：
    -   [AIConfigPanel.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/components/AIConfigPanel.vue) Dify/N8N Tab 增加 MCP Server 配置区块。
    -   支持配置 URL、Token、超时、启用开关。
    -   测试连接按钮可发现 N8N 上的工具列表。
7.  [x] **后端 API**：
    -   [ai.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/routers/ai.py) 新增 `GET /api/ai/mcp/config`、`PUT /api/ai/mcp/config`、`POST /api/ai/mcp/test`、`GET /api/ai/mcp/tools`。
8.  [x] **数据库脚本**：
    -   [v2.1_add_mcp_config.sql](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/sql/v2.1_add_mcp_config.sql) 新增 4 个 MCP 配置键（MERGE 语法，增量更新）。
    -   [create_ai_tables.sql](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/sql/create_ai_tables.sql) 同步更新（新部署自动包含）。

### 阶段 2：扩展与优化
**目标**：提升 AI 的可用性和覆盖范围。

1.  [ ] **增加更多 MCP 工具**（如需）：
    -   接入 N8N 上的其他工作流（如设备状态、报警详情、工单生成等）。
2.  [ ] **Dify RAG 集成**（可选）：
    -   如果需要文档问答功能，配置 Dify知识库。
    -   实现 AI 自动路由到 Dify 的逻辑。
3.  [ ] **前端交互优化**：
    -   AI 回答增加图表展示（如产量柱状图）。
    -   支持多轮对话上下文的引用（如"刚才那个 Lot 的下一步是什么？"）。
4.  [ ] **异常处理与兜底**：
    -   MCP 调用失败时，给用户友好提示。
    -   LLM 选错工具时，增加兜底逻辑。

### 阶段 3：高级特性 (按需)
-   [ ] **主动推送**：告警时主动触发 AI 分析并推送给用户。
-   [ ] **批量处理**：支持一次查询多个 Lot ID。
-   [ ] **多 Agent 协作**：引入多个 AI Agent 分工合作。

---

## 六、已确认决策（2026-07-28）

| 编号 | 决策项 | 结论 |
| :--- | :--- | :--- |
| 1 | **N8N MCP Token** | 固定 Token，通过 AI 配置管理面板录入，存 `ai_configs` 表 |
| 2 | **AI 跳转目标** | 跳转到 `MachineDetail` 页面，并携带时间戳 query 参数 |
| 3 | **N8N 工具清单** | 先把已知的 `MES_LotInfo_Query` 接进去，后续用户自行在后台配置其他工具 |

