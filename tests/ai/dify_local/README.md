# Dify 本地部署套件（0.10.3，六服务最小栈）

对应 docs/AI对接真实性测试报告_20261101.md 第三节。前置：WSL2 + Docker Desktop
（离线安装用本目录 install_offline.ps1，安装包需自备或从迅雷云盘取）。

## 部署
1. `docker pull` 六个镜像（国内源级联拉取用 pull_watcher.sh/pull_final.sh，见脚本头注释；
   遇限流属正常，等窗口重试）
2. 复制 docker-compose.yaml 到任意工作目录（数据卷在其 ./volumes 下）
3. `docker compose up -d` → 等 1-2 分钟迁移完成
4. `python dify_init.py` —— 自动注册管理员(admin@fabtwin.local / FabTwin#2026!Dify)、
   登录、建应用、生成 API Key（写入 dify_credentials.json）
5. 配置 FabTwin 后端：
   PUT /api/ai/config  {"dify_enabled":true,"dify_base_url":"http://localhost:8088/v1","dify_api_key":"app-xxx"}

## 服务
- Dify 控制台 http://localhost:3088 （web）
- Dify API http://localhost:8088 （console/api 与 /v1 同端口）
- postgres 5433 / redis 6380 / weaviate 8089 / sandbox 8194
