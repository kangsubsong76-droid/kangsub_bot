@echo off
:: ============================================================
:: KangSub Bot — 정지 스크립트
:: ============================================================
echo [정지] KangSub Bot 종료 중...

:: 봇 프로세스 종료
taskkill /FI "WINDOWTITLE eq KangSubBot-Main" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq KangSubBot-Dashboard" /F >nul 2>&1

:: 포트 8080 사용 프로세스 종료
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8080" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [종료] PID %%a (포트 8080)
)

:: Python 프로세스 (main.py, server.py) 종료
wmic process where "name='python.exe' and CommandLine like '%%main.py%%'" delete >nul 2>&1
wmic process where "name='python.exe' and CommandLine like '%%server.py%%'" delete >nul 2>&1

echo [완료] 봇 종료 완료
timeout /t 2
