# SETUP_daily_restart_ec2.ps1
# KangSubBot 매일 새벽 05:48 강제 재시작 Task Scheduler 등록
# EC2 PowerShell (관리자 권한)에서 한 번만 실행

$TASK_NAME   = "KangSubBotDailyRestart"
$BOT_TASK    = "KangSubBot"
$RESTART_TIME = "05:48"   # KST 05:48 (봇 재시작, 05:50 메인 트리거보다 2분 앞서 종료)

Write-Host "=== KangSubBot 매일 강제 재시작 Task 등록 ===" -ForegroundColor Cyan

# ── 기존 태스크 제거 ──
Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue

# ── 재시작 인라인 스크립트 ──
$script = @"
Stop-ScheduledTask -TaskName '$BOT_TASK' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 15
Start-ScheduledTask -TaskName '$BOT_TASK'
"@

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -Command `"$script`""

# 매일 05:48 실행 (EC2 시간대가 KST로 설정되어 있어야 함)
# EC2 시간대 확인: Get-TimeZone
# KST로 변경: Set-TimeZone -Id "Korea Standard Time"
$trigger = New-ScheduledTaskTrigger -Daily -At $RESTART_TIME

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0 -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# S4U: 로그인 없이 백그라운드 실행
Register-ScheduledTask `
    -TaskName  $TASK_NAME `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -LogonType S4U `
    -Force

Write-Host ""
Write-Host "✅ '$TASK_NAME' 태스크 등록 완료" -ForegroundColor Green
Write-Host "   - 매일 $RESTART_TIME KST에 KangSubBot 강제 재시작" -ForegroundColor Yellow
Write-Host "   - 순서: Stop → 15초 대기 → Start (메모리 클린 재시작)" -ForegroundColor Yellow
Write-Host ""

# EC2 타임존 확인
$tz = (Get-TimeZone).Id
Write-Host "현재 EC2 TimeZone: $tz" -ForegroundColor Cyan
if ($tz -ne "Korea Standard Time") {
    Write-Host "⚠️  EC2 타임존이 KST가 아닙니다!" -ForegroundColor Red
    Write-Host "   아래 명령으로 변경하세요:" -ForegroundColor Red
    Write-Host "   Set-TimeZone -Id 'Korea Standard Time'" -ForegroundColor White
}

Write-Host ""
Write-Host "태스크 목록 확인:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "KangSub*" | Select-Object TaskName, State | Format-Table -AutoSize
