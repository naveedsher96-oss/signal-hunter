@echo off
title Signal Hunter (local)
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during setup, then run this again.
  pause
  exit /b
)
echo Checking requirements (first run takes a minute)...
python -m pip install --quiet --disable-pip-version-check flask requests openpyxl
echo.
python webapp.py
pause
