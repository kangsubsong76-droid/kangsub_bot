# KangSub Bot — EC2 접속 시 매번 실행하는 시작 스크립트
# PowerShell에 붙여넣기만 하면 자동으로 모든 설정 완료

Write-Host "=== KangSub Bot EC2 시작 스크립트 ===" -ForegroundColor Cyan

# 1. Python 경로 자동 탐색
$pythonFound = $false
$pythonDirs = @(
    "C:\Program Files\Python312",
    "C:\Program Files\Python311",
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python312",
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python311",
    "C:\Python312", "C:\Python311"
)
foreach ($d in $pythonDirs) {
    if (Test-Path "$d\python.exe") {
        $env:PATH = "$d;$d\Scripts;" + $env:PATH
        Write-Host "Python 발견: $d" -ForegroundColor Green
        $pythonFound = $true
        break
    }
}
if (-not $pythonFound) {
    $found = Get-ChildItem C:\ -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $d = $found.DirectoryName
        $env:PATH = "$d;$d\Scripts;" + $env:PATH
        Write-Host "Python 발견 (탐색): $d" -ForegroundColor Green
    }
}

# 2. Git 경로 설정
$gitDirs = @("C:\Program Files\Git\cmd", "C:\Program Files (x86)\Git\cmd")
foreach ($d in $gitDirs) {
    if (Test-Path "$d\git.exe") {
        $env:PATH = "$d;" + $env:PATH
        Write-Host "Git 발견: $d" -ForegroundColor Green
        break
    }
}

# 3. PATH 영구 등록
[System.Environment]::SetEnvironmentVariable("PATH", $env:PATH, "Machine")

# 4. 확인
Write-Host ""
python --version
git --version
Write-Host ""

# 5. 프로젝트 폴더 이동 또는 클론
if (Test-Path "C:\kangsub_bot\main.py") {
    Write-Host "프로젝트 폴더 존재 - git pull 실행" -ForegroundColor Yellow
    cd C:\kangsub_bot
    git pull origin main
} else {
    Write-Host "프로젝트 클론 시작..." -ForegroundColor Yellow
    cd C:\
    git clone https://github.com/kangsubsong76-droid/kangsub_bot.git
    cd C:\kangsub_bot

    # 패키지 설치
    @"
yfinance==0.2.36
requests==2.31.0
beautifulsoup4==4.12.3
lxml==5.1.0
pandas==2.2.0
numpy==1.26.4
APScheduler==3.10.4
python-telegram-bot==21.1.1
notion-client==2.2.1
streamlit==1.33.0
plotly==5.20.0
python-dotenv==1.0.1
pytz==2024.1
"@ | Out-File -FilePath req.txt -Encoding utf8

    pip install -r req.txt
    pip install pykrx pywin32

    # .env 생성
    if (-not (Test-Path "config\.env")) {
        Copy-Item config\.env.example config\.env
        Write-Host ".env 파일 생성됨 - API 키를 입력하세요" -ForegroundColor Red
        notepad config\.env
    }
}

Write-Host ""
Write-Host "=== 준비 완료! C:\kangsub_bot 에서 작업하세요 ===" -ForegroundColor Cyan
Write-Host "테스트: python main.py --paper --once" -ForegroundColor Yellow
