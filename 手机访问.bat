@echo off
chcp 65001 >nul
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0
set PY=C:\ProgramData\anaconda3\envs\yolov5\python.exe

if not exist "%PY%" (
  echo [ERROR] Python not found at %PY%
  pause
  exit /b 1
)

title jushen-daily server
"%PY%" "%~dp0server.py"
echo.
pause
