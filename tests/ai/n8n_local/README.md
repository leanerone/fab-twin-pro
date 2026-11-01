# n8n 本地真实对接测试套件

用途：本机起真实 n8n（npm 直装，无需 Docker）后，验证 FabTwin AI → n8n → FabTwin API → Oracle 的完整真实链路。
详见 docs/AI对接真实性测试报告_20261101.md。

## 环境
- n8n 2.8.4 @ E:\AI\fab-ai-services\n8n（Node 20 便携版 @ E:\AI\fab-ai-services\node20，sqlite3 预编译）
- 端口 5678，账号 admin@fabtwin.local / FabTwin#2026!N8n
- 启动：见报告第二节"服务启动命令"

## 步骤
1. `bash n8n_setup.sh <FabTwin管理员token>`  —— owner 初始化 + 建两个 webhook 工作流 + 激活
2. 工作流若需重建（响应模式/字段调整）：`FABTWIN_TOKEN=<token> python n8n_rebuild_workflows.py`
3. `bash ai_real_test.sh` —— 7 项真实性断言（要求 7/7）

## 已知坑（勿踩）
- n8n 工作流内访问 FabTwin 后端必须用 127.0.0.1（Node 20 把 localhost 解析为 ::1，后端只听 IPv4）
- HTTP Request 节点会把 JSON 数组响应拆成多 item，Code 节点用 $input.all() 聚合
- n8n 2.x 删除工作流前必须先 archive；激活端点要带 versionId
- 中文请求体走 --data-binary @文件（UTF-8），Git Bash 内联中文会转码 400
