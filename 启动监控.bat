@echo off
chcp 65001 >nul
title 网易云音乐播放列表守护程序
echo.
echo  正在启动播放列表监控...
echo  当网易云音乐的播放列表发生变化时，将自动创建备份。
echo.
cd /d "%~dp0"
python main.py watch
pause
