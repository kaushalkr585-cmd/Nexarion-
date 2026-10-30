@echo off
title NEXARION — Stopping System Services

echo =====================================================================
echo                Stopping NEXARION System Services
echo =====================================================================
echo.

echo [1/3] Stopping Node / Vite Frontend processes...
taskkill /F /IM node.exe /FI "WINDOWTITLE eq NEXARION Frontend*" 2>NUL
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq NEXARION Frontend*" 2>NUL

echo [2/3] Stopping Python / Uvicorn Backend processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq NEXARION Backend*" 2>NUL
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq NEXARION Backend*" 2>NUL

echo [3/3] Done. Services stopped.
echo =====================================================================
timeout /t 2 /nobreak >NUL
