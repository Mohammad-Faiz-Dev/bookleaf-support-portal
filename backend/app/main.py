import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, auth, author
from .config import get_settings
from .db import engine, init_db
from .errors import register_error_handlers
from .models import Category, Priority, TicketStatus
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(seed)
    yield


app = FastAPI(title="BookLeaf Author Support Portal API", version="1.0.0", lifespan=lifespan,
              description="REST API for the author portal and the admin support desk. Auth: `Authorization: Bearer <token>` from POST /api/auth/login.")
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(author.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["meta"])
def health():
    from sqlalchemy import text
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": engine.dialect.name, "db_ok": db_ok, "ai_enabled": bool(get_settings().ai_api_key), "provider": get_settings().ai_provider, "model": get_settings().ai_model}


@app.get("/api/meta", tags=["meta"])
def meta():
    return {"statuses": [s.value for s in TicketStatus], "categories": [c.value for c in Category],
            "priorities": [p.value for p in Priority]}


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")
