# Dify + n8n 真实导出格式参考

> 本文件记录 Dify 0.6.0 和 n8n 的真实导出格式，供后续更新 DSL/JSON 模板时参照。
> 更新日期：2026-09-04
> 来源：用户从测试环境真实导出的 `FabTwin_Agent_测试环境.yml` 和 `Zabbix Monitor To MySQL Alert Dify` 工作流

***

## 一、Dify DSL 格式（YAML，0.6.0）

### 1.1 顶层结构

```yaml
app:                          # 应用元信息
  description: 描述文本
  icon: 🤖                    # emoji 图标
  icon_background: '#FFEAD5'  # 背景色
  icon_type: emoji            # 固定 emoji
  mode: agent-chat            # ★ 必须 agent-chat（不是 agent）
  name: 应用名称
  use_icon_as_answer_icon: false
dependencies:                 # 模型插件依赖
  - current_identifier: null
    type: package
    value: 'plugin_unique_identifier: langgenius/azure_openai:0.0.56@<hash>'
    version: null
kind: app                     # ★ 必须 app
model_config:                 # ★ 全部配置在此节内
  # ...见下文 20 个子节...
```

### 1.2 model\_config 必须包含的 20 个子节

| 子节                                 | 类型     | 说明                                                                                                                |
| ---------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------- |
| `agent_mode`                       | object | Agent 配置：enabled/max\_iteration/prompt/strategy/tools                                                             |
| `annotation_reply`                 | object | 标注回复：{enabled: false}                                                                                             |
| `chat_prompt_config`               | object | 对话提示：{prompt: \[{role: system, text: ''}]}                                                                        |
| `completion_prompt_config`         | object | 补全提示：{conversation\_histories\_role: {...}, prompt: {text: ''}}                                                   |
| `dataset_configs`                  | object | 知识库：{datasets: {datasets: \[], retrieval\_model: multiple, top\_k: 4}, dataset\_query\_variable: ''}              |
| `external_data_tools`              | array  | 外部数据工具：\[]                                                                                                        |
| `file_upload`                      | object | 文件上传配置                                                                                                            |
| `model`                            | object | 模型：{completion\_params: {stop: \[]}, mode: chat, name: gpt-5.2, provider: langgenius/azure\_openai/azure\_openai} |
| `more_like_this`                   | object | {enabled: false}                                                                                                  |
| `opening_statement`                | string | 开场白：''                                                                                                            |
| `pre_prompt`                       | string | ★ System Prompt 放这里（不是 system\_prompt！）                                                                           |
| `prompt_type`                      | string | 固定 simple                                                                                                         |
| `retriever_resource`               | object | {enabled: true}                                                                                                   |
| `sensitive_word_avoidance`         | object | {config: {}, enabled: false, type: ''}                                                                            |
| `speech_to_text`                   | object | {enabled: false}                                                                                                  |
| `suggested_questions`              | array  | \[]                                                                                                               |
| `suggested_questions_after_answer` | object | {enabled: false}                                                                                                  |
| `text_to_speech`                   | object | {enabled: false, language: '', voice: ''}                                                                         |
| `user_input_form`                  | array  | ★ 开始变量放这里（不是 app\_variables！）                                                                                     |
| `version`                          | string | 固定 0.6.0                                                                                                          |

### 1.3 agent\_mode 结构

```yaml
agent_mode:
  enabled: true
  max_iteration: 10
  prompt: null                # 固定 null
  strategy: function_call     # 固定 function_call
  tools: []                   # 工具列表（见下文）
```

### 1.4 tools 项格式（MCP 类型 — 用户测试环境使用的格式）

```yaml
tools:
  - enabled: true
    notAuthor: false
    provider_id: liang_n8n_mcp_testenv       # MCP 服务提供者 ID
    provider_name: liang_n8n_MCPTrigger_TestEnv
    provider_type: mcp
    tool_label: Call_MES_LotInfo_Query_TestEnv_
    tool_name: Call_MES_LotInfo_Query_TestEnv_
    tool_parameters:                          # 参数映射
      lot: null                               # null 表示由 LLM 动态填入
    type: mcp
```

> **注意**：Dify DSL 导入只支持已配置好的 MCP 工具引用。
> 对于 HTTP API 工具（OpenAPI），需导入 DSL 后在 Dify UI「工具 → 自定义工具 → OpenAPI」手动添加。
> 因此我们生成的 DSL 中 `agent_mode.tools` 留空，配套 `fabtwin-tools-openapi.yaml` 供 UI 导入。

### 1.5 user\_input\_form 项格式

```yaml
user_input_form:
  # 文本输入
  - text-input:
      variable: machine_id
      label: 当前机台ID
      required: false
      default: ''
      max_length: 100
  # 下拉选择
  - select:
      variable: user_role
      label: 用户角色
      required: true
      default: user
      options:
        - user
        - admin
  # 段落输入
  - paragraph:
      variable: n8n_secret
      label: n8n 密钥
      required: false
      default: ''
```

### 1.6 file\_upload 结构（直接复制即可）

```yaml
file_upload:
  allowed_file_extensions: [.JPG, .JPEG, .PNG, .GIF, .WEBP, .SVG, .MP4, .MOV, .MPEG, .WEBM]
  allowed_file_types: [image]
  allowed_file_upload_methods: [remote_url, local_file]
  enabled: true
  image:
    detail: high
  number_limits: 3
  transfer_methods: [remote_url, local_file]
```

### 1.7 model 结构

```yaml
model:
  completion_params:
    stop: []
  mode: chat
  name: gpt-5.2
  provider: langgenius/azure_openai/azure_openai
```

***

## 二、n8n 工作流 JSON 格式

### 2.1 顶层结构

```json
{
  "name": "工作流名称",
  "nodes": [...],
  "pinData": {},
  "connections": {...},
  "active": false,
  "settings": {"executionOrder": "v1"},
  "versionId": "UUID",
  "meta": {"templateCredsSetupCompleted": true, "instanceId": "fabtwin-local"},
  "id": "UUID",
  "tags": []
}
```

### 2.2 必须的顶层字段

| 字段            | 类型      | 说明                                                           |
| ------------- | ------- | ------------------------------------------------------------ |
| `name`        | string  | 工作流名称                                                        |
| `nodes`       | array   | 节点列表                                                         |
| `pinData`     | object  | 固定 `{}`                                                      |
| `connections` | object  | 连接关系                                                         |
| `active`      | boolean | 导入后是否自动激活（建议 false）                                          |
| `settings`    | object  | `{"executionOrder": "v1"}`                                   |
| `versionId`   | string  | UUID（随机生成即可）                                                 |
| `meta`        | object  | `{"templateCredsSetupCompleted": true, "instanceId": "..."}` |
| `id`          | string  | UUID（随机生成即可）                                                 |
| `tags`        | array   | 固定 `[]`                                                      |

### 2.3 节点（node）结构

```json
{
  "parameters": {...},
  "name": "节点名称",
  "type": "n8n-nodes-base.webhook",
  "typeVersion": 2,
  "position": [240, 300],
  "webhookId": "xxx-webhook-id",
  "credentials": {"oracleApi": {"id": "", "name": "FabTwin Oracle"}}
}
```

### 2.4 各节点 typeVersion 对照表

| 节点类型               | type                            | typeVersion |
| ------------------ | ------------------------------- | ----------- |
| Webhook            | n8n-nodes-base.webhook          | **2**       |
| Code（JS）           | n8n-nodes-base.code             | **2**       |
| Oracle             | n8n-nodes-base.oracle           | 1           |
| MySQL              | n8n-nodes-base.mySql            | 2           |
| HTTP Request       | n8n-nodes-base.httpRequest      | 4           |
| IF                 | n8n-nodes-base.if               | 2           |
| Respond to Webhook | n8n-nodes-base.respondToWebhook | 1           |
| Email Send         | n8n-nodes-base.emailSend        | 2           |
| Schedule Trigger   | n8n-nodes-base.scheduleTrigger  | 1.3         |

### 2.5 connections 格式

```json
{
  "节点A名": {
    "main": [
      [
        {"node": "节点B名", "type": "main", "index": 0}
      ]
    ]
  }
}
```

- 每个节点名作为 key

- `main` 是固定 key

- 值是数组的数组：`[[{node, type, index}]]`

- 一对一连接就是 `[[{...}]]`

- 一对多连接就是 `[[{...}, {...}]]`（分叉）

### 2.6 Webhook 节点 parameters

```json
{
  "httpMethod": "POST",
  "path": "get_machine_status",
  "responseMode": "responseNode",
  "options": {}
}
```

### 2.7 Code 节点 parameters

```json
{
  "jsCode": "const body = $input.first().json; return { json: {...} };",
  "options": {}
}
```

### 2.8 Oracle 节点 parameters + credentials

```json
{
  "parameters": {
    "operation": "executeQuery",
    "query": "SELECT * FROM machines WHERE id = '{{ $json.machine_id }}'",
    "options": {}
  },
  "credentials": {
    "oracleApi": {"id": "", "name": "FabTwin Oracle"}
  }
}
```

> 导入后需在 n8n 中手动绑定 Oracle 凭据。

### 2.9 Respond to Webhook 节点 parameters

```json
{
  "responseCode": 200,
  "responseBody": "={{ JSON.stringify($json) }}",
  "options": {}
}
```

***

## 三、Dify → n8n 工具对接方式

### 方式 A：MCP（用户测试环境使用的方式）

```
Dify App
  └─ agent_mode.tools[]
       └─ type: mcp, provider_id: <n8n_mcp_server_id>
            └─ n8n MCP Trigger 节点
                 └─ 路由到各 n8n 工作流
```

- 优点：Dify 自动发现工具，无需手动配 OpenAPI

- 缺点：需要在 n8n 额外配置 MCP Server Trigger

### 方式 B：OpenAPI/HTTP API（我们当前生成模板使用的方式）

```
Dify App
  └─ Dify UI「工具 → 自定义工具 → OpenAPI Schema」
       └─ 导入 fabtwin-tools-openapi.yaml
            └─ 每个 path 对应一个 n8n Webhook 工作流
```

- 优点：n8n 端只需 Webhook 节点，无需 MCP Server

- 缺点：Dify DSL 导入时 `agent_mode.tools` 留空，需导入后手动添加 OpenAPI 工具

### 当前 FabTwin 选用方式 B 的原因

1. n8n 工作流模板已全部使用 Webhook 触发，无需额外配置 MCP
2. OpenAPI 规范文件 `fabtwin-tools-openapi.yaml` 已生成，一次导入即定义 10 个工具
3. 对用户更直观：每个工具 = 一个 n8n Webhook = 一个 OpenAPI path

***

## 四、用户测试环境真实导出样本（脱敏）

### 4.1 Dify 导出（YAML 摘要）

来源：`FabTwin_Agent_测试环境.yml`

```yaml
app:
  description: 你是一名IT助手，根据用户问题，调用合适的工具，查询lot相关信息
  icon: 🤖
  icon_background: '#FFEAD5'
  icon_type: emoji
  mode: agent-chat
  name: FabTwin_Agent_测试环境
  use_icon_as_answer_icon: false
dependencies:
  - current_identifier: null
    type: package
    value: 'plugin_unique_identifier: langgenius/azure_openai:0.0.56@3410d96fe3aaece47897701a7e7ef468abb230dfaa4f5dcb49a17dbbdda43442'
    version: null
kind: app
model_config:
  agent_mode:
    enabled: true
    max_iteration: 10
    prompt: null
    strategy: function_call
    tools:
      # 共 6 个 MCP 工具，全部来自 provider: liang_n8n_MCPTrigger_TestEnv
      - enabled: true
        notAuthor: false
        provider_id: liang_n8n_mcp_testenv
        provider_name: liang_n8n_MCPTrigger_TestEnv
        provider_type: mcp
        tool_label: Call_MES_BounsLoss_Query_TestEnv_
        tool_name: Call_MES_BounsLoss_Query_TestEnv_
        tool_parameters: {lot: null}
        type: mcp
      # ... 其余 5 个工具结构相同 ...
  # ... 其余 model_config 子节 ...
  pre_prompt: '你是一名IT助手，根据用户问题，调用合适的工具，查询lot相关信息'
  prompt_type: simple
  user_input_form: []
  version: 0.6.0
```

### 4.2 n8n 导出（JSON 摘要）

来源：`Zabbix Monitor To MySQL Alert Dify` 工作流

```json
{
  "name": "Zabbix Monitor To MySQL Alert Dify",
  "nodes": [
    {
      "parameters": {"method": "POST", "url": "http://10.30.8.184/api_jsonrpc.php", ...},
      "id": "e21c78e9-...",
      "name": "Zabbix Login",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4,
      "position": [944, -256]
    },
    {
      "parameters": {"operation": "executeQuery", "query": "INSERT INTO server_metrics ...", ...},
      "id": "b83f7319-...",
      "name": "Upsert Metrics To MySQL",
      "type": "n8n-nodes-base.mySql",
      "typeVersion": 2,
      "position": [2032, -384],
      "credentials": {"mySql": {"id": "kq5Pl5ndYUJynzJM", "name": "MySQL_XAMPP_n8n"}}
    }
    // ... 更多节点 ...
  ],
  "pinData": {},
  "connections": {
    "Zabbix Login": {"main": [[{"node": "Get Hosts", "type": "main", "index": 0}]]},
    // ... 更多连接 ...
  },
  "active": true,
  "settings": {"executionOrder": "v1", "binaryMode": "separate"},
  "versionId": "0e1c2b96-daa3-478a-8cb9-23f39daaf152",
  "meta": {"templateCredsSetupCompleted": true, "instanceId": "3a88f4a70ff5583cab71266511921616a23539d988a5c2a732a8f07d0758ad75"},
  "id": "vBWut3cTiKQw1gWc",
  "tags": []
}
```

***

## 五、更新指南

当需要修改 Dify DSL 或 n8n JSON 模板时：

1. **修改 Dify DSL**：编辑 `scripts/generate_dify_dsl.py`，运行 `python scripts/generate_dify_dsl.py`
2. **修改 n8n JSON**：编辑 `scripts/generate_n8n_workflows.py`，运行 `python scripts/generate_n8n_workflows.py`
3. **修改 OpenAPI**：直接编辑 `docs/integration/dify/fabtwin-tools-openapi.yaml`
4. 本文件（格式参考）在 Dify/n8n 版本升级或导出格式变化时更新

