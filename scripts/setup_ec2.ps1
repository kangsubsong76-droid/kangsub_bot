# KangSub Bot — AWS EC2 Windows Server 초기 설정 스크립트
# PowerShell로 실행: .\setup_ec2.ps1

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  KangSub Bot EC2 초기 설정 시작" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Chocolatey 패키지 매니저 설치
Write-Host "`n[1/8] Chocolatey 설치..." -ForegroundColor Yellow
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 2. Python 3.11 설치
Write-Host "`n[2/8] Python 3.11 설치..." -ForegroundColor Yellow
choco install python311 -y
refreshenv

# 3. Git 설치
Write-Host "`n[3/8] Git 설치..." -ForegroundColor Yellow
choco install git -y
refreshenv

# 4. 프로젝트 클론
Write-Host "`n[4/8] GitHub 프로젝트 클론..." -ForegroundColor Yellow
cd C:\
git clone https://github.com/kangsubsong76-droid/kangsub_bot.git
cd C:\kangsub_bot

# 5. Python 패키지 설치
Write-Host "`n[5/8] Python 패키지 설치..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install pywin32
pip install pykiwoom

# 6. .env 파일 생성 안내
Write-Host "`n[6/8] .env 파일 설정..." -ForegroundColor Yellow
Copy-Item "config\.env.example" "config\.env"
Write-Host "  → config\.env 파일을 열어 API 키를 입력해주세요!" -ForegroundColor Red
notepad "config\.env"

# 7. data/store 폴더 생성
Write-Host "`n[7/8] 데이터 폴더 생성..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "C:\kangsub_bot\data\store"
New-Item -ItemType Directory -Force -Path "C:\kangsub_bot\logs"

# 8. Windows 작업 스케줄러 등록 (부팅 시 자동 시작)
Write-Host "`n[8/8] 자동 시작 등록..." -ForegroundColor Yellow
$action = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "C:\kangsub_bot\main.py" `
    -WorkingDirectory "C:\kangsub_bot"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "KangSubBot" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force

Write-Host "`n====================================================" -ForegroundColor Green
Write-Host "  설정 완료!" -ForegroundColor Green
Write-Host "  다음 단계:" -ForegroundColor Green
Write-Host "  1. 키움 Open API+ 설치: https://www1.kiwoom.com/h/common/download/WOOZSDownload" -ForegroundColor Green
Write-Host "  2. config\.env 파일에 API 키 입력" -ForegroundColor Green
Write-Host "  3. python main.py --paper 로 테스트 실행" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
