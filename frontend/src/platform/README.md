# 模块⑥ 平台内核（platform / backend core）

- **负责人**：洪佳琪
- **定位**：被 ≥2 个功能模块共用、改坏会全体受影响的底座。刻意保持小，不做业务。

## 前端

```
platform/frontend/
  shell/        AppHeader；App.vue/router/main.js 仍在 src/ 根（应用装配表）
  core/composables/  useThree、useRafLoop、threeDispose、useWebSocket（跨模块共享）
```
另有内核入口（在 src/ 根，归此模块）：`frontend/src/App.vue`、`frontend/src/main.js`、
`frontend/src/router/`、`frontend/src/stores/{app,auth,model}.js`、`frontend/src/utils/`、
`frontend/src/styles/`、`frontend/src/configs/`。
`frontend/src/api/` 是现有统一出口：`core.js` 与 `index.js` 属公共代码，业务接口文件按根 README 责任表归属。

## 后端（根公共入口 + core/services，当前真实目录）

根公共入口与模型：`backend/main.py`、`backend/config.py`、`backend/database.py`、`backend/models.py`（ORM 总表）、`backend/schemas.py`；
另有根级 `backend/seed_data.py`、`backend/sql_runner.py`。
公共依赖与查询：`backend/core/{deps,events_query}.py`。
公共服务：`backend/core/services/{security,cache,realtime,perf,time_utils}.py`。
工程文件 requirements、.github、CI 仍属公共审核范围。

后端公共入口保留在 `backend/` 根，公共服务已经在 `backend/core/services/`；不要引用旧平铺服务目录，也不要另建平台后端目录。旧平铺路由、服务与 7 个 AI 兼容 shim 已移除。
`backend/integrations/dify_n8n/` 是张亮的集成资产；Dify/n8n 平台 Provider 仍在 `backend/modules/ai_assistant/services/providers/`，归朱明钊。
以上公共代码和前端 platform 的改动都必须在 PR 说明影响范围，并由洪佳琪最终审核；季世庆的总控协调不替代公共代码审核。

## 纪律

- 内核只加不改语义；改接口签名必须全仓 grep 调用点 + 洪佳琪批准。
- 业务表先在 `models.py` 按模块分段注释，建表/改列走内核 review；后续再评估各模块自持表文件。
- 新东西先问“是否 ≥2 模块共用且改坏全挂”，否则进功能模块，不进内核。

## 边界守门（目标）

CI 增加静态检查：`modules/A` 禁止 import `modules/B` 的内部文件，只允许经公开组件/`@/api`/`@/stores`。
