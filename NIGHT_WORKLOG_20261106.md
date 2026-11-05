# 夜班工作日志 2026-11-06（AI-A）

> 用途：①明早验收清单 ②会话中断后的续接锚点。每完成一项立即更新本文件。
> 计划书：docs/PLAN_AI功能升级与测试迭代_20261106.md
> 状态行格式：[状态] 任务 —— 备注（状态：DONE / IN_PROGRESS / TODO / SKIP）

## 当前状态（续接先看这里）
- **当前任务**：T1（n8n 关键词误触发修复）——即将开始
- **下一个任务**：T2（路由透明化）
- 截止：06:30。到点后执行 T8 收尾。

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
- [TODO] T1 n8n 关键词误触发修复 → middleware.py `_is_n8n_command` + 新测试 test_n8n_command_gate.py
- [TODO] T2 路由透明化 force_provider（后端参数+前端徽标/重答）
- [TODO] T3 会话持久化 AI_CHAT_SESSIONS 表 + LRU 上限
- [TODO] T4 Dify 工具桥 routes/ai_tools_bridge.py + openapi.json 导出
- [TODO] T5 MES 直连适配层 mes_adapter.py（MCP fallback）
- [TODO] T6 安全四项（SSO本机默认/读接口+WS鉴权/debug限admin/登录限流）
- [TODO] T7 前端 defineAsyncComponent + WS 重连重同步
- [TODO] T8 收尾：全量回归+还原配置+拉容器尝试+NIGHT_REPORT_20261106.md

## 提交记录
（随做随记）

## 明早验收指引
1. 看 git log --oneline（每任务一提交）
2. 跑三套回归验证（命令见计划书第2节）
3. 读 NIGHT_REPORT_20261106.md 看遗留项
