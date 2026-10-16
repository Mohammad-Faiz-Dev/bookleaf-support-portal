from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings

_url = get_settings().database_url
IS_SQLITE = _url.startswith("sqlite")
if IS_SQLITE:
    engine = create_engine(_url, connect_args={"check_same_thread": False})
else:
    # Serverless + PgBouncer/Supavisor transaction pooler: no client-side pool, no prepared statements.
    engine = create_engine(_url, poolclass=NullPool, pool_pre_ping=True,
                           connect_args={"prepare_threshold": None, "connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(seed_fn) -> None:
    """Create tables and seed once. On Postgres a transaction-scoped advisory lock makes this
    race-safe when many serverless instances cold-start at the same time."""
    if IS_SQLITE:
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_fn(db)
        return
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(814207)"))
        Base.metadata.create_all(conn)
        with SessionLocal(bind=conn, join_transaction_mode="create_savepoint") as db:
            seed_fn(db)
