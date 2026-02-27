@echo off
chcp 65001 >nul
title 卸载开机自启动
cd /d "%~dp0"
python install.py uninstall
echo.
pause
