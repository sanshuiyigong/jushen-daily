@echo off
chcp 65001 >nul
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0

set PY=C:\ProgramData\anaconda3\envs\yolov5\python.exe

if not exist "%PY%" (
  echo [ERROR] Python not found at %PY%
  echo Edit this file and fix the PY path.
  pause
  exit /b 1
)

"%PY%" "%~dp0run.py" --open %*
set CODE=%ERRORLEVEL%

echo.
if not "%CODE%"=="0" (
  echo [FAILED] exit code %CODE%
) else (
  echo [OK] reading/queue.md updated
)
echo.
pause
