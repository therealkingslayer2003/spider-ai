import re
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


class ChatTokenCounter(Protocol):
    @property
    def count_kind(self) -> Literal["local_tokenizer", "estimated"]: ...

    @property
    def version(self) -> str: ...

    def count_text(self, text: str) -> int: ...

    def count_prompt(self, prompt: str) -> int: ...


class ChatTokenizerUnavailableError(RuntimeError):
    """The configured chat tokenizer cannot be loaded from local assets."""


@cache
def _load_chat_tokenizer(tokenizer_id: str, revision: str, cache_dir: str) -> Any:
    try:
        from huggingface_hub import try_to_load_from_cache
        from transformers import AutoTokenizer

        config_path = try_to_load_from_cache(
            tokenizer_id,
            "tokenizer_config.json",
            cache_dir=cache_dir,
            revision=revision,
        )
        if not isinstance(config_path, str):
            raise FileNotFoundError("Pinned chat tokenizer snapshot is not cached")
        tokenizer = AutoTokenizer.from_pretrained(
            Path(config_path).parent,
            local_files_only=True,
            use_fast=True,
            trust_remote_code=False,
        )
    except (ImportError, OSError, ValueError) as exc:
        raise ChatTokenizerUnavailableError(
            "Pinned chat tokenizer assets are unavailable locally; "
            "run the setup in docs/thesis_rag_skeleton.md"
        ) from exc
    if not tokenizer.is_fast or not tokenizer.chat_template:
        raise ChatTokenizerUnavailableError(
            "Chat tokenizer needs a fast tokenizer and chat template"
        )
    return tokenizer


class LocalChatTokenCounter:
    """Count the single-user chat request sent to the configured Ollama model."""

    count_kind: Literal["local_tokenizer"] = "local_tokenizer"

    def __init__(
        self,
        *,
        model: str,
        tokenizer_model: str,
        tokenizer_id: str,
        tokenizer_revision: str,
        cache_dir: Path,
        tokenizer: Any = None,
    ) -> None:
        if model != tokenizer_model:
            raise ValueError("Chat tokenizer is configured for another Ollama model")
        if not tokenizer_id or not tokenizer_revision:
            raise ValueError("Chat tokenizer identity and revision are required")
        self.version = (
            f"hf-chat:{tokenizer_id}@{tokenizer_revision};ollama={model};"
            "single-user-chat-template-v1;truncation=false"
        )
        self._tokenizer_id = tokenizer_id
        self._tokenizer_revision = tokenizer_revision
        self._cache_dir = str(cache_dir.expanduser().resolve())
        self._tokenizer = tokenizer

    def _get_tokenizer(self) -> Any:
        if self._tokenizer is None:
            with _TOKENIZER_LOAD_LOCK:
                if self._tokenizer is None:
                    self._tokenizer = _load_chat_tokenizer(
                        self._tokenizer_id,
                        self._tokenizer_revision,
                        self._cache_dir,
                    )
        return self._tokenizer

    def ensure_available(self) -> None:
        """Resolve local assets before choosing the generation budget."""
        self._get_tokenizer()

    def count_text(self, text: str) -> int:
        return len(
            self._get_tokenizer().encode(
                text, add_special_tokens=False, truncation=False
            )
        )

    def count_prompt(self, prompt: str) -> int:
        return len(
            self._get_tokenizer().apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=True,
                add_generation_prompt=True,
                truncation=False,
            )
        )


_ESTIMATED_TOKENS = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class EstimatedChatTokenCounter:
    """Offline text-size proxy for chat models without a local tokenizer."""

    count_kind: Literal["estimated"] = "estimated"

    def __init__(self, model: str) -> None:
        if not model.strip():
            raise ValueError("The chat model is required")
        self.version = (
            f"estimated-chat:{model};word-punctuation-or-utf8-bytes-v1;"
            "prompt=text-only"
        )

    def count_text(self, text: str) -> int:
        return max(len(_ESTIMATED_TOKENS.findall(text)), (len(text.encode()) + 2) // 3)

    def count_prompt(self, prompt: str) -> int:
        # Unknown chat framing is covered by the configured fallback margin.
        return self.count_text(prompt)


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
