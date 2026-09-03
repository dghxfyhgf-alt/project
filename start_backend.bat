@echo off
REM Startup script for Macau Navigation Backend (Windows)
REM Run from project root: start_backend.bat

cd backend
call ..\venv\Scripts\activate.bat
set PYTHONPATH=.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload