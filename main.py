"""Thin launcher — prefer `cd backend && PYTHONPATH=. uvicorn app.main:app`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.main import run  # noqa: E402

if __name__ == "__main__":
    run()
