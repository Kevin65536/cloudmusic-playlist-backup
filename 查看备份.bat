@echo off
chcp 65001 >nul
title 播放列表备份管理
cd /d "%~dp0"
python main.py list
echo.
pause
