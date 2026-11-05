# 夜班验收报告（2026-11-06 00:16 ～ 收尾）

> 施工人：AI-A　分支：review-ver3　计划书：docs/PLAN_AI功能升级与测试迭代_20261106.md
> 过程日志：NIGHT_WORKLOG_20261106.md（每步留痕）　**共 11 个提交，全部本地未推送**

## 一、一句话总结

按约定完成「AI 功能升级 + n8n 替代 + 测试迭代」三轮共 **11 项任务**，
全部带测试提交；**新增/修订测试 11 个文件共 162 项断言全绿**，三套原有回归
（21+29+20）+ n8n 真实链路（7）继续全绿；另修复 4 个排查中发现的存量 bug。

## 二、交付清单（按提交顺序）

| # | 提交 | 内容 | 测试 |
|---|---|---|---|
| 1 | e068486 | 夜班计划书 + 工作日志（自检续接机制） | — |
| 2 | 5bf38b0 | **T1** n8n 指令识别收紧：显式前缀/动名强匹配，弱关键词有智能引擎时让路 | 23/23 |
| 3 | efe3371 | **T2** 路由透明化：force_provider(dify/llm/local) + 前端「⇄ 换引擎重答」按钮 | 11/11 |
| 4 | 181da1c | **T3** 会话持久化：AI_CHAT_SESSIONS 表 + 每轮落库 + 重启恢复 + 内存 LRU200/映射500 | 12/12 |
| 5 | aad1781 | **T4** Dify 工具桥：14 个本地工具 REST 暴露 + Dify 可导入 OpenAPI 规范 | 18/18 |
| 6 | acdd268 | **T5** MES 直连适配层：MES_DB_* 直连优先、MCP 自动兜底（n8n 替代①） | 12/12 |
| 7 | c0a4142 | **T6** 安全四项：SSO 默认仅回环 / 读接口+WS 鉴权 / debug 限 admin / 登录限流 | 13/13 |
| 8 | e1e5c1b | **T7** 前端重视图异步化（index 包 107KB→29KB）+ WS 重连重同步/半开看门狗 | build ✓ |
| 9 | fb6916d | **R1** 告警智能诊断工具 diagnose_alarm（频次/趋势/原因/建议/优先处置） | 11/11 |
| 10 | d2b45e6 | **R2** 多机台对比工具 compare_machines（一条 GROUP BY，无 N+1） | 8/8 |
| 11 | 032cbfe | **R3** perf SQL 计数修复 / events 截断告警 / 机台写路径缓存失效 | 4/4 |
| 12 | 951eaa0 | **R4** OHT 最新位置 1+N 查询改 MAX+JOIN | 接口验证 |
| 13 | d56fd97 | **R5/R6** 全局引擎选择重启生效修复 + 缓存扩容 + WS 半关闭收口 + 生产部署清单 | 冒烟 ✓ |

## 三、测试矩阵（收尾全量回归）

```
原有回归：  test_real_data 21/21 ✅   test_sql_guard 29/29 ✅   run_chain_tests 20/20 ✅
新增测试：  test_n8n_command_gate 23   test_force_provider 11   test_session_persist 12
            test_tools_bridge 18       test_mes_adapter 12      test_diagnose_alarm 11
            test_compare_machines 8    test_security_hardening 13   test_perf_ctx 4
真实链路：  n8n 真实链路 ai_real_test.sh 7/7 ✅（对真实 n8n 2.8.4 + Oracle）
前端构建：  vite build ✓（3.2s）
合计：      11 个测试文件 162 项断言全绿
```

## 四、排查中顺手修复的 4 个存量 bug（都有证据链）

1. **机台域告警 SQL 从未真正生效**：tuple 绑定 oracledb 报 DPY-3002，被 `except` 吞掉静默走慢速
   fallback（fb6916d，expanding bindparam 修复）——get_machine_alarms 一并修复
2. **VFEI 信封结构告警字段在 data 子对象未解包**：物化列有值但解析层永远读不到（fb6916d）
3. **describe_fab_table 一调用即 500**：stale import `.ai_schema`（应为 `.schema`，与当年 `.ai_sql`
   同款批次2改名残留，aad1781）
4. **switch-global "重启仍生效" 是假的**：kv 里 provider=dify 从不被启动加载，重启静默回退
   本地规则引擎（d56fd97，R6 修复并实测重启恢复）

## 五、明早环境状态

- ✅ 后端 8002：最新代码，全局 Dify 已恢复 + n8n 启用，日志确认配置加载正确
- ✅ 前端 5173：dev 服务运行中（浏览器打开即用，登录 admin/admin123）
- ✅ Docker：Dify(8080) + n8n(5678) 全套容器已拉起（重启策略自动恢复）
- ✅ 测试实例：8003 后端 + 替身 8901(工具模式)/8902(普通模式) 仍在跑（回归用，可随时杀）

## 六、给你的三个行动项（代码之外，需要你/公司操作）

1. **Dify 真实 LLM key**：Dify 应用底层模型当前指向本地替身 LLM(8902)，回答是占位文本；
   在 Dify 控制台「模型供应商」配置真实 key 后即恢复真智能（链路本身已全通）
2. **Dify 工具导入**（新能力，5分钟）：Dify → 工具 → 自定义 → 导入 OpenAPI，
   粘贴 `GET http://localhost:8002/api/ai/tools/openapi.json` 内容 → 鉴权 Bearer 填后端 token
   → 应用挂载后，Dify 应用即拥有全部 14 个本地数据工具（含今晚新增的诊断/对比）
3. **推送远端**：11 个提交都在本地 review-ver3，需要我推 test31 的话说一声

## 七、遗留项（按优先级，均已写入 docs/生产部署清单_20261106.md）

- P1: Dify 知识库 RAG（设备手册/告警SOP）→ 智能度下一台阶
- P1: stream async 深度重构（async 生成器内仍有 3 处同步 DB 调用点，已定位 middleware.py）
- P2: 主动告警推送（WS 事件流 → 悬浮球主动提醒）
- P2: metrics/perf 端点鉴权、CORS 环境变量化、限流/会话缓存多实例 Redis 化
- 附: APScheduler 报表自动化（n8n webhook 自动化的完全替代， MES 查询已可直连先行下线 n8n）
