# FabTwin Pro — 历史文档导航（已归档）

> **归档提示：这不是当前交接入口。** 新人只读仓库根 `README.md`，再读自己模块的 README。本文保留 2026-11-03 的原导航内容；其中“当前”等表述、原相对链接和旧后端平铺路径均为历史记录，不要据此开发。

> 最后更新：2026-11-03（功能模块化落地后重整）
> 本文是全部文档的入口。**先看“我要找什么”，再进对应目录。**
> 当前开发主线：`ver3` 分支。

---

## 一、新人/接手先看这两份

| 我要… | 文档 |
|---|---|
| 看最新交付基线、验证证据、DB 迁移与复验步骤 | [交接说明_2026-11-02_ver3.md](./交接说明_2026-11-02_ver3.md) ⭐ |
| 看后续做什么（六维度分析 + A~E 清单 + 量产清单） | [优化深度分析与行动计划_20261101.md](./优化深度分析与行动计划_20261101.md) |

> 更早的接手急救包（2026-09 DB 轮留档）在 [archive/2026-09/HANDOFF_NOTES.md](./archive/2026-09/HANDOFF_NOTES.md)，分支/路径已过时，仅作历史参考。

## 二、目录结构

```
docs/
├── README.md                  ← 本导航
├── 交接说明_2026-11-02_ver3.md ← 当前交付基线（随版本更新）
├── 优化深度分析与行动计划…     ← 全局路线图（当前有效）
│
├── architecture/              ← 架构与模块化（方案 + 交互图）
│   ├── 功能模块化方案_20261103.md
│   ├── diagrams/01..08-*.html  ← archify 交互图（双击打开）
│   └── archive/                ← 迁移前的会议材料/预览（历史）
│
├── sops/                      ← 长期有效的操作手册
├── specs/                     ← 规范、说明书、机制（长期有效）
├── changelog/                 ← 跨版本变更记录
├── integration/               ← Dify / n8n / db_proxy 集成（张亮）
├── business/                  ← 机台接入/对接规范等业务文档
├── assets/                    ← 参考图、基线截图
├── v2.13-*                    ← v2.13 DB 变更与发布材料
└── archive/2026-10、2026-11/  ← 带日期的一次性交接/计划/报告（留底，不再维护）
```

## 三、按目的查找

| 我想要… | 看哪里 |
|---|---|
| 从 0 部署一套（在线打包→离线安装→启动） | [sops/DEPLOY_SOP.md](./sops/DEPLOY_SOP.md) ⭐ |
| 接一台新机台（三件套+deriver+入库） | [sops/新机台建模SOP_v1.md](./sops/新机台建模SOP_v1.md) |
| AI 数据真实链路怎么测 | [sops/AI链路测试SOP_v1.md](./sops/AI链路测试SOP_v1.md) |
| 画/改 SVG 模型 | [sops/SVG公共库编写指南.md](./sops/SVG公共库编写指南.md) |
| 系统架构总览（技术栈/模块/接口） | [specs/系统架构说明书.md](./specs/系统架构说明书.md) |
| 谁负责哪块、目录边界、提交流程 | [specs/团队分工与协作手册_20261101.md](./specs/团队分工与协作手册_20261101.md)、[specs/公共与模块边界定义_20261101.md](./specs/公共与模块边界定义_20261101.md) |
| **后端每个文件是谁的、改什么找谁、各线怎么自测（交接必读）** | [specs/后端文件交接地图_20261103.md](./specs/后端文件交接地图_20261103.md) ⭐ |
| 团队怎么运转（三铁律/四种开发流/12 周路线） | [specs/项目推进机制与开发模式_20261101.md](./specs/项目推进机制与开发模式_20261101.md) |
| 性能模型与预算 | [specs/PERFORMANCE_MODEL.md](./specs/PERFORMANCE_MODEL.md) |
| 跨版本改了什么 | [changelog/变更更改版记录.md](./changelog/变更更改版记录.md) |
| 功能怎么拆成模块、模块长什么样 | [architecture/功能模块化方案_20261103.md](./architecture/功能模块化方案_20261103.md) |
| 架构/文件/分工/进度/路线 交互图 | [architecture/diagrams/](./architecture/diagrams/)（01~08 HTML） |
| Dify / n8n 部署与可导入资产 | [integration/README.md](./integration/README.md)、[integration/DEPLOY_SOP.md](./integration/DEPLOY_SOP.md) |
| OXE 等机台业务接入 | [business/OXE接入指南.md](./business/OXE接入指南.md)、[business/对接规范文档.md](./business/对接规范文档.md) |

## 四、八张架构图索引（architecture/diagrams/）

| 图 | 内容 | 时效 |
|---|---|---|
| 01-system-architecture | 系统架构（设备→DB→poller→WS→动画 + Dify/n8n） | 当前 |
| 02-file-architecture | **当前文件架构**（前端 modules + 后端文件级归属） | 当前（已更新） |
| 03-ownership | **负责人分工树** | 当前（已更新） |
| 04-progress | 开发进度时间线（含 11-03 模块化落地） | 当前（已更新） |
| 05-roadmap | S1~S6 Sprint 路线 | 当前 |
| 06-functional-modules | 模块边界与依赖方向（已落地） | 当前（已更新） |
| 07-target-folders | 模块落地结构（迁移目标，现已成现实） | 已完成 |
| 08-migration-map | 迁移流向（M1~M4 历史记录） | 历史 |

> 图源 JSON 与 HTML 同目录；改数据用 archify 重渲染，不手改 HTML。

## 五、当前模块与负责人（速查）

| 模块 | 负责人 | 前端目录 | 后端归属 |
|---|---|---|---|
| ① 模型库 | 钱鸣 | `frontend/src/modules/model-library/` | routers/models、uploads；services/html_parser；models/ 资产 |
| ② 生产监控 | 季世庆 | `frontend/src/modules/production-monitor/` | 11 个数据 router；db_poller/simulator；sql、deploy |
| ③ AI 助手 | 朱明钊 | `frontend/src/modules/ai-assistant/` | routers/ai、services/ai 包 |
| ④ 系统管理 | 洪佳琪（过渡） | `frontend/src/modules/system-admin/` | routers/auth、users |
| ⑤ 智能体集成 | 张亮 | —（零平台代码） | docs/integration、deploy dify/n8n |
| ⑥ 平台内核 | 洪佳琪 | `frontend/src/platform/`、api/stores/router | main/config/db/models/schemas、core、公共 service |

详见 [architecture/功能模块化方案_20261103.md](./architecture/功能模块化方案_20261103.md) 与根目录 `CODEOWNERS`。
> 后端维持 `routers/services` 平铺（测试/脚本大量平铺 import，物理搬迁风险高），
> 负责人由 CODEOWNERS 按**文件**精确界定，不影响分工。

## 六、文档维护规则

- 长期有效的操作手册放 `sops/`，规范/机制放 `specs/`，变更记 `changelog/`
- 业务机台文档放 `business/`，外部智能体集成放 `integration/`
- 带日期的一次性交接/计划/报告，过期后移 `archive/<年-月>/`，**只归档不删除**
- 架构/分工相关的图统一放 `architecture/diagrams/`，保持 01~08 编号连续
- 每次发版在 `changelog/变更更改版记录.md` 追加条目，并更新本导航
