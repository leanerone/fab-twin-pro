# FabTwin IIS Mode (Backend Only) - PowerShell Version
# Frontend served by IIS, WebSocket connects directly to backend :8002
# Usage: .\start_iis.ps1

$ErrorActionPreference = "Stop"

# ================================================================
#  Configuration
# ================================================================
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $BaseDir "backend"
$BackendPort = 8002
$IisSiteDir = "C:\inetpub\wwwroot\FabTwin"

function Write-Banner {
    param([string]$Text, [ConsoleColor]$Color = 'Cyan')
    Write-Host "================================================================" -ForegroundColor $Color
    Write-Host " $Text" -ForegroundColor White
    Write-Host "================================================================" -ForegroundColor $Color
}

function Import-EnvBat {
    param([string]$BatFile)
    if (-not (Test-Path $BatFile)) { return @{} }
    $envVars = @{}
    $lines = Get-Content $BatFile
    foreach ($line in $lines) {
        if ($line -match '^\s*set\s+(\w+)=(.*?)\s*$') {
            $envVars[$Matches[1]] = $Matches[2]
        }
    }
    return $envVars
}

# ================================================================
#  Banner
# ================================================================
Write-Banner "FabTwin IIS Mode Start"
Write-Host ""
Write-Host " Backend: $BackendPort  |  IIS: 80  |  WebSocket: direct to $BackendPort" -ForegroundColor Gray
Write-Host ""
Write-Host " Architecture:" -ForegroundColor Yellow
Write-Host "   - HTTP API:  browser -> IIS:80 -> URL Rewrite -> backend:$BackendPort"
Write-Host "   - WebSocket: browser -> backend:$BackendPort (direct, bypass IIS)"
Write-Host "   - Static:    IIS serves frontend\dist"
Write-Host ""
Write-Host " NOTE: WebSocket bypasses IIS because URL Rewrite cannot"
Write-Host "       proxy WebSocket upgrade handshake."
Write-Host ""

# ================================================================
#  Check Python
# ================================================================
try {
    $pyVer = python --version 2>&1
    Write-Host "[OK] Python: $pyVer" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
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
    Write-Host "[ERROR] env.bat not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# ================================================================
#  Auto-create venv if missing
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
        & $venvPip install --no-index --find-links=wheels -r requirements.txt
    }
    else {
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
#  Verify packages
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
try {
    $v = & $venvPython -c "import oracledb; print(oracledb.__version__)" 2>$null
    Write-Host "  oracledb: $v"
}
catch { Write-Host "  [WARN] oracledb not found!" -ForegroundColor Yellow }
Write-Host ""

# ================================================================
#  Check IIS frontend
# ================================================================
if (Test-Path "$IisSiteDir\index.html") {
    Write-Host "[OK] IIS frontend found at $IisSiteDir" -ForegroundColor Green
}
else {
    Write-Host "[WARN] IIS frontend not found at $IisSiteDir" -ForegroundColor Yellow
    Write-Host "[INFO] Please run deploy_iis_nt_final.bat first to deploy frontend to IIS"
}
Write-Host ""

# ================================================================
#  Start backend
# ================================================================
Write-Host "[1/1] Starting backend (FastAPI :$BackendPort)..." -ForegroundColor Cyan

$envLines = @()
foreach ($key in $envVars.Keys) {
    $envLines += "`$env:$key = '$($envVars[$key])'"
}
$envLines += "`$env:NO_PROXY = '*'"
$envLines += "`$env:no_proxy = '*'"
$envLines += "`$env:HTTP_PROXY = ''"
$envLines += "`$env:HTTPS_PROXY = ''"
$envSetup = $envLines -join "`n"

$backendScript = @"
`$Host.UI.RawUI.WindowTitle = 'FabTwin Backend'
$envSetup
Set-Location '$BackendDir'
Write-Host '=== Backend Config ===' -ForegroundColor Cyan
Write-Host \"DB_TYPE: `$env:DB_TYPE\"
Write-Host \"ORACLE_HOST: `$env:ORACLE_HOST\"
Write-Host \"ORACLE_USER: `$env:ORACLE_USER\"
Write-Host \"ORACLE_CLIENT_DIR: `$env:ORACLE_CLIENT_DIR\"
Write-Host '======================' -ForegroundColor Cyan
& '$venvPython' main.py
Write-Host ''
Write-Host 'Backend stopped. Press Enter to close this window.' -ForegroundColor Yellow
Read-Host
"@

$backendScriptFile = Join-Path $BackendDir "_run_iis.ps1"
$backendScript | Out-File -FilePath $backendScriptFile -Encoding utf8

Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "`"$backendScriptFile`""

Start-Sleep -Seconds 3

Write-Host ""
Write-Banner "IIS Mode Started!" -Color Green
Write-Host ""
Write-Host " Frontend:   http://localhost         (IIS port 80)"
Write-Host " Backend:    http://localhost:$BackendPort     (FastAPI direct)"
Write-Host " WebSocket:  ws://localhost:$BackendPort/ws/realtime  (direct, bypass IIS)"
Write-Host " API docs:   http://localhost:$BackendPort/docs"
Write-Host ""
Write-Host " IMPORTANT: Open port $BackendPort in Windows Firewall for WebSocket!" -ForegroundColor Yellow
Write-Host "   netsh advfirewall firewall add rule name='FabTwin Backend' dir=in action=allow protocol=TCP localport=$BackendPort"
Write-Host ""
Write-Host " Close the backend window to stop." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to close this window"
