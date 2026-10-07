@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :environment_ready

python --version >nul 2>&1
if errorlevel 1 (
  echo [Agentorium] Python not found. Please install Python 3.10 or newer.
  pause
  exit /b 1
)

echo [Agentorium] Creating project environment...
python -m venv .venv
if errorlevel 1 goto :error

:environment_ready
set "APP_PYTHON=.venv\Scripts\python.exe"
if /I "%AGENTORIUM_CHECK_ONLY%"=="1" (
  "%APP_PYTHON%" --version
  if errorlevel 1 goto :error
  echo [Agentorium] Launch script and environment check passed.
  exit /b 0
)

echo [Agentorium] Checking runtime dependencies...
"%APP_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo [Agentorium] Starting...
"%APP_PYTHON%" main.py
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo [Agentorium] Dependency install or launch failed. See the messages above.
pause
exit /b 1
