@echo off
REM Startup script for Macau Navigation Backend (Windows)
REM Run from project root: start_backend.bat

cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload