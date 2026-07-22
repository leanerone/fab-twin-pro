# FabTwin AI 集成指南

## 一、当前系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      FabTwin 平台                            │
├─────────────────────────────────────────────────────────────┤
│  前端 (Vue3)          │  后端 (FastAPI)                      │
│  - 机台详情页          │  - REST API (/api/*)                │
│  - 平面图              │  - WebSocket 推送                   │
│  - 历史回放            │  - DB 轮询服务                      │
│  - AI助手组件          │  - 事件解析服务                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Oracle 量产数据库                         │
│  - DT_EVENT_RAW: 历史事件表                                 │
│  - DT_EVENT_RAW_CUR: 当前状态表                             │
│  - MACHINES: 机台基础信息                                   │
│  - MACHINE_MODEL_CONFIGS: 模型配置                          │
└─────────────────────────────────────────────────────────────┘
```

## 二、AI 接入点规划

### 2.1 现有 AI 组件
- `frontend/src/components/AiAssistant.vue` - 前端 AI 对话组件
- 支持 OpenAI API 调用
- 支持上下文对话

### 2.2 AI 能力扩展方向

#### A. 自然语言查询
```python
# 用户输入
"7月15号 PODOPENER-1 有什么异常"

# AI 解析后调用 API
GET /api/machines/PODOPENER-1/events?date=2026-07-15&level=alarm
```

#### B. 语音交互
```javascript
// 前端集成 Web Speech API
const recognition = new webkitSpeechRecognition()
recognition.lang = 'zh-CN'

// 用户说："跳到昨天下午三点的异常时间线"
// AI 解析后跳转
router.push({
  path: `/machine/${machineId}`,
  query: { date: '2026-07-14', time: '15:00' }
})
```

#### C. 异常检测与推荐
```python
# 后端定时分析异常模式
# 提供给 AI 的上下文
context = {
    "machine_id": "PODOPENER-1",
    "time_range": "2026-07-15 14:00 ~ 15:00",
    "alarms": [
        {"time": "14:23", "code": "E0042", "desc": "温度过高"},
        {"time": "14:25", "code": "E0018", "desc": "压力异常"}
    ],
    "related_events": [
        {"time": "14:20", "event": "lot_start", "lot_id": "LOT-12345"}
    ]
}

# AI 推理
"14:23 温度过高可能与 14:20 开始加工的 LOT-12345 有关，建议检查该批次的 Recipe 参数"
```

## 三、Dify / N8n 接入案例

### 3.1 Dify 接入（推荐）

#### 方案：通过 API 扩展 Dify Agent

```yaml
# Dify 工具定义 (OpenAPI schema)
openapi: 3.0.0
info:
  title: FabTwin API
  version: 1.0.0
servers:
  - url: http://your-server:8000/api
paths:
  /machines/{machine_id}/events:
    get:
      summary: 获取机台事件
      parameters:
        - name: machine_id
          in: path
          required: true
          schema:
            type: string
        - name: date
          in: query
          schema:
            type: string
      responses:
        '200':
          description: 事件列表
  /machines/{machine_id}/lots:
    get:
      summary: 获取机台批次
```

#### Dify Agent 配置步骤

1. **创建自定义工具**
   - 进入 Dify 工作流 → 工具 → 导入 OpenAPI Schema
   - 填入 FabTwin API 文档

2. **创建 Agent**
   ```text
   名称: FabTwin 机台助手
   提示词: |
     你是 FabTwin 晶圆厂机台监控平台的 AI 助手。
     用户会问关于机台状态、异常事件、批次信息的问题。
     
     你可以调用以下工具：
     - get_events: 查询机台事件
     - get_lots: 查询批次信息
     - get_machines: 获取机台列表
     
     当用户说"跳转到xxx时间"时，回复 JSON 格式：
     {"action": "navigate", "machine_id": "xxx", "date": "YYYY-MM-DD", "time": "HH:MM"}
   ```

3. **前端集成**
   ```javascript
   // frontend/src/api/ai.js
   export async function askDify(prompt, context) {
     const res = await fetch('https://api.dify.ai/v1/chat-messages', {
       method: 'POST',
       headers: {
         'Authorization': `Bearer ${DIFY_API_KEY}`,
         'Content-Type': 'application/json'
       },
       body: JSON.stringify({
         query: prompt,
         user: currentUser.id,
         inputs: { context }
       })
     })
     return res.json()
   }
   ```

### 3.2 N8n 接入（自动化工作流）

#### 用例：异常告警推送到 Teams/Slack

```json
{
  "name": "FabTwin Alarm Notifier",
  "nodes": [
    {
      "type": "webhook",
      "name": "Webhook",
      "parameters": {
        "path": "alarm-webhook",
        "method": "POST"
      }
    },
    {
      "type": "function",
      "name": "Parse Alarm",
      "parameters": {
        "functionCode": "const alarm = items[0].json;\nreturn [{\n  json: {\n    machine_id: alarm.machine_id,\n    alarm_code: alarm.alarm_code,\n    timestamp: alarm.timestamp,\n    severity: alarm.level,\n    description: alarm.description\n  }\n}];"
      }
    },
    {
      "type": "slack",
      "name": "Slack Notification",
      "parameters": {
        "channel": "#fab-alarms",
        "text": "🚨 机台 {{$json.machine_id}} 告警\n\n时间: {{$json.timestamp}}\n类型: {{$json.alarm_code}}\n描述: {{$json.description}}"
      }
    }
  ]
}
```

#### 用例：定时分析异常趋势

```yaml
# n8n 工作流
trigger:
  type: schedule
  cron: "0 8 * * 1-5"  # 工作日早8点

workflow:
  - action: http_request
    url: http://your-server:8000/api/analytics/alarm-trend
    method: GET
    params:
      days: 7

  - action: openai_chat
    model: gpt-4
    prompt: |
      分析以下一周告警趋势数据，生成简报：
      {{ $json.trend_data }}
      
      请包含：
      1. 告警总量变化
      2. TOP3 高频告警
      3. 异常机台建议

  - action: slack
    channel: "#fab-reports"
    message: "{{ $json.ai_response }}"
```

## 四、本地规则引擎

### 4.1 现有规则配置

```python
# backend/services/rules_engine.py (待实现)

RULES = [
    {
        "rule_id": "R001",
        "name": "温度过高告警",
        "condition": "temp > 80",
        "action": "alarm",
        "severity": "critical"
    },
    {
        "rule_id": "R002",
        "name": "压力异常",
        "condition": "pressure < 0.5 OR pressure > 2.0",
        "action": "alarm",
        "severity": "warning"
    },
    {
        "rule_id": "R003",
        "name": "长时间待机",
        "condition": "state == 'idle' AND duration > 3600",
        "action": "notify",
        "message": "机台已待机超过1小时"
    }
]
```

### 4.2 规则触发流程

```
DT_EVENT_RAW 新数据
      │
      ▼
┌───────────────────┐
│  rules_engine.py  │
│  - 解析 payload   │
│  - 匹配规则条件   │
│  - 执行动作       │
└───────────────────┘
      │
      ▼
  ┌─────┐ ┌──────┐ ┌────────┐
  │alarm│ │notify│ │AI分析  │
  └─────┘ └──────┘ └────────┘
```

## 五、部署建议

### 5.1 Dify 部署
```bash
# Docker Compose
git clone https://github.com/langgenius/dify.git
cd dify/docker
docker-compose up -d

# 访问 http://localhost:3000
```

### 5.2 N8n 部署
```bash
# Docker
docker run -d --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# 访问 http://localhost:5678
```

### 5.3 连接顺序

```
1. Dify → 创建 Agent → 导入 FabTwin API 工具
2. N8n → 创建 Webhook → 监听 FabTwin 事件
3. 前端 → 集成 Dify Chat API
4. 后端 → 添加事件推送到 N8n Webhook
```