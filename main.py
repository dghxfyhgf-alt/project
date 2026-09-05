"""Compatibility entry point.

The production application lives in ``backend.main``. Running
``uvicorn main:app`` from the repository root remains supported.
"""

from backend.main import app

__all__ = ["app"]
