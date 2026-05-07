@echo off
title AlfaPro Bot - DEV
cd /d "%~dp0"

set VENV_PY=alfapro-bot-gold\venv311\Scripts\python.exe

if not exist "%VENV_PY%" (
    echo [HATA] venv bulunamadi: %VENV_PY%
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
echo   AlfaPro Bot - DEV  [--reload aktif]
echo  ====================================
echo   Panel    : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo   Degisiklik kaydedince otomatik yeniden baslar
echo   Durdurmak: CTRL+C
echo  ====================================
echo.

set APP_ENV=development
set APP_DEBUG=true
"%VENV_PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
