# FabTwin DB Proxy 启动脚本
# 用法：.\start.ps1
# 首次运行需先：pip install -r requirements.txt

# ====== Oracle 配置 ======
$env:ORACLE_HOST = "localhost"      # 改成你的 Oracle 地址
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE = "orcl"       # 10g/11g 用 sid, 12c+ 用 service_name
$env:ORACLE_USER = "fabtwin"
$env:ORACLE_PASSWORD = "your-password"  # 改成实际密码

# ====== Oracle Thick 模式（10g/11g 需要）======
# $env:ORACLE_CLIENT_DIR = "C:\oracle\instantclient_19_9"

# ====== Informix 配置 ======
$env:INFORMIX_SERVER = "rcms_server"  # 改成实际 server 名
$env:INFORMIX_HOST = "localhost"
$env:INFORMIX_PORT = "9088"
$env:INFORMIX_DATABASE = "rcms"
$env:INFORMIX_USER = "admin"
$env:INFORMIX_PASSWORD = "your-password"  # 改成实际密码

# ====== 安全配置 ======
$env:DB_PROXY_PORT = "8010"
$env:DB_PROXY_TOKEN = "fabtwin-db-proxy-secret"  # 改成你的密钥

Write-Host "启动 FabTwin DB Proxy (端口 $env:DB_PROXY_PORT)..." -ForegroundColor Green
python db_proxy.py
