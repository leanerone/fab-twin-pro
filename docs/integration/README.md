# Dify + n8n 集成文档总览

> 本目录包含 FabTwin Pro 与 Dify / n8n 集成的所有模板和 SOP 文档。

---

## 📁 目录结构

```
integration/
├── README.md                    ← 你在这里
├── DIFY_N8N_ADVANCED_GUIDE.md   ← 联合开发教学（从测试到生产全流程）
│
├── dify/
│   ├── DIFY_INTEGRATION_SOP.md         ← Dify 接入详细 SOP
│   └── fabtwin-ai-assistant.dsl.yaml ← Dify 应用模板（可直接导入）
│
└── n8n/
    ├── N8N_INTEGRATION_SOP.md  ← n8n 接入详细 SOP
    ├── 01_export_alarm_report.json      ← 工作流：导出告警报表
    ├── 02_generate_work_order.json      ← 工作流：生成故障工单
    ├── 03_export_machine_data.json      ← 工作流：批量导出设备数据
    ├── 04_push_daily_report.json        ← 工作流：产线日报自动推送
    └── 05_general_query.json           ← 工作流：通用查询（转发给 AI）
```

---

## 🚀 快速开始（5步走）

### 第 1 步：部署 Dify 和 n8n
- Dify SOP 第二章：部署方式
- n8n SOP 第二章：部署方式

### 第 2 步：导入模板
- Dify：导入 `dify/fabtwin-ai-assistant.dsl.yaml`
- n8n：逐个导入 `n8n/01_*.json` ~ `05_*.json`

### 第 3 步：配置连接
- Dify：添加模型供应商 → 配置 6 个 API 工具
- n8n：修改 HTTP 节点的 URL 为你的 FabTwin 后端地址

### 第 4 步：在 FabTwin 中配置
- AI 配置管理页面 → 启用 Dify / n8n → 填入地址和密钥

### 第 5 步：测试验证
- 用 AI 悬浮球对话测试
- 用 n8n 自动化指令测试（如"导出告警报表"）

---

## 📖 文档说明

| 文档 | 内容 | 适合人群 |
|---|---|---|
| [DIFY_INTEGRATION_SOP.md](dify/DIFY_INTEGRATION_SOP.md) | Dify 从零到接入的完整步骤，包含部署→导入→配置→测试→RAG | 第一次接触 Dify 的工程师 |
| [N8N_INTEGRATION_SOP.md](n8n/N8N_INTEGRATION_SOP.md) | n8n 从零到接入的完整步骤，包含部署→导入→配置→自定义工作流 | 第一次接触 n8n 的工程师 |
| [DIFY_N8N_ADVANCED_GUIDE.md](DIFY_N8N_ADVANCED_GUIDE.md) | 进阶开发教学，5 天学习路线，从测试到生产 | 想深入掌握的开发人员 |

---

## 🔌 FabTwin 代码中的对接位置

| 功能 | 文件 | 说明 |
|---|---|---|
| AI 中间层主逻辑 | `backend/services/ai_middleware.py` | Provider 分发、Dify 调用、n8n 触发 |
| 6 个工具函数 | `backend/services/ai_tools.py` | Function Calling 工具定义与实现 |
| AI 配置面板（前端） | `frontend/src/components/AIConfigPanel.vue` | 配置界面 |
| AI 设置页面 | `frontend/src/views/AIConfigView.vue` | 独立页面 |
| AI 路由 | `backend/routers/ai.py` | API 接口 |

---

## ⚙️ FabTwin 当前支持的 Provider

| Provider | 状态 | 说明 |
|---|---|---|
| 本地规则引擎 | ✅ | 关键字匹配，无需 API Key |
| 智谱 AI (GLM) | ✅ |国内推荐 |
| OpenAI 官方 | ✅ | |
| DeepSeek | ✅ | |
| 通义千问 | ✅ | |
| 自定义 OpenAI 兼容 | ✅ | 任意兼容接口 |
| Dify | ✅ | 支持 chat-messages API |
| n8n | ✅ | Webhook 触发，仅 admin 可用 |

---

## ❓ 常见问题速查

**Q: Dify 和 n8n 有什么区别？**
A: Dify 是 AI 应用开发平台（对话、RAG、工具调用），n8n 是工作流自动化平台（数据处理、定时任务、系统集成）。两者可以配合使用。

**Q: 一定要两个都接吗？**
A: 不一定。只需要 AI 对话 + 知识库 → 只接 Dify；只需要自动化流程 → 只接 n8n；都需要 → 都接。

**Q: 当前代码里 Dify 和 n8n 是怎么配合的？**
A: 当前是"并行模式"。正常对话走配置的 Provider（可以是 Dify），当 AI 识别到特定关键字（如"导出报表"）时走 n8n。

**Q: n8n 为什么只有 admin 能用？**
A: 安全考虑。自动化流程涉及数据导出、工单创建等操作，权限比较高。如果需要放开，可以在 `ai_middleware.py` 的 `_trigger_n8n_workflow` 中去掉角色校验。

---

## 📝 版本信息

- 文档版本：v1.0
- 更新日期：2026-07-27
- 适用 FabTwin 版本：ver1.5+
- 适用 Dify 版本：0.6+
- 适用 n8n 版本：1.20+
