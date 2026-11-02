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

echo.
echo [1/2] Syncing state from cloud...
git -C "%~dp0" pull --ff-only --quiet 1>nul 2>nul
if errorlevel 1 (
  echo       skipped - no network, or the proxy is not running
  echo       ^(local dedupe may be stale; the cloud copy is still correct^)
) else (
  echo       ok
)

echo [2/2] Generating today's digest...
echo.
"%PY%" "%~dp0run.py" --open %*
set CODE=%ERRORLEVEL%

echo.
if not "%CODE%"=="0" (
  echo [FAILED] exit code %CODE%
) else (
  echo [OK] reading\queue.md updated
)
echo.
pause
