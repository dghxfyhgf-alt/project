#!/bin/bash
# Startup script for Macau Navigation Backend
# Run from project root: ./start_backend.sh

cd "$(dirname "$0")"
if [ -f venv/bin/activate ]; then source venv/bin/activate; fi
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload