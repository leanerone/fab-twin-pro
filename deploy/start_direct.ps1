# FabTwin Direct Mode (No IIS) - PowerShell Version
# Usage: Right-click -> Run with PowerShell, or: .\start_direct.ps1
# 在 VSCode 终端中直接运行：.\start_direct.ps1

$ErrorActionPreference = "Stop"

# ================================================================
#  Configuration
# ================================================================
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $BaseDir "backend"
$FrontendDir = Join-Path $BaseDir "frontend"

$BackendPort = 8002
$FrontendPort = 5173

# ================================================================
#  Helper: Write colored banner
# ================================================================
function Write-Banner {
    param([string]$Text, [ConsoleColor]$Color = 'Cyan')
    Write-Host "================================================================" -ForegroundColor $Color
    Write-Host " $Text" -ForegroundColor White
    Write-Host "================================================================" -ForegroundColor $Color
}

# ================================================================
#  Helper: Parse env.bat and set environment variables
# ================================================================
function Import-EnvBat {
    param([string]$BatFile)
    if (-not (Test-Path $BatFile)) { return @{} }
    
    $envVars = @{}
    $lines = Get-Content $BatFile
    foreach ($line in $lines) {
        if ($line -match '^\s*set\s+(\w+)=(.*?)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
            $envVars[$name] = $value
        }
    }
    return $envVars
}

# ================================================================
#  Banner
# ================================================================
Write-Banner "FabTwin Direct Mode Start (No IIS)"
Write-Host ""
Write-Host " Backend: $BackendPort  |  Frontend: Vite preview $FrontendPort" -ForegroundColor Gray
Write-Host ""
Write-Host " Architecture:" -ForegroundColor Yellow
Write-Host "   - HTTP API:  browser -> Vite:$FrontendPort -> proxy -> backend:$BackendPort"
Write-Host "   - WebSocket: browser -> Vite:$FrontendPort -> proxy -> backend:$BackendPort"
Write-Host "   - Static:    Vite serves frontend\dist (preview mode)"
Write-Host ""
Write-Host " NOTE: This mode does NOT need IIS. Vite proxy handles both"
Write-Host "       HTTP and WebSocket natively."
Write-Host ""

# ================================================================
#  Check Python
# ================================================================
try {
    $pyVer = python --version 2>&1
    Write-Host "[OK] $pyVer" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ first"
    Read-Host "Press Enter to exit"
    exit 1
}

# ================================================================
#  Check Node.js
# ================================================================
try {
    $nodeVer = node --version 2>&1
    Write-Host "[OK] Node.js $nodeVer" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Node.js not found in PATH" -ForegroundColor Red
    Write-Host "Please install Node.js 18+ first"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# ================================================================
#  Load environment
# ================================================================
$envBat = Join-Path $BaseDir "env.bat"
if (Test-Path $envBat) {
    Write-Host "[INFO] Loading env.bat..." -ForegroundColor Yellow
    $envVars = Import-EnvBat $envBat
    foreach ($key in $envVars.Keys) {
        [System.Environment]::SetEnvironmentVariable($key, $envVars[$key], "Process")
    }
    Write-Host "  DB_TYPE: $($envVars['DB_TYPE'])"
    Write-Host "  ORACLE_HOST: $($envVars['ORACLE_HOST'])"
    Write-Host "  ORACLE_USER: $($envVars['ORACLE_USER'])"
    Write-Host "  ORACLE_CLIENT_DIR: $($envVars['ORACLE_CLIENT_DIR'])"
}
else {
    Write-Host "[ERROR] env.bat not found! Oracle connection required." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# ================================================================
#  Auto-create backend venv if missing
# ================================================================
$venvPython = Join-Path $BackendDir "venv\Scripts\python.exe"
$venvPip = Join-Path $BackendDir "venv\Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Banner "venv not found, creating virtual environment..."
    
    Push-Location $BackendDir
    try {
        python -m venv venv
        Write-Host "[OK] venv created" -ForegroundColor Green
    }
    catch {
        Write-Host "[ERROR] Failed to create venv: $_" -ForegroundColor Red
        Pop-Location
        Read-Host "Press Enter to exit"
        exit 1
    }
    
    Write-Host "Upgrading pip..."
    & $venvPython -m pip install --upgrade pip | Out-Null
    
    Write-Host "Installing dependencies..."
    $wheelsDir = Join-Path $BackendDir "wheels"
    if (Test-Path $wheelsDir) {
        Write-Host "  Found wheels directory, installing OFFLINE..."
        & $venvPip install --no-index --find-links=wheels -r requirements.txt
    }
    else {
        Write-Host "  No wheels directory, installing ONLINE..."
        & $venvPip install -r requirements.txt
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] pip install failed" -ForegroundColor Red
        Pop-Location
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "[OK] Dependencies installed" -ForegroundColor Green
    Write-Banner "Ready" -Color Green
    Pop-Location
}
else {
    Write-Host "[OK] venv already exists" -ForegroundColor Green
}
Write-Host ""

# ================================================================
#  Verify critical packages
# ================================================================
Write-Host "[INFO] Checking critical packages..." -ForegroundColor Yellow
try {
    $v = & $venvPython -c "import fastapi; print(fastapi.__version__)" 2>$null
    Write-Host "  fastapi: $v"
}
catch { Write-Host "  [WARN] fastapi not found!" -ForegroundColor Yellow }

try {
    $v = & $venvPython -c "import sqlalchemy; print(sqlalchemy.__version__)" 2>$null
    Write-Host "  sqlalchemy: $v"
}
catch { Write-Host "  [WARN] sqlalchemy not found!" -ForegroundColor Yellow }
Write-Host ""

# ================================================================
#  Check frontend build
# ================================================================
$distIndex = Join-Path $FrontendDir "dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Host "[INFO] Frontend dist not found, building..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..."
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] npm install failed" -ForegroundColor Red
            Pop-Location
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
    
    Write-Host "Building frontend..."
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Frontend build failed" -ForegroundColor Red
        Pop-Location
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "[OK] Frontend built" -ForegroundColor Green
    Pop-Location
}
else {
    Write-Host "[OK] Frontend dist found" -ForegroundColor Green
}
Write-Host ""

# ================================================================
#  Build environment variable string for child processes
# ================================================================
$envLines = @()
foreach ($key in $envVars.Keys) {
    $envLines += "`$env:$key = '$($envVars[$key])'"
}
$envLines += "`$env:NO_PROXY = '*'"
$envLines += "`$env:no_proxy = '*'"
$envLines += "`$env:HTTP_PROXY = ''"
$envLines += "`$env:HTTPS_PROXY = ''"
$envSetup = $envLines -join "`n"

# ================================================================
#  Start backend in a new PowerShell window
# ================================================================
Write-Host "[1/2] Starting backend (FastAPI :$BackendPort)..." -ForegroundColor Cyan

$backendScript = @"
`$Host.UI.RawUI.WindowTitle = 'FabTwin Backend'
$envSetup
Set-Location '$BackendDir'
Write-Host '=== Backend Config ===' -ForegroundColor Cyan
Write-Host \"DB_TYPE: `$env:DB_TYPE\"
Write-Host \"ORACLE_HOST: `$env:ORACLE_HOST\"
Write-Host \"ORACLE_USER: `$env:ORACLE_USER\"
Write-Host '======================' -ForegroundColor Cyan
& '$venvPython' main.py
Write-Host ''
Write-Host 'Backend stopped. Press Enter to close this window.' -ForegroundColor Yellow
Read-Host
"@

$backendScriptFile = Join-Path $BackendDir "_run_direct.ps1"
$backendScript | Out-File -FilePath $backendScriptFile -Encoding utf8

Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "`"$backendScriptFile`""

Start-Sleep -Seconds 3

# ================================================================
#  Start frontend in a new PowerShell window
# ================================================================
Write-Host "[2/2] Starting frontend (Vite preview :$FrontendPort)..." -ForegroundColor Cyan

$frontendScript = @"
`$Host.UI.RawUI.WindowTitle = 'FabTwin Frontend'
Set-Location '$FrontendDir'
npx vite preview --host
Write-Host ''
Write-Host 'Frontend stopped. Press Enter to close this window.' -ForegroundColor Yellow
Read-Host
"@

$frontendScriptFile = Join-Path $FrontendDir "_run_preview.ps1"
$frontendScript | Out-File -FilePath $frontendScriptFile -Encoding utf8

Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "`"$frontendScriptFile`""

Start-Sleep -Seconds 2

# ================================================================
#  Done
# ================================================================
Write-Host ""
Write-Banner "Direct Mode Started!" -Color Green
Write-Host ""
Write-Host " Frontend:   http://localhost:$FrontendPort  (Vite preview)"
Write-Host " Backend:    http://localhost:$BackendPort  (FastAPI direct)"
Write-Host " WebSocket:  ws://localhost:$FrontendPort/ws/realtime"
Write-Host " API docs:   http://localhost:$BackendPort/docs"
Write-Host ""
Write-Host " No IIS needed. Vite proxy handles HTTP + WebSocket natively."
Write-Host ""
Write-Host " Close the backend/frontend windows to stop services." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to close this window"
