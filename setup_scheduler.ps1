# ============================================================
# KangSub Bot — Windows 작업 스케줄러 등록 스크립트
# PowerShell로 실행: .\setup_scheduler.ps1
# EC2 부팅 시 자동 시작 + 매일 오전 8:00 재시작
# ============================================================

$BotDir = "C:\kangsub_bot"
$ScriptPath = "$BotDir\start_bot.bat"

Write-Host "=== KangSub Bot 작업 스케줄러 등록 ===" -ForegroundColor Cyan

# 1. 부팅 시 자동 시작
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$actionBoot  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $BotDir
$settingsBoot = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName "KangSubBot_AutoStart" `
    -Trigger $triggerBoot `
    -Action $actionBoot `
    -Settings $settingsBoot `
    -RunLevel Highest `
    -Force

Write-Host "[OK] 부팅 자동 시작 등록 완료" -ForegroundColor Green

# 2. 매일 오전 8:00 재시작 (메모리 누수 방지)
$triggerDaily = New-ScheduledTaskTrigger -Daily -At "08:00AM"
$stopAction   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BotDir\stop_bot.bat`"" -WorkingDirectory $BotDir
$startAction  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $BotDir

Register-ScheduledTask `
    -TaskName "KangSubBot_DailyRestart" `
    -Trigger $triggerDaily `
    -Action $stopAction, $startAction `
    -RunLevel Highest `
    -Force

Write-Host "[OK] 매일 오전 8:00 재시작 등록 완료" -ForegroundColor Green

# 3. 상태 확인
Write-Host ""
Write-Host "=== 등록된 작업 ===" -ForegroundColor Cyan
Get-ScheduledTask | Where-Object { $_.TaskName -like "KangSubBot*" } | Format-Table TaskName, State -AutoSize

Write-Host ""
Write-Host "=== AWS Security Group 포트 개방 필요 ===" -ForegroundColor Yellow
Write-Host "EC2 콘솔 -> Security Group -> Inbound rules -> 추가:"
Write-Host "  Type: Custom TCP | Port: 8080 | Source: 0.0.0.0/0 (또는 내 IP)"
Write-Host ""
Write-Host "대시보드 URL: http://<EC2-Public-IP>:8080"
