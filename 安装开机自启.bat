@echo off
chcp 65001 >nul
title 安装开机自启动
cd /d "%~dp0"
python install.py install
echo.
pause
