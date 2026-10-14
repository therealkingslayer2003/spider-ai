from functools import cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Protocol

EmbeddingTask = Literal["document", "query"]
TOKENIZER_ID = "nomic-ai/nomic-embed-text-v1.5"
TOKENIZER_REVISION = "e9b6763023c676ca8431644204f50c2b100d9aab"
_PREFIXES: dict[EmbeddingTask, str] = {
    "document": "search_document:",
    "query": "search_query:",
}
_OLLAMA_MODELS = {
    "nomic-embed-text",
    "nomic-embed-text:latest",
    "nomic-embed-text:v1.5",
    "nomic-embed-text:137m-v1.5-fp16",
}
_TOKENIZER_LOAD_LOCK = Lock()


class TokenCounter(Protocol):
    @property
    def version(self) -> str: ...

    def count_text(self, text: str) -> int: ...

    def format_embedding_input(self, text: str, task: EmbeddingTask) -> str: ...

    def count_embedding_input(self, text: str, task: EmbeddingTask) -> int: ...


def validate_nomic_ollama_model(model: str) -> None:
    """Accept only Ollama names published for Nomic Embed Text v1.5."""
    if model not in _OLLAMA_MODELS:
        raise ValueError(
            "The pinned Nomic v1.5 tokenizer requires an Ollama "
            "nomic-embed-text v1.5 model"
        )


@cache
def _load_tokenizer(cache_dir: str) -> Any:
    from transformers import AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            TOKENIZER_ID,
            revision=TOKENIZER_REVISION,
            cache_dir=cache_dir,
            local_files_only=True,
            use_fast=True,
            trust_remote_code=False,
        )
    except OSError as exc:
        raise RuntimeError(
            "Pinned Nomic tokenizer assets are unavailable locally; "
            "run the one-time setup in docs/thesis_rag_skeleton.md"
        ) from exc
    if (
        not tokenizer.is_fast
        or tokenizer.cls_token_id != 101
        or tokenizer.sep_token_id != 102
        or tokenizer.vocab_size != 30522
    ):
        raise RuntimeError("Cached Nomic tokenizer has unexpected BERT metadata")
    return tokenizer


class NomicTokenCounter:
    """Text counts omit specials; embedding counts include prefix and CLS/SEP."""

    version = (
        f"hf:{TOKENIZER_ID}@{TOKENIZER_REVISION};fast-bert-v1;"
        "text-special=false;embedding-special=true;prefixes=v1;truncation=false"
    )

    def __init__(self, cache_dir: Path, *, tokenizer: Any = None) -> None:
        self._cache_dir = str(cache_dir.expanduser().resolve())
        self._tokenizer = tokenizer

    def _get_tokenizer(self) -> Any:
        if self._tokenizer is None:
            # @cache alone can invoke a cold loader twice under concurrent calls.
            with _TOKENIZER_LOAD_LOCK:
                if self._tokenizer is None:
                    self._tokenizer = _load_tokenizer(self._cache_dir)
        return self._tokenizer

    def count_text(self, text: str) -> int:
        return len(
            self._get_tokenizer().encode(
                text, add_special_tokens=False, truncation=False
            )
        )

    def format_embedding_input(self, text: str, task: EmbeddingTask) -> str:
        value = text.strip()
        if not value:
            raise ValueError("Embedding input is empty")
        prefix = _PREFIXES[task]
        for known in _PREFIXES.values():
            if value.startswith(known):
                if known != prefix:
                    raise ValueError("Embedding input has the wrong task prefix")
                value = value[len(known) :].strip()
                if not value or any(
                    value.startswith(other) for other in _PREFIXES.values()
                ):
                    raise ValueError("Embedding input has an empty or duplicate prefix")
                return f"{prefix} {value}"
        return f"{prefix} {value}"

    def count_embedding_input(self, text: str, task: EmbeddingTask) -> int:
        formatted = self.format_embedding_input(text, task)
        return len(
            self._get_tokenizer().encode(
                formatted, add_special_tokens=True, truncation=False
            )
        )
