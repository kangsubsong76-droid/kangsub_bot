# SETUP_autostart_ec2.ps1
# EC2 Windows Task Scheduler - KangSub Bot auto start
# PowerShell 5.1 compatible

$taskName   = "KangSubBot"
$workingDir = "C:\kangsub_bot"
$logFile    = "C:\kangsub_bot\logs\autostart.log"

Write-Host "=== KangSub Bot Auto Start Setup ===" -ForegroundColor Cyan

# Remove existing task
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "  Removed existing task" -ForegroundColor Yellow
}

# Find py.exe (full path required for SYSTEM account)
$pyExe = $null
$candidates = @(
    "C:\Windows\py.exe",
    "C:\Windows\SysWOW64\py.exe",
    "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe"
)
$pyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($pyCmd) { $pyExe = $pyCmd.Source }
if (-not $pyExe) {
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

# ── wrapper script: 재시작 루프 + 크래시 알림 ──────────────────
$wrapperPath = "C:\kangsub_bot\start_bot.ps1"
$wrapperContent = @"
# start_bot.ps1 - Task Scheduler wrapper (auto-restart loop)
`$env:PATH += ";C:\Program Files\Git\bin;C:\Windows"
`$env:PYTHONIOENCODING = "utf-8"
Set-Location "C:\kangsub_bot"

`$logFile      = "C:\kangsub_bot\logs\autostart.log"
`$pyExe        = "$pyExe"
`$restartCount = 0

function Write-Log(`$msg) {
    `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path `$logFile -Value "`$ts  `$msg" -Encoding UTF8
}

function Send-TelegramCrash(`$exitCode, `$count) {
    try {
        `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        & "`$pyExe" -c "import sys; sys.path.insert(0,'C:/kangsub_bot'); from notification.telegram_bot import TelegramNotifier; TelegramNotifier()._send_http(f'<b>KangSub Bot 크래시</b>\n종료코드: `$exitCode | 재시작 #`$count\n30초 후 자동 재시작\n시각: `$ts')"
    } catch {}
}

Write-Log "[WRAPPER START] py: `$pyExe"

while (`$true) {
    & "`$pyExe" "C:\kangsub_bot\main.py"
    `$exit = `$LASTEXITCODE
    if (`$exit -eq 0) {
        Write-Log "[WRAPPER] Normal exit (code 0) — stopped"
        break
    }
    `$restartCount++
    Write-Log "[WRAPPER CRASH] exit=`$exit restart=`$restartCount"
    Send-TelegramCrash `$exit `$restartCount
    Start-Sleep 30
}
"@
Set-Content -Path $wrapperPath -Value $wrapperContent -Encoding UTF8
Write-Host "  Wrapper: $wrapperPath" -ForegroundColor Green

# ── Task Scheduler 등록 ─────────────────────────────────────
# powershell.exe 전체 경로 사용 (SYSTEM 계정 PATH 미보장)
$psExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

$action = New-ScheduledTaskAction `
    -Execute $psExe `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$wrapperPath`"" `
    -WorkingDirectory $workingDir

$triggerBoot         = New-ScheduledTaskTrigger -AtStartup
$triggerBoot.Delay   = "PT1M"   # 부팅 후 1분 대기
$triggerDaily        = New-ScheduledTaskTrigger -Daily -At "05:50"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances  IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# SYSTEM 대신 현재 로그인 사용자로 등록 (환경변수 보장)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "  실행 계정: $currentUser" -ForegroundColor Green

$principal = New-ScheduledTaskPrincipal `
    -UserId   $currentUser `
    -LogonType Interactive `
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
Write-Host "Account  : $currentUser" -ForegroundColor Cyan
Write-Host "Trigger 1: EC2 boot + 1min" -ForegroundColor Cyan
Write-Host "Trigger 2: Daily 05:50" -ForegroundColor Cyan
Write-Host ""
Write-Host "Start now:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
Write-Host ""
Write-Host "Check:" -ForegroundColor Yellow
Write-Host "  Get-ScheduledTask -TaskName '$taskName' | Select State" -ForegroundColor White
Write-Host "  Get-Content C:\kangsub_bot\logs\autostart.log" -ForegroundColor White
