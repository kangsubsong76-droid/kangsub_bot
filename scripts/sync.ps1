# EC2 ↔ GitHub 실시간 동기화 스크립트
# PowerShell로 실행: .\sync.ps1
# (로컬에서도 동일하게 사용)

param(
    [string]$message = "Auto sync: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
)

Write-Host "=== KangSub Bot Git Sync ===" -ForegroundColor Cyan
cd C:\kangsub_bot

# Pull 최신 코드
Write-Host "최신 코드 pull..." -ForegroundColor Yellow
git pull origin main

# 변경사항 push (로컬에서만)
if ($args[0] -eq "--push") {
    git add .
    git commit -m $message
    git push origin main
    Write-Host "Push 완료" -ForegroundColor Green
}

Write-Host "동기화 완료" -ForegroundColor Green
