@echo off
title Ambi Climate Local Hub
cd /d "%~dp0"
echo ========================================================
echo   Starting Ambi Climate Local Hub (192.168.1.138)
echo ========================================================
echo.
python ambi_hub.py
if errorlevel 1 (
    echo [ERROR] Script stopped with error.
    pause
)
