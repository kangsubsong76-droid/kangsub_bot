# SETUP_daily_restart_ec2.ps1
# KangSubBot 매일 새벽 05:48 강제 재시작 Task Scheduler 등록
# EC2 PowerShell (관리자 권한)에서 한 번만 실행

$TASK_NAME   = "KangSubBotDailyRestart"
$BOT_TASK    = "KangSubBot"
$RESTART_TIME = "05:48"
$ROOT        = "C:\kangsub_bot"

Write-Host "=== KangSubBot 매일 강제 재시작 Task 등록 ===" -ForegroundColor Cyan

# ── Step 1: 재시작용 helper 스크립트 생성 ──
$helperPath = "$ROOT\scripts\daily_restart.ps1"
$helperContent = 'Stop-ScheduledTask -TaskName "KangSubBot" -ErrorAction SilentlyContinue' + "`r`n" +
                 'Start-Sleep -Seconds 15' + "`r`n" +
                 'Start-ScheduledTask -TaskName "KangSubBot"'
Set-Content -Path $helperPath -Value $helperContent -Encoding UTF8
Write-Host "Helper 스크립트 생성: $helperPath" -ForegroundColor Green

# ── Step 2: 기존 태스크 제거 ──
Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue

# ── Step 3: 액션 / 트리거 / 세팅 ──
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NonInteractive -WindowStyle Hidden -File `"$helperPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At $RESTART_TIME

$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -RunOnlyIfNetworkAvailable

# ── Step 4: 태스크 등록 ──
Register-ScheduledTask -TaskName $TASK_NAME -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -LogonType S4U -Force

Write-Host ""
Write-Host "✅ '$TASK_NAME' 태스크 등록 완료" -ForegroundColor Green
Write-Host "   매일 $RESTART_TIME KST  →  Stop → 15초 대기 → Start" -ForegroundColor Yellow
Write-Host ""

# ── EC2 타임존 확인 ──
$tz = (Get-TimeZone).Id
Write-Host "현재 EC2 TimeZone: $tz" -ForegroundColor Cyan
if ($tz -ne "Korea Standard Time") {
    Write-Host "⚠️  EC2 타임존이 KST가 아닙니다! 아래 명령으로 변경 후 재실행 하세요:" -ForegroundColor Red
    Write-Host "   Set-TimeZone -Id 'Korea Standard Time'" -ForegroundColor White
}

Write-Host ""
Get-ScheduledTask -TaskName "KangSub*" | Select-Object TaskName, State | Format-Table -AutoSize
