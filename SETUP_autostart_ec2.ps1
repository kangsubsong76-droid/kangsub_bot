# SETUP_autostart_ec2.ps1
# EC2 Windows Task Scheduler - KangSub Bot auto start
# PowerShell 5.1 compatible

$taskName   = "KangSubBot"
$botScript  = "C:\kangsub_bot\main.py"
$workingDir = "C:\kangsub_bot"
$logFile    = "C:\kangsub_bot\logs\autostart.log"

Write-Host "=== KangSub Bot Auto Start Setup ===" -ForegroundColor Cyan

# Remove existing task
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "  Removed existing task" -ForegroundColor Yellow
}

# Find py.exe
$pyExe = $null
$pyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($pyCmd) {
    $pyExe = $pyCmd.Source
}
if (-not $pyExe) {
    $candidates = @(
        "C:\Windows\py.exe",
        "C:\Windows\SysWOW64\py.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $pyExe = $c; break }
    }
}
if (-not $pyExe) {
    Write-Host "  [ERROR] py.exe not found" -ForegroundColor Red
    exit 1
}
Write-Host "  py.exe: $pyExe" -ForegroundColor Green

# Create logs directory
New-Item -ItemType Directory -Force -Path "C:\kangsub_bot\logs" | Out-Null

# Create wrapper script (restart loop)
$wrapperPath = "C:\kangsub_bot\start_bot.ps1"
Set-Content -Path $wrapperPath -Encoding UTF8 -Value @'
# start_bot.ps1 - wrapper for Task Scheduler
$env:PATH += ";C:\Program Files\Git\bin"
Set-Location "C:\kangsub_bot"

$logFile = "C:\kangsub_bot\logs\autostart.log"
$pyExe   = "PYEXE_PLACEHOLDER"

# 텔레그램 알림 전송 함수 (봇 프로세스 밖에서 동작)
function Send-TelegramAlert([string]$msg) {
    try {
        & $pyExe -c @"
import sys; sys.path.insert(0,'C:/kangsub_bot')
from notification.telegram_bot import TelegramNotifier
TelegramNotifier()._send_http('''$msg''')
"@
    } catch {}
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "$ts  [WRAPPER] KangSub Bot wrapper started"

$restartCount = 0
while ($true) {
    & $pyExe "C:\kangsub_bot\main.py"
    $exit = $LASTEXITCODE
    $ts   = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if ($exit -eq 0 -or $exit -eq $null) {
        # 정상 종료 (Ctrl+C 등) — 루프 탈출
        Add-Content -Path $logFile -Value "$ts  [WRAPPER] Normal exit — stopping"
        break
    }

    # 비정상 종료 — 재시작
    $restartCount++
    Add-Content -Path $logFile -Value "$ts  [WRAPPER] Crash (exit $exit) restart #$restartCount in 30s"
    Send-TelegramAlert "🚨 KangSub Bot 크래시 감지`n종료코드: $exit | 재시작 #$restartCount`n30초 후 자동 재시작`n시각: $ts"
    Start-Sleep 30
}
'@

# Replace placeholder with actual py.exe path
(Get-Content $wrapperPath) -replace 'PYEXE_PLACEHOLDER', $pyExe | Set-Content $wrapperPath -Encoding UTF8
Write-Host "  Wrapper script: $wrapperPath" -ForegroundColor Green

# Register Task
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapperPath`"" `
    -WorkingDirectory $workingDir

$triggerBoot  = New-ScheduledTaskTrigger -AtStartup
$triggerDaily = New-ScheduledTaskTrigger -Daily -At "05:50"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   @($triggerBoot, $triggerDaily) `
    -Settings  $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Trigger 1: Auto start 1 min after EC2 boot" -ForegroundColor Cyan
Write-Host "Trigger 2: Daily at 05:50" -ForegroundColor Cyan
Write-Host ""
Write-Host "Check status:" -ForegroundColor Yellow
Write-Host "  Get-ScheduledTask -TaskName '$taskName' | Select State, LastRunTime" -ForegroundColor White
Write-Host ""
Write-Host "Manual start:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
