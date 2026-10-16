"""Runtime configuration, read from environment variables (never hardcoded secrets)."""
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _database_url() -> str:
    """DATABASE_URL / POSTGRES_URL (e.g. Neon) if set; else SQLite (in /tmp on Vercel, which is ephemeral)."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/bookleaf.db"
    return f"sqlite:///{BASE_DIR / 'bookleaf.db'}"


class Settings:
    def __init__(self) -> None:
        self.database_url = _database_url()
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me-in-production")
        self.jwt_ttl_minutes = int(os.getenv("JWT_TTL_MINUTES", "720"))
        # AI provider: Google Gemini if GEMINI_API_KEY is set, else any OpenAI-compatible endpoint
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.ai_provider = os.getenv("AI_PROVIDER", "gemini" if gemini_key else "openai")
        if self.ai_provider == "gemini":
            self.ai_api_key = gemini_key
            self.ai_base_url = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
            self.ai_model = os.getenv("AI_MODEL", "gemini-3.6-flash")
            # tried in order if the primary model is overloaded (429/503) or retired (404)
            self.ai_fallback_models = [m for m in os.getenv("AI_FALLBACK_MODELS", "gemini-3.5-flash").split(",") if m]
        else:
            self.ai_api_key = os.getenv("OPENAI_API_KEY", "")
            self.ai_base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
            self.ai_model = os.getenv("AI_MODEL", "gpt-4o-mini")
        self.ai_timeout_s = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
        self.seed_file = Path(os.getenv("SEED_FILE", str(BASE_DIR / "bookleaf_sample_data.json")))
        self.default_author_password = os.getenv("SEED_AUTHOR_PASSWORD", "author123")
        self.default_admin_password = os.getenv("SEED_ADMIN_PASSWORD", "admin123")


@lru_cache
def get_settings() -> Settings:
    return Settings()
