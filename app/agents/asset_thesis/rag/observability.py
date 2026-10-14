"""Per-operation correlation and single-owner failure logging for filing RAG."""

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_RUN_ID: ContextVar[str | None] = ContextVar("filing_rag_run_id", default=None)
_FAILURE_LOGGED: ContextVar[bool] = ContextVar(
    "filing_rag_failure_logged", default=False
)


@contextmanager
def rag_run(run_id: str | None = None) -> Iterator[str]:
    current = _RUN_ID.get()
    if current is not None and (run_id is None or run_id == current):
        yield current
        return
    run_token = _RUN_ID.set(run_id or uuid4().hex)
    failure_token = _FAILURE_LOGGED.set(False)
    try:
        yield _RUN_ID.get() or "-"
    finally:
        _FAILURE_LOGGED.reset(failure_token)
        _RUN_ID.reset(run_token)


def current_run_id() -> str:
    return _RUN_ID.get() or "-"


def preview(text: str, limit: int = 160) -> str:
    return text[:limit].replace("\n", "\\n").replace("\r", "\\r")


def log_failure_once(logger: logging.Logger, stage: str, *, ids: str = "") -> None:
    if _FAILURE_LOGGED.get():
        return
    _FAILURE_LOGGED.set(True)
    logger.error(
        "thesis_rag.%s.failed run_id=%s %s reason=%s",
        stage,
        current_run_id(),
        ids,
        sys.exception(),
        exc_info=True,
    )
