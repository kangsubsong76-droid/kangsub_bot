# SETUP_autostart_ec2.ps1
# EC2 Windows Task Scheduler에 KangSub Bot 자동 시작 등록
# ─ 시스템 시작 시 자동 실행
# ─ 크래시 시 5분 후 최대 5회 자동 재시작
#
# 실행: EC2 PowerShell (관리자 권한)

$taskName   = "KangSubBot"
$pyPath     = "py"          # EC2: py.exe (Python Launcher)
$botScript  = "C:\kangsub_bot\main.py"
$workingDir = "C:\kangsub_bot"
$logFile    = "C:\kangsub_bot\logs\autostart.log"

Write-Host "=== KangSub Bot 자동 시작 등록 ===" -ForegroundColor Cyan

# ── 기존 태스크 제거 (있는 경우) ───────────────────────────
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "  기존 태스크 제거됨" -ForegroundColor Yellow
}

# ── py.exe 경로 확인 ────────────────────────────────────────
$pyExe = (Get-Command py -ErrorAction SilentlyContinue)?.Source
if (-not $pyExe) {
    # 일반적인 설치 경로 탐색
    $candidates = @(
        "C:\Windows\py.exe",
        "C:\Windows\SysWOW64\py.exe",
        "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $pyExe = $c; break }
    }
}
if (-not $pyExe) {
    Write-Host "  [오류] py.exe 를 찾을 수 없습니다. Python Launcher 설치를 확인하세요." -ForegroundColor Red
    exit 1
}
Write-Host "  py.exe 경로: $pyExe" -ForegroundColor Green

# ── 로그 디렉터리 생성 ───────────────────────────────────────
New-Item -ItemType Directory -Force -Path "C:\kangsub_bot\logs" | Out-Null

# ── 시작 래퍼 스크립트 생성 (PATH 보장 + 재시작 루프) ──────
$wrapperPath = "C:\kangsub_bot\start_bot.ps1"
$wrapperContent = @"
# start_bot.ps1 — Task Scheduler 호출용 래퍼
# PATH에 Git 추가 (git pull 사용 시 필요)
`$env:PATH += ";C:\Program Files\Git\bin"
`$env:PATH += ";C:\Python313;C:\Python313\Scripts"

Set-Location "C:\kangsub_bot"
`$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "$logFile" -Value "`$timestamp  [START] KangSub Bot 시작"

# 봇 실행 (크래시 시 30초 후 재시작, 최대 무한 반복)
while (`$true) {
    try {
        & "$pyExe" "C:\kangsub_bot\main.py"
        `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path "$logFile" -Value "`$ts  [EXIT] 봇 정상 종료"
        break   # 정상 종료(Ctrl+C)는 루프 탈출
    } catch {
        `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path "$logFile" -Value "`$ts  [CRASH] 재시작 대기 30초..."
        Start-Sleep 30
    }
}
"@
$wrapperContent | Out-File -FilePath $wrapperPath -Encoding UTF8 -Force
Write-Host "  래퍼 스크립트 생성: $wrapperPath" -ForegroundColor Green

# ── Task Scheduler 등록 ─────────────────────────────────────
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapperPath`"" `
    -WorkingDirectory $workingDir

# 트리거 1: 시스템 시작 시 (+ 1분 지연 — 네트워크 대기)
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerBoot.Delay = "PT1M"   # 1분 지연

# 트리거 2: 매일 05:50 (장 시작 10분 전 재확인 — 야간 재부팅 후 backup)
$triggerDaily = New-ScheduledTaskTrigger -Daily -At "05:50"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
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
Write-Host "=== 등록 완료 ===" -ForegroundColor Green
Write-Host ""
Write-Host "트리거 1: EC2 시작/재시작 시 1분 후 자동 실행" -ForegroundColor Cyan
Write-Host "트리거 2: 매일 05:50 실행 (이미 실행 중이면 무시)" -ForegroundColor Cyan
Write-Host ""
Write-Host "확인:" -ForegroundColor Yellow
Write-Host "  Get-ScheduledTask -TaskName '$taskName' | Select State, LastRunTime" -ForegroundColor White
Write-Host ""
Write-Host "수동 시작:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
Write-Host ""
Write-Host "태스크 제거:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor White
