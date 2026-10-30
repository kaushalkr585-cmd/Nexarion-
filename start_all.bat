@echo off
setlocal enabledelayedexpansion
title NEXARION — Starting System Services

echo =====================================================================
echo               NEXARION Multi-Agent Code Review System
echo =====================================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: 1. Check & Start Ollama
echo [1/3] Checking Ollama local AI server...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo       [OK] Ollama is already running on http://localhost:11434
) else (
    echo       [..] Starting Ollama server in background...
    start "Ollama AI Server" /min cmd /c "ollama serve"
    timeout /t 2 /nobreak >NUL
    echo       [OK] Ollama server launched on http://localhost:11434
)

:: 2. Check & Start FastAPI Backend
echo [2/3] Starting FastAPI Backend on port 8000...
if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    start "NEXARION Backend (FastAPI)" cmd /k "title NEXARION Backend (FastAPI) && cd /d "%ROOT_DIR%" && .venv\Scripts\python.exe -m uvicorn code_review.web.app:app --host 127.0.0.1 --port 8000 --reload"
    echo       [OK] Backend server started at http://127.0.0.1:8000
    echo            API Docs available at http://127.0.0.1:8000/docs
) else (
    echo       [ERROR] Python virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

:: 3. Check & Start Frontend (Vite)
echo [3/3] Starting Vite Frontend on port 5173...
if exist "%ROOT_DIR%frontend" (
    start "NEXARION Frontend (Vite)" cmd /k "title NEXARION Frontend (Vite) && cd /d "%ROOT_DIR%frontend" && npm run dev"
    echo       [OK] Frontend server started at http://localhost:5173
) else (
    echo       [ERROR] Frontend directory not found!
    pause
    exit /b 1
)

echo.
echo =====================================================================
echo                 All NEXARION Services Are Online!
echo =====================================================================
echo   * Web Dashboard : http://localhost:5173
echo   * Backend API   : http://127.0.0.1:8000
echo   * API Docs      : http://127.0.0.1:8000/docs
echo   * Ollama API    : http://localhost:11434
echo =====================================================================
echo.
echo Press any key to open the Web Dashboard in your default browser...
pause >NUL
start http://localhost:5173
