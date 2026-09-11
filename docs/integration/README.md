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
│   ├── FAB_QUERY_merged.json              ← ★ 现役：读类合并工作流（F1~F6+F10，webhook: fab_query）
│   ├── FAB_ADMIN_merged.json              ← ★ 现役：管理类合并工作流（F7 F8 F9，webhook: fab_admin）
│   ├── F1_get_machine_status.json         ← 以下 10 个为旧版单工具流，保留但不 Active
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
    ├── fabtwin-tools-openapi.yaml           ← ★ 合并版 OpenAPI：2 个 path，只占 2 个 Dify 工具位
    ├── eap-log-query.dsl.yml                ← ★ LOG 捞取工作流（19节点，挂在 Agent 下作 tool）
    └── knowledgebase/
        └── OXE_Etcher_SOP_v1.0.md           ← RAG 知识库文档示例

services/db_proxy/                           ← DB Proxy 服务（与后端同 server 部署）
├── main.py                                  ← FastAPI，10 个原始端点 + 2 个 action 分发端点
├── requirements.txt                         ← oracledb + fastapi + uvicorn
├── .env.example                             ← 配置模板
└── start.bat                                ← Windows 启动脚本

tests/
└── test_n8n_f1_f10.py                       ← ★ 分层自测（直连 db_proxy + 经 n8n 各测一次，--merged 测合并版）
```

---

## 工具收敛：10 个 Dify 工具位 → 2 个

**为什么要做**：Dify 按 OpenAPI 里的 **path 数量**注册工具，原来 F1~F10 是 10 个 path，一次性占满 Agent 工具位，LOG 捞取等其他工具挂不上去。

**怎么做的**：只保留 2 个 path，用 `action` 参数分发。db_proxy 侧原来那 10 个端点**一个都没删**，分发端点只是按 action 转交给同一批 handler，业务逻辑零改动。

| 现工具 | webhook / 端点 | 覆盖 | action 取值 |
|---|---|---|---|
| `fab_query` | `/webhook/fab_query` → `/query/fab_query` | F1~F6 + F10（读类） | `machine_status` `lot_info` `machine_alarms` `event_timeline` `yield_stats` `recipe_info` `list_capabilities` |
| `fab_admin` | `/webhook/fab_admin` → `/query/fab_admin` | F7 F8 F9（写 + 导出） | `mes_lot_info` `export_alarm_report` `generate_work_order` |

读写分离而不是合成 1 个：管理类含真实建工单的写操作，单独一个工具便于后续加权限控制，模型也更不容易误触。

**切换步骤**：
1. 重启 db_proxy（新增两个端点）
2. n8n 导入 `FAB_QUERY_merged.json` / `FAB_ADMIN_merged.json`，改 HTTP 节点地址，**点 Active**；旧 10 个工作流关掉 Active 即可，不用删
3. Dify 里删掉旧工具，重新导入 `fabtwin-tools-openapi.yaml`
4. 验证：`python tests\test_n8n_f1_f10.py --merged`

**注意**：合并版 n8n 的 `jsonBody` 必须是整体透传 `{{ JSON.stringify($json.body || {}) }}`。若沿用旧的逐字段白名单写法，`action` 会被丢掉，db_proxy 会回「缺少 action 参数」。

**以后加新功能**（如 F11 查 run 货历史）：只需在 db_proxy 的 `_QUERY_ACTIONS` 字典加一行 + OpenAPI 的 action enum 加一个值。**不再需要新建 n8n 工作流，也不再多占 Dify 工具位。**

---

## 快速开始

**只需阅读一个文件**：[DEPLOY_SOP.md](DEPLOY_SOP.md)

7 大步骤：
1. 部署 DB Proxy（Python，10 分钟）
2. 导入 n8n 工作流（合并版 2 个，改地址+激活，3 分钟）
3. 导入 Dify 应用模板（2 分钟）
4. 配置 Dify OpenAPI 工具（10 分钟）
5. Dify 测试对话（5 分钟）
6. 配置 FabTwin 后端 .env（3 分钟）
7. 端到端测试（5 分钟）

---

## 版本信息

- 文档版本：v5.1（DB Proxy 中转架构 + Dify 工具收敛为 2 个）
- 更新日期：2026-09-11
- 适用 Dify 版本：1.15+
- **已知坑**：Dify 1.15+ 出站走 squid 代理，上游非 2xx 会被包装成「SSRF blocked」；HTTP 节点的 `headers` 字段按**换行符**切分，YAML 单引号字面量 `\n` 不会被转义，需用块标量 `|-` 或 `>`；Dify 按 OpenAPI 的 path 数量注册工具，path 越多占位越多
- 适用 n8n 版本：1.20+
- 适用 Oracle 版本：11g（通过 DB Proxy Thick mode 连接）
