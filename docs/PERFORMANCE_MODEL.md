# FabTwin 性能模型

> 建立日期：2026-10-29　|　版本：1.0
> 目的：把"性能"从"手工 curl + 肉眼看时间"变成**可复现、可比对、可拦截**的工程实践。

---

## 一、为什么要有性能模型

此前项目里的性能结论有两个共同问题：

1. **口径不统一**：有人用浏览器 Network 面板，有人用 `curl -w`，有人跑离线报表，
   同一接口能得出差几倍的数字，无法判断"这次改动是变好还是变坏"
2. **不可拦截**：性能退化只有到了现场才被发现。F5 14s / F8 43s / F7 60s 超时
   这类问题都是在量产后才暴露的

性能模型要解决的就是这两点：**统一口径 + 设阈值 + 自动化拦截**。

---

## 二、三层度量

| 层级 | 采集方式 | 用途 |
|---|---|---|
| **服务端耗时** | `services/perf.py` 的 HTTP 中间件 | 排除网络与客户端噪声，反映真实处理耗时 |
| **服务端 SQL** | SQLAlchemy `before/after_cursor_execute` 钩子 | 定位慢查询、统计每请求 SQL 次数（发现 N+1） |
| **客户端耗时** | `tests/perf/benchmark.py` | 用户实际感受到的端到端耗时 |

两个口径都要看：服务端 P95 正常但客户端慢 → 网络/序列化问题；
客户端 P95 正常但服务端慢 → 缓存命中掩盖了冷路径。

---

## 三、核心指标定义

| 指标 | 定义 | 为什么用它 |
|---|---|---|
| **P95** | 95% 请求的耗时不超过该值 | 平均值会被大量快请求拉低，掩盖长尾。看板类系统用户感知的是"最慢的那几次" |
| **冷态** | 进程启动后 / 缓存失效后的首次请求 | 决定"用户第一次打开页面等多久" |
| **热态** | 缓存命中后的请求 | 决定"日常刷新的手感" |
| **每请求 SQL 数** | 一次请求执行的 SQL 条数 | 突然变多通常意味着引入了 N+1 |
| **慢查询** | 单条 SQL 超过阈值（默认 500ms） | 直接指向缺失索引或全表扫 |

> **不要只看平均值。** 一个接口 100 次里 95 次 50ms、5 次 8s，平均值 450ms 看着能接受，
> 但那 5 次会让用户觉得系统"卡死了"。

---

## 四、怎么用

### 1. 实时观测

```powershell
# 性能快照（按 P95 倒序）
curl http://localhost:8002/api/metrics/perf

# 清零（跑基准前先清，避免被历史请求污染）
curl -X POST http://localhost:8002/api/metrics/perf/reset
```

返回示例：
```json
{
  "routes": {
    "GET /api/lots": {"count": 8, "errors": 0, "p50_ms": 87.7, "p95_ms": 87.7, "max_ms": 101.9}
  },
  "slow_sql": [{"sql": "SELECT ...", "ms": 812.4}]
}
```

### 2. 跑基准

```powershell
python tests/perf/benchmark.py                      # local 档，10 轮
python tests/perf/benchmark.py --profile prod       # 量产档
python tests/perf/benchmark.py --rounds 20 --machine OXE-51
```

超出预算会**退出码 1**，可以直接挂进 CI。

### 3. 端到端链路验证

```powershell
python tests/perf/test_poller_e2e.py
```

验证"外部直接写库 → 轮询 → WebSocket 推送"这条生产链路。
> 这个测试存在的原因：db_poller 曾长期从未启动，但因为走 rvmessages API 注入的事件
> 会绕过轮询直接广播，端到端测试一直全绿，问题始终没被发现。**测试不能只覆盖
> 绕开被测组件的旁路。**

---

## 五、预算表

在 `tests/perf/budget.json`，按环境分档（本机小库与量产大库量级完全不同，不能用同一套阈值）。

### local 档（本机 Oracle XE，2026-10-29 实测基线）

| 端点 | P95 实测 | 预算 |
|---|---|---|
| GET /api/machines | 166ms | 800ms |
| GET /api/machines/stats | 170ms | 800ms |
| GET /api/floors | 183ms | 600ms |
| GET /api/alarms | 206ms | 800ms |
| GET /api/lots | 261ms | 1000ms |
| GET /api/models | 181ms | 600ms |
| GET /api/events/latest | 175ms | 800ms |
| GET /api/oht/positions | 172ms | 500ms |
| GET /api/history/{tool_id} | 195ms | 2500ms |
| GET /api/history/{tool_id}/timeline | 183ms | 2500ms |

> 注意：本机库仅约 2000 行事件，**这个基线不能代表量产**。量产库 `DT_EVENT_RAW` 千万级，
> 冷态 7.3~34s 是此前实测过的量级。prod 档阈值需要在有真实数据量后重新标定。

---

## 六、已知的性能风险点（本次未修，按优先级排）

| # | 风险 | 位置 | 影响 |
|---|---|---|---|
| 1 | `ai_middleware.py` 13 处同步 `requests`，timeout 最高 120s | `services/ai_middleware.py` | 占满 FastAPI 默认 40 线程池，拖垮所有同步端点。应改 `httpx.AsyncClient` |
| 2 | `machine_state_ttl` 缓存 key 为全机台 id 拼接，`maxsize=32` | `routers/machines.py:113` | 浏览 32+ 台机台后全量缓存被逐出，冷态重算 |
| 3 | 写后不失效 | `services/cache.py` | 新事件写入后状态最长 60s 陈旧 |
| 4 | 7 个 async 端点在事件循环里做同步 DB/文件 IO | `routers/uploads.py` | 上传期间冻结整个后端 |
| 5 | KPI 用 `LIMIT 5000/10000` 截断 | `routers/machines.py:210/244` | 千万级库上 KPI 静默偏低；应改 SQL 聚合 |
| 6 | N+1 查询 | `floors.py:28`、`users.py:254/383` | 列表接口随数据量线性变慢 |

---

## 七、前端性能约定（本次已落地）

| 约定 | 落地位置 |
|---|---|
| 渲染循环必须受管：后台标签页暂停、卸载即清理 | `composables/useRafLoop.js` |
| Three.js 场景必须整体释放，不能只 `renderer.dispose()` | `composables/threeDispose.js` |
| 定时器必须受管 | `useRafLoop.js` 的 `useInterval` |
| 高频动画进度**不要**放响应式对象 | `FloorPlan.vue` 天车进度改普通对象 + 15fps 推给模板 |
| 生产构建保留 `console.error` | `vite.config.js` |

---

## 八、回归检查清单

改完性能相关代码后，按顺序跑：

```powershell
# 1. 清零并跑基准
python tests/perf/benchmark.py --rounds 15

# 2. 看慢查询有没有新增
curl http://localhost:8002/api/metrics/perf | findstr slow_sql

# 3. 前端构建（确认没引入体积回归）
cd frontend && npm run build

# 4. SVG/Motion 一致性（新增机型时）
python -m models.svg_kit.validate <机台.svg> <机台.motion.json>
```
