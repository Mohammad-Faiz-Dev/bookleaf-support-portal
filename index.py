"""Vercel Python entrypoint: exposes the FastAPI app from backend/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402,F401
from app.seed import seed  # noqa: E402

# Serverless cold starts may skip lifespan events; create tables + seed once (idempotent, lock-protected).
init_db(seed)
