"""Application settings, read from environment variables and .env files.

The backend now talks to Microsoft SQL Server (pyodbc). The connection string
lives in the repo-root ``.env`` under the (un-prefixed) key ``sqlss_conn_str``;
``MT_STATIC_DIR`` (built SPA dir) lives in ``backend/.env``. Both files are read
here, with backend/.env taking precedence, and real environment variables
overriding both (that is how the tests point the app at ``mileageTracker_test``).
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ROOT_DIR = _BACKEND_DIR.parent
_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


class Settings(BaseSettings):
    # Read the root .env first, then backend/.env (later file wins); real env
    # vars still take precedence over both.
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_DIR / ".env"), str(_BACKEND_DIR / ".env")),
        extra="ignore",
        case_sensitive=False,
    )

    # Raw SQL Server connection fragment (SERVER=..;DATABASE=..;UID=..;PWD=..).
    sqlss_conn_str: str = ""
    static_dir: str = Field(default="../frontend/dist", alias="MT_STATIC_DIR")

    def pyodbc_conn_str(self) -> str:
        """Full pyodbc connection string (driver + fragment + TLS opt-out)."""
        return (
            f"DRIVER={{{_ODBC_DRIVER}}};{self.sqlss_conn_str};"
            "TrustServerCertificate=Yes"
        )
