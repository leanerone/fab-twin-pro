# Dify + n8n 集成文档总览

> FabTwin Pro 与 Dify / n8n 集成的全部模板和 SOP 文档。
> 架构：Dify（AI 中枢）→ n8n（直连数据库：Oracle节点 + ODBC节点）→ Oracle/Informix

---

## 文件目录结构

```
integration/
├── README.md                            ← 你在这里
├── DIFY_N8N_联通部署SOP.md             ← ★ 唯一 SOP（6步从零到联通）
│
├── n8n/
│   ├── 01_query_alarms.json             ← 工作流：告警查询（Oracle节点）
│   ├── 02_query_machine_status.json     ← 工作流：机台状态（Oracle节点）
│   ├── 03_query_events.json             ← 工作流：事件时间线（Oracle节点）
│   ├── 04_query_lots.json               ← 工作流：Lot查询（Oracle节点）
│   ├── 05_query_yield.json              ← 工作流：产量统计（Oracle节点）
│   ├── 06_query_rcms_maintenance.json   ← 工作流：RCMS维修（ODBC节点）
│   └── 07_query_mes_lot.json            ← 工作流：MES Lot（ODBC节点）
│
└── dify/
    ├── fabtwin-ai-assistant.dsl.yaml    ← Dify 应用模板（可直接导入）
    ├── fabtwin-tools-openapi.yaml       ← 7个工具 OpenAPI 定义（导入 Dify）
    ├── system_prompt.md                 ← 系统提示词（参考）
    └── knowledgebase/
        └── OXE_Etcher_SOP_v1.0.md       ← RAG 知识库文档示例
```

---

## 快速开始

**只需阅读一个文件**：[DIFY_N8N_联通部署SOP.md](DIFY_N8N_联通部署SOP.md)

6 大步骤：
1. 配置 n8n 数据库凭据（Oracle + Informix ODBC）
2. 导入 n8n 工作流（7个）+ 绑定凭据
3. 创建 Dify 智能体
4. 配置 Dify 工具（接入 n8n）
5. 网站后端配置
6. 端到端调试

---

## 版本信息

- 文档版本：v3.0（去掉 DB Proxy，n8n 直连数据库）
- 更新日期：2026-09-03
- 适用 Dify 版本：0.6+
- 适用 n8n 版本：1.20+（需支持 Oracle/ODBC 节点）
