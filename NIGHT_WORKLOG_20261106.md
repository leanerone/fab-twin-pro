# 夜班工作日志 2026-11-06（AI-A）

> 用途：①明早验收清单 ②会话中断后的续接锚点。每完成一项立即更新本文件。
> 计划书：docs/PLAN_AI功能升级与测试迭代_20261106.md
> 状态行格式：[状态] 任务 —— 备注（状态：DONE / IN_PROGRESS / TODO / SKIP）

## 当前状态（续接先看这里）
- **夜班主体施工已完成（01:15）**，全部交付见 NIGHT_REPORT_20261106.md
- 剩余时段：cron 每30分钟唤醒做环境健康巡检（服务/容器/端口存活）；
  若发现故障按下方「环境快照」恢复；如有新的可安全落地的改进点自行评估执行
- **明早验收入口：NIGHT_REPORT_20261106.md**（三个行动项在第六节）

## 第二轮计划（00:50 追加——首轮 T1-T7 提前完成，按用户约定自动续接 P1 提升项）
- R1 告警智能诊断工具 `diagnose_alarm`：机台告警→聚合 TOP 告警码→关联历史事件时间线→产出诊断式回答；进工具桥自动暴露
- [DONE] R1 ✅ fb6916d —— diagnose_alarm 11/11（频次/趋势/KB建议/优先处置）；顺带修复两个被掩盖存量bug：
  机台域告警 tuple绑定DPY-3002静默降级（expanding bindparam 修复）+ VFEI信封 data 子对象未解包（get_machine_alarms 一并修复）
- R2 对比工具 `compare_machines`：多机台产量/状态/告警横向对比，支撑"对比分析"类多跳问题
- R3 小修批：perf.py sql 计数 contextvars 化（恒0问题）/ events.py 超5000返回 truncated 标志 / machines.py 增删改后失效 machine_state 缓存
- R4 OHT N+1：oht.py 逐台查询改 MAX+JOIN 一次取回
- [DONE] R2 ✅ d2b45e6 —— compare_machines 8/8（表结构/降序/参数归一/自动选机台），bridge 18/18，real_data 21/21
- [DONE] R3 ✅ 032cbfe —— perf计数ContextVar化(test_perf_ctx 4/4)/events 5000截断warning/机台写路径失效缓存，回归 security13+bridge18+chain20
- [DONE] R4 ✅ 951eaa0 (OHT MAX+JOIN，接口验证 2台/去重正确/字段完整)
- [DONE] R5+R6 ✅ d56fd97 —— 全局引擎选择重启生效修复(R6真bug)+缓存扩容256+WS半关闭收口+生产部署清单文档
- [DONE] T8 收尾 ✅ —— 11测试文件162断言全绿 + chain 20/20 + n8n真实链路7/7 + vite build ✓
  环境终态：8002(新代码+全局Dify+n8n启用) / 5173前端 / Dify+n8n容器 / 8003+8901+8902测试实例 全部在跑

## 环境快照（00:25）
- 后端 8002（开发）与 8003（测试用实例）已启动，日志 /tmp/backend_night.log、/tmp/backend8003.log
- 替身：8901=MOCK_TOOL_MODE=1（给 real_data）、8902=普通模式（给 chain 20 例）
- Oracle XE 运行中；Dify(8080)/n8n(5678) 容器**未运行**
- 基线：real_data 21/21 ✅　sql_guard 29/29 ✅　chain 20/20 ✅
- ⚠️ 踩坑记录：chain 测试会把 DB 里 AI 配置改成替身且**不还原**——已手动还原（provider=dify，
  dify_base_url=http://localhost:8080/v1，n8n_enabled=false）。全部测试跑完后需再次还原！
  还原脚本模式见 /tmp/restore_ai_cfg.py（会话丢失则重写：读 E:/AI/fab-ai-services/dify_credentials.json）

## 任务状态
- [DONE] P0 基线：三套回归全绿（21+29+20）
- [DONE] P0 计划文档 docs/PLAN_AI功能升级与测试迭代_20261106.md
- [DONE] T1 ✅ 5bf38b0 —— n8n 关键词误触发修复：三层收紧（显式前缀/动名强匹配/弱词让路），test_n8n_command_gate 23/23，链路回归 20/20
- [TODO] T2 路由透明化 force_provider（后端参数+前端徽标/重答）
- [DONE] T2 ✅ efe3371 —— force_provider(dify/llm/local) 后端双入口+前端换引擎重答按钮，test_force_provider 11/11，vite build OK
- [TODO] T3 会话持久化 AI_CHAT_SESSIONS 表 + LRU 上限
- [DONE] T3 ✅ 181da1c —— AI_CHAT_SESSIONS 表(sql/v2.21)+每轮落库+重启恢复+LRU200/conv_map500，test_session_persist 12/12，链路 20/20
- [TODO] T4 Dify 工具桥 routes/ai_tools_bridge.py + openapi.json 导出
- [DONE] T4 ✅ aad1781 —— 工具桥REST(12工具)+OpenAPI导出+修复describe stale import(.ai_schema→.schema)，test_tools_bridge 18/18，回归 21/21+29/29。
  ※ Dify 接入：Dify→工具→自定义→导入OpenAPI(粘 openapi.json)→鉴权 Bearer 填服务账号 token→应用挂工具
- [TODO] T5 MES 直连适配层 mes_adapter.py（MCP fallback）
- [DONE] T5 ✅ acdd268 —— MES_DB_* 直连优先+MCP自动兜底+字段标准化（内置别名/COLUMN_MAP覆盖），test_mes_adapter 12/12，real_data 21/21
- [TODO] T6 安全四项（SSO本机默认/读接口+WS鉴权/debug限admin/登录限流）
- [TODO] T7 前端 defineAsyncComponent + WS 重连重同步
- [DONE] T7 ✅ e1e5c1b —— 悬浮球+详情页5重视图异步化（index包107KB→29KB）、WS重连重拉快照、半开看门狗90s、cache热路径日志降噪
- [TODO] T8 收尾：全量回归+还原配置+拉容器尝试+NIGHT_REPORT_20261106.md

## 提交记录
（随做随记）

## 明早验收指引
1. 看 git log --oneline（每任务一提交）
2. 跑三套回归验证（命令见计划书第2节）
3. 读 NIGHT_REPORT_20261106.md 看遗留项
