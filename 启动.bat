@echo off
chcp 65001 >nul
setlocal
set PYTHONIOENCODING=utf-8

rem 项目根目录：写死绝对路径，这样这个 bat 被复制到任何地方都能用；
rem 如果哪天项目搬走了，下面的 if not exist 会退回「bat 自己所在目录」。
set "PROJ=D:\2026一次深刻而迫切的转变\jushen-daily"
if not exist "%PROJ%\run.py" set "PROJ=%~dp0"

set PYTHONPATH=%PROJ%
set PY=C:\ProgramData\anaconda3\envs\yolov5\python.exe

if not exist "%PY%" (
  echo [ERROR] Python not found at %PY%
  echo Edit this file and fix the PY path.
  pause
  exit /b 1
)
if not exist "%PROJ%\run.py" (
  echo [ERROR] run.py not found in %PROJ%
  echo The project folder may have been moved.
  pause
  exit /b 1
)

cd /d "%PROJ%"

echo.
echo [1/2] Syncing state from cloud...
git -C "%PROJ%" pull --ff-only --quiet 1>nul 2>nul
if errorlevel 1 (
  echo       skipped - no network, or the proxy is not running
  echo       ^(local dedupe may be stale; the cloud copy is still correct^)
) else (
  echo       ok
)

echo [2/2] Generating today's digest...
echo.
"%PY%" "%PROJ%\run.py" --open %*
set CODE=%ERRORLEVEL%

echo.
if not "%CODE%"=="0" (
  echo [FAILED] exit code %CODE%
) else (
  echo [OK] reading\queue.md updated
)
echo.
pause
