@echo off
title Ambi Climate Local Hub
cd /d "%~dp0"
echo ========================================================
echo   Starting Ambi Climate Local Hub & Web Dashboard (:9090)
echo ========================================================
echo.
python ambi_hub.py
if errorlevel 1 (
    echo [ERROR] Script stopped with error.
    pause
)
