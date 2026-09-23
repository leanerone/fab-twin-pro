# ============================================================
# FabTwin Pro - Dify 本地服务器一键部署脚本 (PowerShell)
# 版本: v1.0  日期: 2026-08-28
# 用途: 在 Windows / Linux 服务器上通过 Docker Compose
#       一键拉起 Dify 全套服务 (PostgreSQL + Redis + Weaviate
#       + Sandbox + Web + API + Worker + Nginx)
# 使用:
#   1. 先配置 $env:DIFY_DOCKER_DIR 与各端口变量
#   2. 以管理员/root运行:  powershell -ExecutionPolicy Bypass -File .\deploy_dify.ps1
# ============================================================

param(
    [string]$Action = "install",   # install | start | stop | restart | status | uninstall | logs
    [string]$DifyDir = $(if ($env:DIFY_DOCKER_DIR) { $env:DIFY_DOCKER_DIR } else { Join-Path $PSScriptRoot "dify" }),
    [string]$Version = "0.10.3",   # Dify 稳定版本 tag
    [string]$HostPort = "8088",    # Web 对外端口
    [string]$PgPort = "5433",      # PostgreSQL 端口（避免冲突）
    [string]$RedisPort = "6380",   # Redis 端口
    [string]$VolumeRoot = $(Join-Path $DifyDir "volumes"),
    [switch]$SkipSSL = $true
)

$ErrorActionPreference = "Stop"

# ---------------- 辅助函数 ----------------
function Write-Step($msg) { Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Dir($path) {
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
}

# ---------------- 环境检查 ----------------
function Invoke-PrereqCheck {
    Write-Step "检查前置依赖 (Docker / Docker Compose / 内存 / 磁盘)"

    if (-not (Test-Cmd "docker")) {
        Write-Fail "未检测到 docker 命令，请先安装 Docker Desktop (Windows) 或 docker-ce (Linux)。下载: https://www.docker.com/products/docker-desktop/"
    }

    try {
        $ver = & docker compose version 2>&1
        if ($LASTEXITCODE -ne 0) { throw }
        Write-Ok "Docker Compose 版本: $ver"
    } catch {
        Write-Fail "未检测到 docker compose 子命令，请升级 Docker 到最新版"
    }

    try {
        $null = & docker info 2>&1
        if ($LASTEXITCODE -ne 0) { throw }
        Write-Ok "Docker daemon 运行正常"
    } catch {
        Write-Fail "Docker daemon 未启动。请先启动 Docker Desktop / dockerd"
    }

    # 内存检查 (Windows)
    try {
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $memGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        Write-Host "  系统内存: $memGB GB"
        if ($memGB -lt 7) { Write-Warn "可用内存偏低 ($memGB GB)，建议 >= 8GB，否则服务可能 OOM" }
    } catch {}

    # 磁盘检查
    $d = Split-Path $DifyDir -Qualifier
    try {
        $disk = Get-PSDrive ($d -replace ':','') -ErrorAction Stop
        $freeGB = [math]::Round($disk.Free / 1GB, 1)
        Write-Host "  $d 盘剩余空间: $freeGB GB"
        if ($freeGB -lt 20) { Write-Warn "磁盘空间不足，建议剩余 >= 50GB 存放镜像、向量数据库和知识库文件" }
    } catch {}
}

# ---------------- 下载 / 初始化 ----------------
function Invoke-PrepareDirs {
    Write-Step "初始化 Dify 目录: $DifyDir"
    Ensure-Dir $DifyDir
    Ensure-Dir (Join-Path $DifyDir "docker")
    Ensure-Dir $VolumeRoot

    $composeFile = Join-Path $DifyDir "docker/docker-compose.yaml"
    $envFile     = Join-Path $DifyDir "docker/.env"

    # 若 compose 不存在，尝试从官方仓库获取 (失败时则直接内置生成)
    if (-not (Test-Path $composeFile)) {
        Write-Host "  未找到 docker-compose.yaml，尝试拉取官方仓库..."
        try {
            Push-Location $DifyDir
            if (-not (Test-Path (Join-Path $DifyDir ".git"))) {
                & git init -q 2>&1 | Out-Null
                & git remote add origin https://github.com/langgenius/dify.git 2>&1 | Out-Null
            }
            & git fetch --depth 1 origin tags/$Version 2>&1 | Out-Null
            & git checkout FETCH_HEAD -- docker 2>&1 | Out-Null
            Pop-Location
            Write-Ok "已从官方仓库 (tag=$Version) 拉取 docker/ 目录"
        } catch {
            Pop-Location
            Write-Warn "Git 拉取失败，将生成内置的 docker-compose.yaml 与 .env 模板"
            New-BuiltinCompose $composeFile
            New-BuiltinEnv $envFile
        }
    } else {
        Write-Ok "docker-compose.yaml 已存在，跳过下载"
    }

    # 生成 .env 覆盖（端口/卷根）
    Update-DifyEnv $envFile
    return $composeFile, $envFile
}

function New-BuiltinCompose($path) {
    $yaml = @'
# Dify built-in compose (FabTwin Pro 专用裁剪版)
# 若需要完整版本请执行: git clone --depth 1 --branch 0.10.3 https://github.com/langgenius/dify.git
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-difyaipass}
      POSTGRES_DB: ${POSTGRES_DB:-dify}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - ${VOLUME_ROOT}/db/data:/var/lib/postgresql/data/pgdata
    ports:
      - "${DB_PORT:-5433}:5432"
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 5s; timeout: 3s; retries: 10

  redis:
    image: redis:6-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-difyredis}
    volumes:
      - ${VOLUME_ROOT}/redis:/data
    ports:
      - "${REDIS_PORT:-6380}:6379"
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s; timeout: 3s; retries: 10

  weaviate:
    image: semitechnologies/weaviate:1.25.4
    environment:
      QUERY_DEFAULTS_LIMIT: 20
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
      PERSISTENCE_DATA_PATH: "/var/lib/weaviate"
      CLUSTER_HOSTNAME: 'node1'
      DISABLE_TELEMETRY: 'true'
    volumes:
      - ${VOLUME_ROOT}/weaviate:/var/lib/weaviate
    restart: always

  sandbox:
    image: langgenius/dify-sandbox:0.2.1
    environment:
      API_KEY: ${SANDBOX_API_KEY:-sbs-dify-fabtwin}
      GIN_MODE: release
      WORKER_TIMEOUT: 15
    restart: always

  web:
    image: langgenius/dify-web:${DIFY_VERSION:-0.10.3}
    environment:
      API_URL: http://api:5001
      APP_NAME: FabTwin Dify
    depends_on:
      - api
    ports:
      - "${LISTEN_PORT:-8088}:3000"
    restart: always

  api:
    image: langgenius/dify-api:${DIFY_VERSION:-0.10.3}
    environment: &api_env
      MODE: api
      SECRET_KEY: ${SECRET_KEY:-sk-fabtwin-dify-xxxxxxxxxxxxxxxx}
      DB_USERNAME: ${POSTGRES_USER:-postgres}
      DB_PASSWORD: ${POSTGRES_PASSWORD:-difyaipass}
      DB_HOST: db
      DB_PORT: 5432
      DB_DATABASE: ${POSTGRES_DB:-dify}
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: ${REDIS_PASSWORD:-difyredis}
      WEAVIATE_ENDPOINT: http://weaviate:8080
      CODE_EXECUTION_ENDPOINT: http://sandbox:8194
      CODE_EXECUTION_API_KEY: ${SANDBOX_API_KEY:-sbs-dify-fabtwin}
      TZ: Asia/Shanghai
    depends_on:
      db:        { condition: service_healthy }
      redis:     { condition: service_healthy }
      weaviate:  { condition: service_started }
      sandbox:   { condition: service_started }
    volumes:
      - ${VOLUME_ROOT}/app/storage:/app/api/storage
    restart: always

  worker:
    image: langgenius/dify-api:${DIFY_VERSION:-0.10.3}
    environment:
      <<: *api_env
      MODE: worker
    depends_on:
      api: { condition: service_started }
    volumes:
      - ${VOLUME_ROOT}/app/storage:/app/api/storage
    restart: always
'@
    Set-Content -Path $path -Value $yaml -Encoding UTF8
}

function New-BuiltinEnv($path) {
    $env = @"
# Dify 环境变量 - 由 deploy_dify.ps1 自动生成
DIFY_VERSION=$Version
SECRET_KEY=sk-fabtwin-dify-$([guid]::NewGuid().ToString('N').Substring(0,16))
VOLUME_ROOT=$($VolumeRoot -replace '\\','/')
LISTEN_PORT=$HostPort
DB_PORT=$PgPort
REDIS_PORT=$RedisPort
POSTGRES_USER=postgres
POSTGRES_PASSWORD=difyaipass
POSTGRES_DB=dify
REDIS_PASSWORD=difyredis
SANDBOX_API_KEY=sbs-dify-fabtwin
"@
    Set-Content -Path $path -Value $env -Encoding UTF8
}

function Update-DifyEnv($path) {
    # 确保 .env 中关键变量存在
    $required = @{
        "DIFY_VERSION" = $Version
        "VOLUME_ROOT"  = ($VolumeRoot -replace '\\','/')
        "LISTEN_PORT"  = $HostPort
        "DB_PORT"      = $PgPort
        "REDIS_PORT"   = $RedisPort
    }
    if (-not (Test-Path $path)) {
        New-BuiltinEnv $path
        return
    }
    $lines = Get-Content $path -Encoding UTF8
    foreach ($k in $required.Keys) {
        if (-not ($lines -match "^$k=")) {
            Add-Content -Path $path -Value "$k=$($required[$k])" -Encoding UTF8
        }
    }
    Write-Ok ".env 已校验，$($required.Count) 个关键变量就绪"
}

# ---------------- 主动作 ----------------
function Invoke-Install {
    Invoke-PrereqCheck
    $composeFile, $_ = Invoke-PrepareDirs
    Write-Step "拉取镜像 + 启动服务 (首次运行较长，5~15 分钟)"
    Push-Location (Split-Path $composeFile -Parent)
    try {
        & docker compose -f $composeFile --env-file .env pull
        & docker compose -f $composeFile --env-file .env up -d
        if ($LASTEXITCODE -ne 0) { Write-Fail "服务启动失败，请查看 docker compose logs" }
    } finally { Pop-Location }
    Write-Ok "Dify 服务已启动"
    Show-Summary
}

function Invoke-Start   { $f = (Join-Path $DifyDir "docker/docker-compose.yaml"); & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") up -d }
function Invoke-Stop    { $f = (Join-Path $DifyDir "docker/docker-compose.yaml"); & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") stop }
function Invoke-Restart { $f = (Join-Path $DifyDir "docker/docker-compose.yaml"); & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") restart }
function Invoke-Status  { $f = (Join-Path $DifyDir "docker/docker-compose.yaml"); & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") ps }
function Invoke-Logs    { $f = (Join-Path $DifyDir "docker/docker-compose.yaml"); & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") logs --tail 100 -f }
function Invoke-Uninstall {
    $f = (Join-Path $DifyDir "docker/docker-compose.yaml")
    Write-Warn "将停止并卸载所有 Dify 容器和卷，5秒后继续 (Ctrl+C 取消)..."
    Start-Sleep 5
    & docker compose -f $f --env-file (Join-Path $DifyDir "docker/.env") down -v
}

function Show-Summary {
    $ip = "localhost"; try { $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' -and $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress } catch {}
    Write-Host "`n========================================================"
    Write-Host "  Dify 部署完成  " -ForegroundColor Green
    Write-Host "========================================================"
    Write-Host "  管理后台 (首次需注册管理员): http://$ip`:$HostPort"
    Write-Host "  PostgreSQL : $ip`:$PgPort   (user/pass/db: postgres / difyaipass / dify)"
    Write-Host "  Redis      : $ip`:$RedisPort (pass: difyredis)"
    Write-Host "  数据卷根   : $VolumeRoot"
    Write-Host "  Dify API   : http://$ip`:$HostPort (与 Web 同端口，Nginx 分发 /v1)"
    Write-Host "`n  管理命令: "
    Write-Host "    查看状态:  .\deploy_dify.ps1 status"
    Write-Host "    看日志  :  .\deploy_dify.ps1 logs"
    Write-Host "    重启服务:  .\deploy_dify.ps1 restart"
    Write-Host "======================================================`n"
}

# ---------------- 分发 ----------------
switch ($Action) {
    "install"   { Invoke-Install }
    "start"     { Invoke-Start }
    "stop"      { Invoke-Stop }
    "restart"   { Invoke-Restart }
    "status"    { Invoke-Status }
    "logs"      { Invoke-Logs }
    "uninstall" { Invoke-Uninstall }
    default     { Write-Fail "未知 Action: $Action，可选: install|start|stop|restart|status|logs|uninstall" }
}
