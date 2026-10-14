import hashlib
import json
import logging
import math
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from ollama import AsyncClient

from app.agents.asset_thesis.rag.observability import (
    log_failure_once,
    preview,
    rag_run,
)
from app.domain.schemas.thesis_rag import FilingChunk
from app.llm.tokenization import (
    EmbeddingTask,
    TokenCounter,
    validate_nomic_ollama_model,
)

logger = logging.getLogger(__name__)


class OllamaFilingEmbeddingGenerator:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        model_revision: str,
        batch_size: int,
        max_input_chars: int,
        max_input_tokens: int,
        token_counter: TokenCounter,
        client: Any = None,
    ) -> None:
        validate_nomic_ollama_model(model)
        if not model or not model_revision or batch_size <= 0:
            raise ValueError("Embedding model, revision and batch size are required")
        if max_input_chars <= 0 or max_input_tokens <= 0:
            raise ValueError("Embedding input bounds must be positive")
        self.model = model
        self.base_url = base_url
        self.batch_size = batch_size
        self.max_input_chars = max_input_chars
        self.max_input_tokens = max_input_tokens
        self._token_counter = token_counter
        self._client = client
        settings = {
            "provider": "ollama",
            "model": model,
            "revision": model_revision,
            "max_input_chars": max_input_chars,
            "max_input_tokens": max_input_tokens,
            "tokenizer": token_counter.version,
        }
        self.version = (
            "ollama-embed-v2-"
            + hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[
                :16
            ]
        )

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = AsyncClient(host=self.base_url)
        return self._client

    def _validate_text(self, text: str, task: EmbeddingTask) -> str:
        formatted = self._token_counter.format_embedding_input(text, task)
        if (
            len(formatted) > self.max_input_chars
            or self._token_counter.count_embedding_input(text, task)
            > self.max_input_tokens
        ):
            raise ValueError("Embedding input exceeds configured bounds")
        return formatted

    @staticmethod
    def _validate_vectors(
        vectors: Sequence[Sequence[float]], count: int
    ) -> list[list[float]]:
        if len(vectors) != count:
            raise RuntimeError("Embedding model returned an incomplete batch")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise RuntimeError("Embedding model returned inconsistent dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise RuntimeError("Embedding model returned a non-finite value")
        return [list(vector) for vector in vectors]

    async def embed_chunks(self, chunks: Sequence[FilingChunk]) -> list[list[float]]:
        with rag_run() as run_id:
            started = perf_counter()
            batch_id = "-"
            first_chunk_id = "-"
            logger.info(
                "thesis_rag.embed.start run_id=%s chunks=%d batch_size=%d model=%s",
                run_id,
                len(chunks),
                self.batch_size,
                self.model,
            )
            try:
                if not chunks:
                    raise ValueError("Embedding requires at least one filing chunk")
                formatted: list[str] = []
                for chunk in chunks:
                    if chunk.token_count != self._token_counter.count_text(chunk.text):
                        raise ValueError(
                            "Filing chunk token count does not match its text"
                        )
                    value = self._validate_text(chunk.text, "document")
                    formatted.append(value)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "thesis_rag.embed.input run_id=%s document_id=%s "
                            "chunk_id=%s chars=%d text_tokens=%d input_tokens=%d "
                            "preview=%r",
                            run_id,
                            chunk.document.document_id,
                            chunk.chunk_id,
                            len(value),
                            chunk.token_count,
                            self._token_counter.count_embedding_input(
                                chunk.text, "document"
                            ),
                            preview(value),
                        )
                client = self._get_client()
                vectors: list[list[float]] = []
                dimension: int | None = None
                for offset in range(0, len(chunks), self.batch_size):
                    batch_id = str(offset // self.batch_size)
                    batch = formatted[offset : offset + self.batch_size]
                    first_chunk_id = chunks[offset].chunk_id
                    batch_started = perf_counter()
                    logger.info(
                        "thesis_rag.embed.batch.start run_id=%s batch_id=%s "
                        "chunks=%d first_chunk_id=%s",
                        run_id,
                        batch_id,
                        len(batch),
                        chunks[offset].chunk_id,
                    )
                    response = await client.embed(
                        model=self.model, input=batch, truncate=False
                    )
                    result = self._validate_vectors(response.embeddings, len(batch))
                    if dimension is not None and len(result[0]) != dimension:
                        raise RuntimeError(
                            "Embedding dimension changed between batches"
                        )
                    dimension = len(result[0])
                    vectors.extend(result)
                    logger.info(
                        "thesis_rag.embed.batch.done run_id=%s batch_id=%s "
                        "vectors=%d dimensions=%d duration_ms=%.1f",
                        run_id,
                        batch_id,
                        len(result),
                        dimension,
                        (perf_counter() - batch_started) * 1000,
                    )
            except Exception:
                log_failure_once(
                    logger,
                    "embed",
                    ids=f"batch_id={batch_id} first_chunk_id={first_chunk_id}",
                )
                raise
            logger.info(
                "thesis_rag.embed.done run_id=%s chunks=%d batches=%d "
                "dimensions=%d duration_ms=%.1f",
                run_id,
                len(chunks),
                (len(chunks) + self.batch_size - 1) // self.batch_size,
                dimension or 0,
                (perf_counter() - started) * 1000,
            )
            return vectors

    async def embed_query(self, query: str) -> list[float]:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info("thesis_rag.embed_query.start run_id=%s", run_id)
            try:
                formatted = self._validate_text(query, "query")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "thesis_rag.embed_query.input run_id=%s chars=%d "
                        "input_tokens=%d query=%r",
                        run_id,
                        len(formatted),
                        self._token_counter.count_embedding_input(query, "query"),
                        preview(formatted),
                    )
                response = await self._get_client().embed(
                    model=self.model, input=[formatted], truncate=False
                )
                vector = self._validate_vectors(response.embeddings, 1)[0]
            except Exception:
                log_failure_once(logger, "embed_query")
                raise
            logger.info(
                "thesis_rag.embed_query.done run_id=%s dimensions=%d duration_ms=%.1f",
                run_id,
                len(vector),
                (perf_counter() - started) * 1000,
            )
            return vector
