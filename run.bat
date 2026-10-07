@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :environment_ready

rem Pick an interpreter to BUILD the venv with. On Windows `python` is often the
rem Microsoft Store placeholder: it IS on PATH, but running it just prints
rem "Python was not found" and exits non-zero -- while a real Python sits behind
rem the `py` launcher. So try both. Test by running code (`-c "import sys"`)
rem rather than `--version`, which is what the placeholder also fails on.
set "PY_BOOT="
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_BOOT=python"
if not defined PY_BOOT (
  py -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY_BOOT=py"
)
if not defined PY_BOOT (
  echo [Agentorium] Python not found. Please install Python 3.10 or newer.
  echo              On Windows, a python.org install also works via the "py" launcher.
  pause
  exit /b 1
)

echo [Agentorium] Creating project environment...
"%PY_BOOT%" -m venv .venv
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
