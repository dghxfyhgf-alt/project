#!/bin/bash
# Startup script for Macau Navigation Backend
# Run from project root: ./start_backend.sh

cd "$(dirname "$0")/backend"
source ../venv/bin/activate
export PYTHONPATH=.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload