@echo off
:: ============================================================
:: KangSub Bot — EC2 Windows Server 자동 시작 스크립트
:: 위치: C:\kangsub_bot\start_bot.bat
:: 사용: 작업 스케줄러 또는 수동 실행
:: ============================================================

setlocal
set BOT_DIR=C:\kangsub_bot
set PYTHON=python
set LOG_FILE=%BOT_DIR%\logs\start_bot.log

:: 로그 디렉토리 생성
if not exist "%BOT_DIR%\logs" mkdir "%BOT_DIR%\logs"

echo [%date% %time%] KangSub Bot 시작 >> %LOG_FILE%
echo ============================================================
echo  KangSub Bot 시작
echo  디렉토리: %BOT_DIR%
echo ============================================================

cd /d %BOT_DIR%

:: 가상환경이 있으면 활성화
if exist "%BOT_DIR%\venv\Scripts\activate.bat" (
    call "%BOT_DIR%\venv\Scripts\activate.bat"
    echo [OK] 가상환경 활성화
) else (
    echo [INFO] 가상환경 없음 - 시스템 Python 사용
)

:: 의존성 확인
%PYTHON% -c "import flask, yfinance" 2>nul
if errorlevel 1 (
    echo [설치] 패키지 설치 중...
    %PYTHON% -m pip install -r requirements.txt --quiet
)

:: 기존 프로세스 종료 (포트 충돌 방지)
echo [정리] 기존 프로세스 확인...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8080" ^| find "LISTENING"') do (
    echo [종료] PID %%a (포트 8080)
    taskkill /PID %%a /F >nul 2>&1
)

:: 메인 봇 백그라운드 실행
echo [시작] 메인 봇 (페이퍼 트레이딩)...
start "KangSubBot-Main" /B %PYTHON% main.py --paper >> %LOG_FILE% 2>&1

:: 대시보드 서버 백그라운드 실행
echo [시작] 대시보드 서버 (포트 8080)...
start "KangSubBot-Dashboard" /B %PYTHON% dashboard\server.py >> %LOG_FILE% 2>&1

echo.
echo [완료] 봇 및 대시보드가 시작되었습니다.
echo  - 메인 봇: 백그라운드 실행 중
echo  - 대시보드: http://localhost:8080
echo  - 로그: %LOG_FILE%
echo.
echo [팁] 텔레그램에서 /status 명령으로 확인하세요.

timeout /t 3
