"""Runtime configuration, read from environment variables (never hardcoded secrets)."""
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'bookleaf.db'}")
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me-in-production")
        self.jwt_ttl_minutes = int(os.getenv("JWT_TTL_MINUTES", "720"))
        # AI provider (any OpenAI-compatible chat-completions endpoint)
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
