# Dify + n8n 集成文档总览

> 架构：Dify（AI 中枢）→ n8n（HTTP Request）→ DB Proxy（Python FastAPI）→ Oracle 11g
>
> 因为 Oracle 11g 不支持 n8n 直连（n8n 的 Oracle 节点需要 12c+），所以用 DB Proxy 中转。

---

## 文件目录结构

```
integration/
├── README.md                              ← 你在这里
├── DEPLOY_SOP.md                           ← ★ 手把手 SOP（7步）
├── dify_n8n_format_reference.md            ← Dify/n8n 真实导出格式参考
│
├── n8n/
│   ├── F1_get_machine_status.json         ← 3节点: Webhook→HTTP Request→Respond
│   ├── F2_get_lot_info.json                ← （同上，指向 DB Proxy）
│   ├── F3_get_machine_alarms.json
│   ├── F4_get_event_timeline.json
│   ├── F5_get_yield_stats.json
│   ├── F6_get_recipe_info.json
│   ├── F7_get_mes_lot_info.json
│   ├── F8_export_alarm_report.json
│   ├── F9_generate_work_order.json
│   ├── F10_list_capabilities.json
│   └── backup_oracle_direct/               ← 旧版备份（Oracle 直连版，5节点）
│
└── dify/
    ├── fabtwin-ai-assistant.dsl.yml        ← Dify 应用模板（全局通用版）
    ├── fabtwin-ai-assistant-OXE.dsl.yml    ← Dify 应用模板（OXE 机台专属版）
    ├── fabtwin-tools-openapi.yaml           ← 10 个工具 OpenAPI 定义
    └── knowledgebase/
        └── OXE_Etcher_SOP_v1.0.md           ← RAG 知识库文档示例

services/db_proxy/                           ← DB Proxy 服务（与后端同 server 部署）
├── main.py                                  ← FastAPI，10 个查询端点
├── requirements.txt                         ← oracledb + fastapi + uvicorn
├── .env.example                             ← 配置模板
└── start.bat                                ← Windows 启动脚本
```

---

## 快速开始

**只需阅读一个文件**：[DEPLOY_SOP.md](DEPLOY_SOP.md)

7 大步骤：
1. 部署 DB Proxy（Python，10 分钟）
2. 导入 n8n 工作流（10 个，改地址+激活，10 分钟）
3. 导入 Dify 应用模板（2 分钟）
4. 配置 Dify OpenAPI 工具（10 分钟）
5. Dify 测试对话（5 分钟）
6. 配置 FabTwin 后端 .env（3 分钟）
7. 端到端测试（5 分钟）

---

## 版本信息

- 文档版本：v5.0（DB Proxy 中转架构）
- 更新日期：2026-09-04
- 适用 Dify 版本：0.6.0
- 适用 n8n 版本：1.20+
- 适用 Oracle 版本：11g（通过 DB Proxy Thick mode 连接）
