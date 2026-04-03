"""
Basis x Squads Guard — Standalone entry point.
Run: python -m squads-guard.main
Or:  python squads-guard/main.py
"""

import os
import sys
import logging

# Allow running as `python squads-guard/main.py` from repo root
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI

from squads_guard.router import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Basis Squads Guard", version="1.0.0")
app.include_router(router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)
