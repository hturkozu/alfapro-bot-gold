@echo off
title AlfaPro Bot - Production
cd /d "%~dp0alfapro-bot-gold"

if not exist "venv311\Scripts\python.exe" (
    echo [HATA] venv311 bulunamadi.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [HATA] .env dosyasi bulunamadi.
    pause
    exit /b 1
)

echo.
echo  ====================================
echo   AlfaPro Bot - Production
echo  ====================================
echo   Panel    : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo   Durdurmak: CTRL+C
echo  ====================================
echo.

set APP_ENV=production
set APP_DEBUG=false
venv311\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
