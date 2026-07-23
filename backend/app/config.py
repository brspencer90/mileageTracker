"""Application settings, read from environment variables and an optional .env file.

Env vars (see docs/IMPLEMENTATION_PLAN.md section 3):
    MT_DB_PATH     SQLite file path (parent dir auto-created). Default ./data/mileage.db
    MT_STATIC_DIR  Built SPA dir; if it doesn't exist, static serving is skipped.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MT_", env_file=".env", extra="ignore")

    db_path: str = "./data/mileage.db"
    static_dir: str = "../frontend/dist"
