# 模块⑥ 平台内核（platform / backend core）

- **负责人**：洪佳琪
- **定位**：被 ≥2 个功能模块共用、改坏会全体受影响的底座。刻意保持小，不做业务。

## 前端

```
platform/frontend/
  shell/        AppHeader；App.vue/router/main.js 仍在 src/ 根（应用装配表）
  core/composables/  useThree、useRafLoop、threeDispose、useWebSocket（跨模块共享）
```
另有内核入口（在 src/ 根，归此模块）：`api/`（barrel，{ api } 统一出口）、
`stores/{app,auth,model}`、`router/`、`utils/`、`styles/`、`configs/`。

## 后端（平铺在 backend/，CODEOWNERS 按文件归此模块）

`main.py / config.py / database.py / models.py(ORM 总表) / schemas.py`、
`core/`（events_query、deps）、
`services/{security,cache,realtime,perf,time_utils}.py`；工程文件 requirements、.github、CI。

## 纪律

- 内核只加不改语义；改接口签名必须全仓 grep 调用点 + 洪佳琪批准。
- 业务表先在 `models.py` 按模块分段注释，建表/改列走内核 review；后续再评估各模块自持表文件。
- 新东西先问“是否 ≥2 模块共用且改坏全挂”，否则进功能模块，不进内核。

## 边界守门（目标）

CI 增加静态检查：`modules/A` 禁止 import `modules/B` 的内部文件，只允许经公开组件/`@/api`/`@/stores`。
