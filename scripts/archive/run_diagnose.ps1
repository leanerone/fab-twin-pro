# FabTwin Oracle环境诊断工具启动器 - PowerShell版本
# 用于在量产环境连接量产Oracle并导出数据报告
# Usage: .\run_diagnose.ps1

$ErrorActionPreference = "Stop"

# ================================================================
#  Configuration
# ================================================================
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $BaseDir "backend"

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
Write-Banner "FabTwin Oracle环境诊断工具"
Write-Host ""
Write-Host " 用途: 连接量产Oracle，导出数据库结构和数据样本" -ForegroundColor Gray
Write-Host " 输出: backend\prod_oracle_report_*.json / *.txt" -ForegroundColor Gray
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
#  Load environment from env.bat
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
    Write-Host "  ORACLE_SERVICE: $($envVars['ORACLE_SERVICE'])"
    Write-Host "  ORACLE_CLIENT_DIR: $($envVars['ORACLE_CLIENT_DIR'])"
}
else {
    Write-Host "[WARN] env.bat not found, will use script defaults" -ForegroundColor Yellow
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
    Pop-Location
}
else {
    Write-Host "[OK] venv already exists" -ForegroundColor Green
}
Write-Host ""

# ================================================================
#  Verify oracledb package
# ================================================================
Write-Host "[INFO] Checking oracledb..." -ForegroundColor Yellow
try {
    $v = & $venvPython -c "import oracledb; print(oracledb.__version__)" 2>$null
    Write-Host "  oracledb: $v"
}
catch { Write-Host "  [WARN] oracledb not found!" -ForegroundColor Yellow }
Write-Host ""

# ================================================================
#  Run diagnose script in venv with env vars
# ================================================================
Write-Host "[1/1] Running diagnose script..." -ForegroundColor Cyan

$envLines = @()
foreach ($key in $envVars.Keys) {
    $envLines += "`$env:$key = '$($envVars[$key])'"
}
$envSetup = $envLines -join "`n"

$diagScript = @"
`$Host.UI.RawUI.WindowTitle = 'FabTwin Oracle Diagnose'
$envSetup
Set-Location '$BackendDir'
Write-Host '=== Diagnose Config ===' -ForegroundColor Cyan
Write-Host \"ORACLE_HOST: `$env:ORACLE_HOST\"
Write-Host \"ORACLE_USER: `$env:ORACLE_USER\"
Write-Host \"ORACLE_CLIENT_DIR: `$env:ORACLE_CLIENT_DIR\"
Write-Host '=========================' -ForegroundColor Cyan
& '$venvPython' diagnose_oracle_env.py
Write-Host ''
Write-Host 'Diagnose complete. Press Enter to close.' -ForegroundColor Yellow
Read-Host
"@

$diagScriptFile = Join-Path $BackendDir "_run_diagnose.ps1"
$diagScript | Out-File -FilePath $diagScriptFile -Encoding utf8

Start-Process powershell.exe -ArgumentList "-NoExit", "-File", "`"$diagScriptFile`""

Start-Sleep -Seconds 2

Write-Host ""
Write-Banner "Diagnose Started in New Window!" -Color Green
Write-Host ""
Write-Host " Output files (in backend\):" -ForegroundColor Yellow
Write-Host "   - prod_oracle_report_*.json  (完整报告，发给开发)" -ForegroundColor White
Write-Host "   - prod_oracle_report_*.txt   (可读性报告)" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to close this window"
