from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "spider-ai.db"


def default_sec_filings_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sec-filings"


def default_chroma_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "chroma"


def default_tokenizer_cache_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "huggingface"


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
    spider_ai_sec_filings_path: Path = Field(default_factory=default_sec_filings_path)
    spider_ai_chroma_path: Path = Field(default_factory=default_chroma_path)
    thesis_rag_tokenizer_cache_path: Path = Field(
        default_factory=default_tokenizer_cache_path
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:14b"
    thesis_rag_chat_tokenizer_model: str = "qwen3:14b"
    thesis_rag_chat_tokenizer_id: str = "Qwen/Qwen3-14B"
    thesis_rag_chat_tokenizer_revision: str = "40c069824f4251a91eefaf281ebe4c544efd3e18"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_embedding_model_revision: str = "local-v1"
    ollama_embedding_batch_size: int = Field(default=32, gt=0)
    ollama_embedding_expected_dimensions: int = Field(default=768, gt=0)
    ollama_embedding_max_input_chars: int = Field(default=1600, gt=0)
    ollama_embedding_max_input_tokens: int = Field(default=450, gt=0)
    thesis_rag_chunk_max_chars: int = Field(default=1600, ge=200)
    thesis_rag_chunk_max_tokens: int = Field(default=450, ge=50)
    thesis_rag_chunk_overlap_tokens: int = Field(default=40, ge=0)
    thesis_rag_retrieval_top_k: int = Field(default=6, gt=0)
    thesis_rag_retrieval_candidate_k: int = Field(default=16, gt=0)
    thesis_rag_retrieval_rerank_enabled: bool = True
    thesis_rag_generation_reserved_output_tokens: int = Field(default=2048, gt=0)
    thesis_rag_generation_safety_margin_tokens: int = Field(default=128, ge=0)
    thesis_rag_generation_fallback_safety_margin_tokens: int = Field(
        default=512, ge=0
    )
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 16384
    fmp_enabled: bool = False
    fmp_api_key: str | None = None
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    sec_user_agent: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_thesis_rag_limits(self) -> "Settings":
        if self.thesis_rag_chunk_max_chars > self.ollama_embedding_max_input_chars:
            raise ValueError("Thesis RAG chunks exceed the embedding character limit")
        if self.thesis_rag_chunk_max_tokens > self.ollama_embedding_max_input_tokens:
            raise ValueError("Thesis RAG chunks exceed the embedding token limit")
        if self.thesis_rag_retrieval_candidate_k < self.thesis_rag_retrieval_top_k:
            raise ValueError("Thesis RAG candidate limit must cover the final limit")
        if (
            self.thesis_rag_generation_reserved_output_tokens
            + max(
                self.thesis_rag_generation_safety_margin_tokens,
                self.thesis_rag_generation_fallback_safety_margin_tokens,
            )
            >= self.ollama_num_ctx
        ):
            raise ValueError("Thesis RAG output reserve exceeds chat context window")
        if (
            self.thesis_rag_chunk_overlap_tokens
            >= self.thesis_rag_chunk_max_tokens // 2
        ):
            raise ValueError(
                "Thesis RAG overlap must be less than half the chunk limit"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
