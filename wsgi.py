"""Stable production WSGI entrypoint for Railway/Gunicorn.

Keeps the backend package on sys.path so imports such as ``ai_provider`` and
``edu_app`` continue to work regardless of Gunicorn's working directory.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import app  # noqa: E402,F401

__all__ = ["app"]
