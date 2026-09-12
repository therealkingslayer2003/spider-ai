from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "spider-ai.db"


class Settings(BaseSettings):
    app_name: str = "Spider"
    app_env: str = "local"
    app_debug: bool = True
    app_pretty_logs: bool = True
    app_log_flow_steps: bool = True
    app_log_llm_prompts: bool = False
    app_log_llm_outputs: bool = False
    app_log_preview_chars: int = 3000

    api_v1_prefix: str = "/api/v1"

    spider_ai_db_path: Path = Field(default_factory=default_database_path)

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.2

    fmp_enabled: bool = False
    fmp_api_key: str | None = None
    fmp_base_url: str = "https://financialmodelingprep.com/stable"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
