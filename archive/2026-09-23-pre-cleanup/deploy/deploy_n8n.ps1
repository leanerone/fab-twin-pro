# ============================================================
# FabTwin Pro - n8n 本地服务器一键部署脚本 (PowerShell)
# 版本: v1.0  日期: 2026-08-28
# 用途: 在 Windows 服务器上通过 Docker 一键拉起 n8n 服务
#       含 PostgreSQL (持久化) + n8n 主容器 + 可选 Nginx 反代
# 使用:
#   1. 以管理员运行:
#      powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action install
#   2. 导入工作流:
#      powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action import
# ============================================================

param(
    [string]$Action = "install",    # install | start | stop | restart | status | logs | import | uninstall
    [string]$N8nDir = $(if ($env:N8N_DOCKER_DIR) { $env:N8N_DOCKER_DIR } else { Join-Path $PSScriptRoot "n8n" }),
    [string]$HostPort = "5678",     # n8n Web 对外端口
    [string]$PgPort = "5434",       # PostgreSQL 端口（避免与 Dify 5433 冲突）
    [string]$Version = "latest",    # n8n 版本 tag
    [string]$N8nUser = "admin",     # n8n 主账号
    [string]$N8nPassword = "FabTwin#2026!N8n",  # n8n 密码
    [string]$VolumeRoot = $(Join-Path $N8nDir "volumes"),
    [string]$FabTwinApiUrl = "http://localhost:8002"  # FabTwin 后端地址（工作流模板中使用）
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Ensure-Dir($path) { if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path -Force | Out-Null } }

# ---------------- 环境检查 ----------------
function Invoke-PrereqCheck {
    Write-Step "检查前置依赖 (Docker / Docker Compose)"
    if (-not (Test-Cmd "docker")) { Write-Fail "未检测到 docker 命令，请先安装 Docker Desktop" }
    try { $v = & docker compose version 2>&1; if ($LASTEXITCODE -ne 0) { throw }; Write-Ok "Docker Compose: $v" }
    catch { Write-Fail "docker compose 不可用" }
    try { $null = & docker info 2>&1; if ($LASTEXITCODE -ne 0) { throw }; Write-Ok "Docker daemon 运行正常" }
    catch { Write-Fail "Docker daemon 未启动" }
}

# ---------------- 生成 compose + .env ----------------
function New-ComposeFiles {
    Write-Step "生成 n8n Docker Compose 文件: $N8nDir"
    Ensure-Dir $N8nDir
    Ensure-Dir $VolumeRoot
    Ensure-Dir (Join-Path $VolumeRoot "db")
    Ensure-Dir (Join-Path $VolumeRoot "n8n")

    $composeFile = Join-Path $N8nDir "docker-compose.yaml"
    $envFile = Join-Path $N8nDir ".env"

    # docker-compose.yaml
    $yaml = @"
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${N8nUser}
      POSTGRES_PASSWORD: ${N8nPassword}
      POSTGRES_DB: n8n
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - ${VolumeRoot}\db:/var/lib/postgresql/data/pgdata
    ports:
      - "${PgPort}:5432"
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${N8nUser}"]
      interval: 5s
      timeout: 3s
      retries: 10

  n8n:
    image: n8nio/n8n:${Version}
    environment:
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=${N8nUser}
      - DB_POSTGRESDB_PASSWORD=${N8nPassword}
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8nUser}
      - N8N_BASIC_AUTH_PASSWORD=${N8nPassword}
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://0.0.0.0:${HostPort}/
      - N8N_EDITOR_BASE_URL=http://0.0.0.0:${HostPort}
      - GENERIC_TIMEZONE=Asia/Shanghai
      - TZ=Asia/Shanghai
      - N8N_LOG_LEVEL=info
      - N8N_METRICS=true
      - FABTWIN_API_URL=${FABTWIN_API_URL}
      - N8N_WEBHOOK_SECRET=${N8N_WEBHOOK_SECRET}
    ports:
      - "${HostPort}:5678"
    volumes:
      - ${VolumeRoot}\n8n:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy
    restart: always
"@
    Set-Content -Path $composeFile -Value $yaml -Encoding UTF8

    # .env
    $envContent = @"
N8N_USER=${N8nUser}
N8N_PASSWORD=${N8nPassword}
N8N_HOST_PORT=${HostPort}
N8N_PG_PORT=${PgPort}
N8N_VERSION=${Version}
FABTWIN_API_URL=${FabTwinApiUrl}
N8N_WEBHOOK_SECRET=
"@
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Write-Ok "docker-compose.yaml 和 .env 已生成"
    return $composeFile
}

# ---------------- 主动作 ----------------
function Invoke-Install {
    Invoke-PrereqCheck
    $composeFile = New-ComposeFiles
    Write-Step "拉取镜像 + 启动 n8n（首次 2~5 分钟）"
    Push-Location (Split-Path $composeFile -Parent)
    try {
        & docker compose -f $composeFile --env-file .env pull
        & docker compose -f $composeFile --env-file .env up -d
        if ($LASTEXITCODE -ne 0) { Write-Fail "n8n 启动失败" }
    } finally { Pop-Location }
    Write-Ok "n8n 服务已启动"
    Start-Sleep 5
    Show-Summary
}

function Invoke-Start    { $f = Join-Path $N8nDir "docker-compose.yaml"; & docker compose -f $f --env-file (Join-Path $N8nDir ".env") start }
function Invoke-Stop     { $f = Join-Path $N8nDir "docker-compose.yaml"; & docker compose -f $f --env-file (Join-Path $N8nDir ".env") stop }
function Invoke-Restart  { $f = Join-Path $N8nDir "docker-compose.yaml"; & docker compose -f $f --env-file (Join-Path $N8nDir ".env") restart }
function Invoke-Status   { $f = Join-Path $N8nDir "docker-compose.yaml"; & docker compose -f $f --env-file (Join-Path $N8nDir ".env") ps }
function Invoke-Logs     { $f = Join-Path $N8nDir "docker-compose.yaml"; & docker compose -f $f --env-file (Join-Path $N8nDir ".env") logs --tail 100 -f }

function Invoke-Uninstall {
    $f = Join-Path $N8nDir "docker-compose.yaml"
    Write-Warn "将停止并卸载所有 n8n 容器和卷，5秒后继续 (Ctrl+C 取消)..."
    Start-Sleep 5
    & docker compose -f $f --env-file (Join-Path $N8nDir ".env") down -v
    Write-Ok "n8n 已卸载"
}

# ---------------- 导入工作流模板 ----------------
function Invoke-Import {
    Write-Step "导入 5 个 FabTwin 工作流模板到 n8n"
    $templateDir = Join-Path $PSScriptRoot "..\docs\integration\n8n"
    if (-not (Test-Path $templateDir)) {
        $templateDir = Join-Path $PSScriptRoot "..\..\docs\integration\n8n"
    }
    if (-not (Test-Path $templateDir)) {
        Write-Fail "找不到工作流模板目录 docs/integration/n8n/"
    }

    $templates = Get-ChildItem $templateDir -Filter "*.json" | Sort-Object Name
    Write-Host "  找到 $($templates.Count) 个模板文件:"
    $templates | ForEach-Object { Write-Host "    - $($_.Name)" }

    $n8nUrl = "http://localhost:$HostPort"
    $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${N8nUser}:${N8nPassword}"))
    $headers = @{ "Authorization" = "Basic $auth"; "Content-Type" = "application/json" }

    # 检查 n8n 是否在线
    try {
        $null = Invoke-RestMethod -Uri "$n8nUrl/healthz" -Method GET -TimeoutSec 5
        Write-Ok "n8n 服务在线"
    } catch {
        Write-Fail "n8n 服务不可达（$n8nUrl），请先执行 -Action install"
    }

    $imported = 0; $failed = 0
    foreach ($t in $templates) {
        $name = $t.BaseName
        Write-Host "`n  导入: $name ..."
        try {
            $content = Get-Content $t.FullName -Raw -Encoding UTF8
            # n8n API POST /api/v1/workflows 需要认证头
            $body = $content
            $resp = Invoke-RestMethod -Uri "$n8nUrl/api/v1/workflows" -Method POST -Headers $headers -Body $body -TimeoutSec 30
            $wfId = $resp.id ?? $resp.data?.id ?? "?"
            Write-Ok "  $name -> workflow ID: $wfId"
            $imported++
        } catch {
            $errMsg = $_.Exception.Message
            if ($errMsg -match "409|already.*exist|conflict") {
                Write-Warn "  $name 已存在，跳过"
                $imported++
            } else {
                Write-Warn "  $name 导入失败: $errMsg"
                $failed++
            }
        }
    }

    Write-Host "`n  导入结果: 成功 $imported / 失败 $failed (共 $($templates.Count))"
    if ($failed -eq 0) { Write-Ok "全部工作流导入完成！" }
    else { Write-Warn "部分失败，可在 n8n Web UI 手动导入" }
}

function Show-Summary {
    $ip = "localhost"; try { $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' -and $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress } catch {}
    Write-Host "`n========================================================"
    Write-Host "  n8n 部署完成  " -ForegroundColor Green
    Write-Host "========================================================"
    Write-Host "  管理后台: http://$ip`:$HostPort"
    Write-Host "  账号/密码: $N8nUser / $N8nPassword"
    Write-Host "  PostgreSQL: $ip`:$PgPort (user/db: $N8nUser / n8n)"
    Write-Host "  数据卷根: $VolumeRoot"
    Write-Host "`n  下一步: 导入工作流模板"
    Write-Host "    .\deploy_n8n.ps1 -Action import"
    Write-Host "`n  管理命令:"
    Write-Host "    状态: .\deploy_n8n.ps1 status"
    Write-Host "    日志: .\deploy_n8n.ps1 logs"
    Write-Host "    重启: .\deploy_n8n.ps1 restart"
    Write-Host "========================================================`n"
}

# ---------------- 分发 ----------------
switch ($Action) {
    "install"   { Invoke-Install }
    "start"     { Invoke-Start }
    "stop"      { Invoke-Stop }
    "restart"   { Invoke-Restart }
    "status"    { Invoke-Status }
    "logs"      { Invoke-Logs }
    "import"    { Invoke-Import }
    "uninstall" { Invoke-Uninstall }
    default     { Write-Fail "未知 Action: $Action，可选: install|start|stop|restart|status|logs|import|uninstall" }
}
