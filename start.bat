@echo off
title Nexarion Launcher
cd /d "%~dp0"

echo ====================================================
echo        NEXARION - Multi-Agent Code Review
echo ====================================================
echo.

REM 1. Check for .env file
if not exist .env (
    echo [INFO] .env not found. Initializing from .env.example...
    copy .env.example .env >nul
    echo [INFO] .env file created successfully.
)

REM 2. Check for Python virtual environment
if not exist .venv\Scripts\python.exe (
    echo [INFO] Virtual environment .venv not found.
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
    echo [INFO] Installing Python dependencies...
    call .\.venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
)

REM 3. Check for frontend node_modules
if not exist frontend\node_modules (
    echo [INFO] Frontend dependencies not found.
    echo [INFO] Installing npm packages in /frontend...
    cd frontend
    call npm install
    cd ..
)

echo.
echo [1/2] Launching Backend API on http://localhost:8000...
start "Nexarion Backend - FastAPI (Port 8000)" cmd /k "call .\.venv\Scripts\activate.bat && .\.venv\Scripts\python.exe -m uvicorn code_review.web.app:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching Frontend Vite Server on http://localhost:5173...
start "Nexarion Frontend - Vite (Port 5173)" cmd /k "cd frontend && npm run dev"

REM Wait 3 seconds for servers to start
ping 127.0.0.1 -n 4 >nul

echo.
echo ====================================================
echo           NEXARION is now up and running!
echo ====================================================
echo   - Web Dashboard : http://localhost:5173
echo   - Backend API   : http://localhost:8000
echo   - API Swagger   : http://localhost:8000/docs
echo ====================================================
echo   To stop Nexarion, close the Backend and Frontend
echo   windows or press Ctrl+C inside them.
echo ====================================================
echo.

REM Open default web browser
start "" "http://localhost:5173"

pause
