# ============================================================
# KangSub Bot — .env 파일 생성 스크립트
# EC2에서 한 번만 실행: .\setup_env.ps1
# ============================================================

$envPath = "C:\kangsub_bot\config\.env"

# 기존 .env가 있으면 백업
if (Test-Path $envPath) {
    Copy-Item $envPath "$envPath.bak"
    Write-Host "[백업] 기존 .env → .env.bak" -ForegroundColor Yellow
}

# 텔레그램 토큰은 기존 .env에서 가져오기
$existingEnv = @{}
if (Test-Path "$envPath.bak") {
    Get-Content "$envPath.bak" | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.*)$") {
            $existingEnv[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
}

$telegramToken  = $existingEnv["TELEGRAM_TOKEN"]
$telegramChatId = $existingEnv["TELEGRAM_CHAT_ID"]
$notionToken    = $existingEnv["NOTION_TOKEN"]
$dartKey        = $existingEnv["DART_API_KEY"]

# .env 파일 작성
@"
# === KangSub Bot 환경변수 ===
# 자동 생성: $(Get-Date -Format 'yyyy-MM-dd HH:mm')

# 텔레그램
TELEGRAM_TOKEN=$telegramToken
TELEGRAM_CHAT_ID=$telegramChatId

# Notion
NOTION_TOKEN=$notionToken
NOTION_DB_TRADES=
NOTION_DB_PORTFOLIO=
NOTION_DB_SIGNALS=
NOTION_DB_NEWS=

# DART
DART_API_KEY=$dartKey

# 키움증권 REST API
KIWOOM_ACCOUNT=6594-7112
KIWOOM_APP_KEY=EDK5NcUXLeFkXyYQN9gNlNIKxRy-fttTNq16DUG2u9g
KIWOOM_SECRET_KEY=If4qA1sYc6Onft7JmGlDYmjMBukiBmsRZ56BMAtk1X4
KIWOOM_MOCK=true
"@ | Set-Content $envPath -Encoding UTF8

Write-Host "[완료] .env 파일 생성됨: $envPath" -ForegroundColor Green
Write-Host ""
Write-Host "키움 REST API 설정:"
Write-Host "  계좌: 6594-7112"
Write-Host "  모드: 모의투자 (KIWOOM_MOCK=true)"
Write-Host ""
Write-Host "실전매매 전환 시: .env에서 KIWOOM_MOCK=false 로 변경"
