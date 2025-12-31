import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Vault CLI"
    database_url: str = f"sqlite:///{Path.home()}/.vlt/vault.db"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "x-ai/grok-4.1-fast"
    openrouter_embedding_model: str = "qwen/qwen3-embedding-8b"
    
    model_config = SettingsConfigDict(
        env_prefix="VLT_",
        env_file=Path.home() / ".vlt" / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_db_path(self) -> Path:

        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.replace("sqlite:///", ""))
        return Path.home() / ".vlt" / "vault.db"

settings = Settings()

# Ensure the directory exists
db_path = settings.get_db_path()
if not db_path.parent.exists():
    db_path.parent.mkdir(parents=True, exist_ok=True)
