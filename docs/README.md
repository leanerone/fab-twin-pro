# FabTwin Pro — docs/ 目录说明

> 最后更新：2026-09-23
> 本目录是 FabTwin 项目的所有正式文档集合，按用途分 3 大类。
> 完整 SOP 见 [`./DEPLOY_SOP.md`](./DEPLOY_SOP.md)。

---

## 1. 目录结构速览

```
docs/
├── README.md                          ← 本文件（导航）
├── DEPLOY_SOP.md                      ⭐ 端到端部署 SOP（在线打包 → 离线安装 → 离线启动）
├── 系统架构说明书.md                   ← 系统架构总览（技术栈、模块、接口）
├── FabTwin_系统架构图.drawio           ← 可编辑架构图（drawio 源文件）
├── FabTwin_系统架构图.svg              ← 架构图 SVG 版本（可贴在 PPT 里）
├── 变更更改版记录.md                   ← 跨版本变更日志
│
├── integration/                       ← AI 子系统文档（自成体系）
│   ├── README.md
│   ├── DEPLOY_SOP.md                  ← Dify / n8n / db_proxy 集成 SOP
│   ├── AI能力说明与规划.md
│   ├── dify_n8n_format_reference.md
│   ├── dify/
│   │   ├── *.dsl.yml
│   │   └── knowledgebase/
│   └── n8n/
│       ├── *.json                    ← F1~F10 工作流定义
│       └── backup_oracle_direct/
│
├── business/                          ← 业务文档（与部署解耦）
│   ├── 对接规范文档.md
│   ├── OXE接入指南.md
│   └── 新机台开发SOP_v3.md
│
└── archive/                           ← 归档：过期/历史文档（不删除，留底）
    ├── FabTwin_项目报告.html
    ├── WIN2022_DEPLOY_SOP.md          ← 早期 IIS 部署 SOP（已并入 DEPLOY_SOP.md）
    ├── IIS_WINDOWS_AUTH_GUIDE.md      ← 早期方案设计文档（已弃用，自标）
    ├── PODOPENER.docx
    ├── VPO_2D.docx
    ├── alarmnew.docx
    └── 项目.txt
```

---

## 2. 怎么找到想要的文档

| 我想要… | 看哪里 |
|---|---|
| **从 0 部署一套 FabTwin**（在线打包 + 离线安装 + 启动） | [`DEPLOY_SOP.md`](./DEPLOY_SOP.md) ⭐ |
| **每个 deploy 脚本的用途** | [`../deploy/README.md`](../deploy/README.md) |
| **架构总览**（技术栈 / 模块 / 接口） | [`系统架构说明书.md`](./系统架构说明书.md) |
| **架构图** | [`FabTwin_系统架构图.svg`](./FabTwin_系统架构图.svg)（或 `.drawio` 源文件） |
| **部署 Dify / n8n / db_proxy** | [`integration/DEPLOY_SOP.md`](./integration/DEPLOY_SOP.md) |
| **AI 工具/能力规划** | [`integration/AI能力说明与规划.md`](./integration/AI能力说明与规划.md) |
| **机台接入**（OXE 等） | [`business/OXE接入指南.md`](./business/OXE接入指南.md) |
| **新机台开发流程** | [`business/新机台开发SOP_v3.md`](./business/新机台开发SOP_v3.md) |
| **对接其他系统的协议** | [`business/对接规范文档.md`](./business/对接规范文档.md) |
| **跨版本变更** | [`变更更改版记录.md`](./变更更改版记录.md) |

---

## 3. 维护规则

- **新 SOP 写完整**：先放 `docs/` 根目录，旧文档移到 `archive/`（**不删**）
- **业务文档**（与机台/业务流程相关的）放 `business/`，**不要**混进 `docs/` 根
- **集成文档**（AI 集成）放 `integration/`
- **历史/阶段性报告**放 `archive/`
- **每次发版** 在 `变更更改版记录.md` 加一行

---

## 4. 已废弃 / 已归档文档说明

| 文档 | 状态 | 替代 |
|---|---|---|
| `deploy-sop.md`（小写旧名） | **已重命名+重写** | `DEPLOY_SOP.md` |
| `WIN2022_DEPLOY_SOP.md` | **已归档**（内容并入 DEPLOY_SOP.md） | DEPLOY_SOP.md §5 |
| `IIS_WINDOWS_AUTH_GUIDE.md` | **已归档**（文件自标「早期方案已弃用」） | DEPLOY_SOP.md §8 |
| `PODOPENER.docx` / `VPO_2D.docx` / `alarmnew.docx` | **已归档**（老设计文件） | `系统架构说明书.md` |
| `项目.txt` | **已归档**（早期需求） | README + 系统架构说明书 |