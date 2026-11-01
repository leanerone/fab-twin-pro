# FabTwin offline install: WSL2 + Docker Desktop (no network needed)
$log = "E:\AI\fab-ai-services\install_log.txt"
function L($msg) { $line = "$(Get-Date -Format 'HH:mm:ss') $msg"; $line | Tee-Object -FilePath $log -Append }

"" | Out-File $log -Encoding utf8
L "===== install start ====="

$wslMsi = "E:\AI\fab-ai-services\wsl-3.0.4-x64.msi"
$dockerExe = "E:\AI\fab-ai-services\DockerDesktopInstaller.exe"
foreach ($f in @($wslMsi, $dockerExe)) {
    if (-not (Test-Path $f)) { L "MISSING FILE: $f"; exit 1 }
}
L "source files ready"

L "enable feature: Microsoft-Windows-Subsystem-Linux ..."
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
L "  DISM exit code $LASTEXITCODE"
L "enable feature: VirtualMachinePlatform ..."
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
L "  DISM exit code $LASTEXITCODE"

L "install WSL MSI 3.0.4.0 ..."
$proc = Start-Process msiexec -ArgumentList "/i", "`"$wslMsi`"", "/qn", "/norestart", "/L*v", "E:\AI\fab-ai-services\wsl_msi.log" -Wait -PassThru
L "  msiexec exit code $($proc.ExitCode)"

L "install Docker Desktop (silent, 3-8 min) ..."
$proc2 = Start-Process "$dockerExe" -ArgumentList "install", "--quiet", "--accept-license" -Wait -PassThru
L "  Docker installer exit code $($proc2.ExitCode)"

L "verify:"
if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") { L "  Docker Desktop INSTALLED" } else { L "  Docker Desktop NOT FOUND" }
$wslExe = "C:\Program Files\WSL\wsl.exe"
if (Test-Path $wslExe) { L "  WSL INSTALLED" } else { L "  WSL dir not found (pending reboot)" }

L "===== install done. REBOOT REQUIRED ====="
