@echo off
chcp 65001 >nul
setlocal
set PYTHONIOENCODING=utf-8

rem 项目根目录：写死绝对路径，这样这个 bat 被复制到任何地方都能用；
rem 如果哪天项目搬走了，下面的 if not exist 会退回「bat 自己所在目录」。
set "PROJ=D:\2026一次深刻而迫切的转变\jushen-daily"
if not exist "%PROJ%\server.py" set "PROJ=%~dp0"

set PYTHONPATH=%PROJ%
set PY=C:\ProgramData\anaconda3\envs\yolov5\python.exe

if not exist "%PY%" (
  echo [ERROR] Python not found at %PY%
  pause
  exit /b 1
)
if not exist "%PROJ%\server.py" (
  echo [ERROR] server.py not found in %PROJ%
  echo The project folder may have been moved.
  pause
  exit /b 1
)

title jushen-daily server
cd /d "%PROJ%"
"%PY%" "%PROJ%\server.py"
echo.
pause
