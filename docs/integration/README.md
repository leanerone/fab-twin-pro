# Dify + n8n 集成文档总览

> FabTwin Pro 与 Dify / n8n 集成的全部模板和参考文档。
> 架构：Dify（AI 中枢）→ n8n（Webhook 工作流 → Oracle 节点）→ Oracle DB

---

## 文件目录结构

```
integration/
├── README.md                              ← 你在这里
├── dify_n8n_format_reference.md            ← ★ Dify/n8n 真实导出格式参考（后续更新用）
│
├── n8n/
│   ├── F1_get_machine_status.json         ← 机台实时状态/全厂概览
│   ├── F2_get_lot_info.json                ← Lot 位置/进度追踪
│   ├── F3_get_machine_alarms.json          ← 报警统计/异常定位
│   ├── F4_get_event_timeline.json          ← 温度趋势/事件时间线
│   ├── F5_get_yield_stats.json             ← 产量/晶圆/完成率
│   ├── F6_get_recipe_info.json             ← 工艺配方/Recipe
│   ├── F7_get_mes_lot_info.json            ← MES Lot 详情（管理员）
│   ├── F8_export_alarm_report.json         ← 导出报警报表 Excel（管理员）
│   ├── F9_generate_work_order.json         ← 生成故障工单（管理员）
│   └── F10_list_capabilities.json           ← 功能清单
│
└── dify/
    ├── fabtwin-ai-assistant.dsl.yml         ← Dify 应用模板（全局通用版，可直接导入）
    ├── fabtwin-ai-assistant-OXE.dsl.yml     ← Dify 应用模板（OXE 机台专属版）
    ├── fabtwin-tools-openapi.yaml           ← 10 个工具 OpenAPI 定义（导入 Dify 自定义工具）
    └── knowledgebase/
        └── OXE_Etcher_SOP_v1.0.md           ← RAG 知识库文档示例
```

---

## 快速开始

### 1. 导入 n8n 工作流（10 个）
逐个导入 `n8n/F1~F10*.json` → 双击 Oracle 节点选凭证 → 激活

### 2. 导入 Dify 应用
导入 `dify/fabtwin-ai-assistant.dsl.yaml`（或 OXE 专属版）
- System Prompt 已内置在 `pre_prompt` 里（10 类 4 步 + FABTWIN 结构化输出）
- 开始变量已配置（machine_id / user_role）

### 3. 配置 Dify 工具
在 Dify 应用「工具 → 自定义工具 → OpenAPI Schema」中导入 `dify/fabtwin-tools-openapi.yaml`，填入 n8n 地址

### 4. 后端配置
```env
ENABLE_LOCAL_RULE_FALLBACK=false
MACHINE_DIFY_CONFIGS_OXE_DIFY_ENDPOINT=https://<dify>/v1
MACHINE_DIFY_CONFIGS_OXE_DIFY_API_KEY=app-xxxx
```

---

## 版本信息

- 文档版本：v4.0（10 工作流 + Dify 0.6.0 格式对齐）
- 更新日期：2026-09-04
- 适用 Dify 版本：0.6.0
- 适用 n8n 版本：1.20+（需支持 Oracle 节点）
