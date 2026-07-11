@echo off
title Turbo Stream Bridge
echo ========================================
echo  Starting Turbo Stream Bridge on Windows
echo ========================================
cd /d "%~dp0"
python streaming\stream_bridge.py
pause
