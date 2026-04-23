# DEPLOY_commands_fix.ps1
# 텔레그램 명령어 수정 + portfolio_manual.json 동기화 배포
# EC2 PowerShell에서 실행: C:\kangsub_bot\DEPLOY_commands_fix.ps1

$ROOT = "C:\kangsub_bot"
$LOG  = "$ROOT\logs\deploy_commands.log"

function Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG -Value $line
}

Log "=== 텔레그램 명령어 수정 배포 시작 ==="

# ── 1. git PATH 보장 ──
$gitBin = "C:\Program Files\Git\bin"
if (-not ($env:PATH -split ";" | Where-Object { $_ -eq $gitBin })) {
    $env:PATH += ";$gitBin"
    Log "Git PATH 추가: $gitBin"
}

# ── 2. git pull ──
Log "git pull 실행 중..."
Set-Location $ROOT
$result = & git pull 2>&1
Log "git pull 결과: $result"

if ($LASTEXITCODE -ne 0) {
    Log "⚠️  git pull 실패. 수동으로 확인 필요."
    Write-Host "git pull 실패 — 아래 명령 직접 실행:"
    Write-Host '  $env:PATH += ";C:\Program Files\Git\bin"'
    Write-Host "  cd C:\kangsub_bot"
    Write-Host "  git pull"
    exit 1
}

# ── 3. 봇 재시작 ──
Log "KangSubBot 태스크 스케줄러 재시작..."
Stop-ScheduledTask  -TaskName "KangSubBot" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "KangSubBot"
Start-Sleep -Seconds 5

$state = (Get-ScheduledTask -TaskName "KangSubBot").State
Log "봇 상태: $state"

if ($state -eq "Running") {
    Log "✅ 봇 재시작 완료 — 텔레그램에서 /balance /holdings /signals /risk 테스트"
} else {
    Log "⚠️  봇 상태 이상: $state"
}

Log "=== 배포 완료 ==="
