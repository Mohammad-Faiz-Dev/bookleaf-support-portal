"""Vercel Python entrypoint: exposes the FastAPI app from backend/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402,F401
from app.seed import seed  # noqa: E402

# Serverless cold starts may skip lifespan events; create tables + seed (idempotent, only when empty).
Base.metadata.create_all(engine)
with SessionLocal() as _db:
    seed(_db)
