@echo off
cd /d "%~dp0.."
if not exist ".venv-phone\Scripts\python.exe" (
  echo First install: python -m venv .venv-phone
  echo Then: .venv-phone\Scripts\python.exe -m pip install -r backend/requirements.txt
  pause
  exit /b 1
)
".venv-phone\Scripts\python.exe" -X utf8 scripts/start_phone_pilot.py
pause
