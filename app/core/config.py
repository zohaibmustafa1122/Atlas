"""Central application configuration.

All configuration is read from environment variables (optionally loaded
from a local .env file). Nothing here should be hard-coded per-machine --
that is the whole point of keeping a single Settings object.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: two levels up from this file (app/core/config.py -> app -> root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ATLAS"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'atlas.db'}"

    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_data_dir: Path = PROJECT_ROOT / "data" / "processed"
    synthetic_data_dir: Path = PROJECT_ROOT / "data" / "synthetic"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Only used if anthropic_api_key is set. A small/fast model is enough
    # for explaining already-retrieved evidence -- this is not a reasoning
    # task that needs a larger model.
    llm_model: str = "claude-haiku-4-5-20251001"

    def ensure_data_dirs(self) -> None:
        """Create the data directories on disk if they don't already exist."""
        for directory in (self.raw_data_dir, self.processed_data_dir, self.synthetic_data_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so the .env file is parsed once."""
    return Settings()
