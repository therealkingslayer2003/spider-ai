from pathlib import Path
from typing import Any

import pytest

from app.llm import tokenization
from app.llm.tokenization import NomicTokenCounter, validate_nomic_ollama_model


class FakeBertTokenizer:
    is_fast = True
    cls_token_id = 101
    sep_token_id = 102
    vocab_size = 30522

    def __init__(self) -> None:
        self.calls: list[tuple[bool, bool]] = []

    def encode(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> list[int]:
        self.calls.append((add_special_tokens, truncation))
        size = len(text.split()) + (2 if add_special_tokens else 0)
        return list(range(size))


def test_text_counts_exclude_specials_and_embedding_counts_include_prefix() -> None:
    tokenizer = FakeBertTokenizer()
    counter = NomicTokenCounter(Path("/unused"), tokenizer=tokenizer)
    assert counter.count_text("Net revenue rose.") == 3
    assert counter.count_embedding_input("Net revenue rose.", "document") == 6
    assert counter.count_embedding_input("Net revenue rose.", "query") == 6
    assert tokenizer.calls == [(False, False), (True, False), (True, False)]
    assert tokenization.TOKENIZER_REVISION in counter.version


def test_formatting_is_idempotent_and_rejects_conflicting_prefixes() -> None:
    counter = NomicTokenCounter(Path("/unused"), tokenizer=FakeBertTokenizer())
    assert (
        counter.format_embedding_input("  search_document: revenue  ", "document")
        == "search_document: revenue"
    )
    assert counter.format_embedding_input("revenue", "query") == "search_query: revenue"
    with pytest.raises(ValueError, match="wrong task prefix"):
        counter.format_embedding_input("search_query: revenue", "document")
    with pytest.raises(ValueError, match="duplicate prefix"):
        counter.format_embedding_input(
            "search_document: search_document: revenue", "document"
        )


def test_pinned_tokenizer_loads_once_and_requires_offline_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from transformers import AutoTokenizer

    calls: list[dict[str, Any]] = []
    fake = FakeBertTokenizer()

    def load(*_args: object, **kwargs: Any) -> FakeBertTokenizer:
        calls.append(kwargs)
        return fake

    monkeypatch.setattr(AutoTokenizer, "from_pretrained", load)
    tokenization._load_tokenizer.cache_clear()
    try:
        first = NomicTokenCounter(tmp_path)
        second = NomicTokenCounter(tmp_path)
        assert first.count_text("one two") == second.count_text("one two") == 2
        assert len(calls) == 1
        assert calls[0]["revision"] == tokenization.TOKENIZER_REVISION
        assert calls[0]["local_files_only"] is True
        assert calls[0]["use_fast"] is True
        assert calls[0]["trust_remote_code"] is False
    finally:
        tokenization._load_tokenizer.cache_clear()


def test_only_nomic_v15_ollama_model_names_are_accepted() -> None:
    validate_nomic_ollama_model("nomic-embed-text:v1.5")
    validate_nomic_ollama_model("nomic-embed-text")
    with pytest.raises(ValueError, match="requires an Ollama nomic-embed-text"):
        validate_nomic_ollama_model("other-embedding-model")
