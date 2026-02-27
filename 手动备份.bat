@echo off
chcp 65001 >nul
title 手动备份播放列表
cd /d "%~dp0"
python main.py backup
echo.
pause
