import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from time import perf_counter

from app.agents.asset_thesis.rag.identity import make_document_id
from app.agents.asset_thesis.rag.observability import current_run_id
from app.domain.schemas.thesis_rag import FilingDocument, FilingDocumentVersion

logger = logging.getLogger(__name__)


class FileRawFilingStore:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    async def save(self, document: FilingDocument, raw_html: bytes) -> FilingDocument:
        if document.document_id != make_document_id(
            document.issuer_cik, document.accession_number, document.filename
        ):
            raise ValueError("Filing document ID does not match its SEC identity")
        digest = hashlib.sha256(raw_html).hexdigest()
        if document.content_sha256 is not None and document.content_sha256 != digest:
            raise ValueError("Raw HTML does not match the document content hash")
        reference = self._reference(digest)
        if document.raw_file_ref is not None and document.raw_file_ref != reference:
            raise ValueError("Raw HTML reference does not match its content hash")
        started = perf_counter()
        cache_hit = await asyncio.to_thread(self._write, reference, raw_html, digest)
        logger.info(
            "thesis_rag.raw_store.saved run_id=%s document_id=%s bytes=%d "
            "cache_hit=%s duration_ms=%.1f",
            current_run_id(),
            document.document_id,
            len(raw_html),
            cache_hit,
            (perf_counter() - started) * 1000,
        )
        return document.model_copy(
            update={"raw_file_ref": reference, "content_sha256": digest}
        )

    async def read(self, document: FilingDocumentVersion) -> bytes:
        raw = await asyncio.to_thread(
            (self._root / self._reference(document.content_sha256)).read_bytes
        )
        if hashlib.sha256(raw).hexdigest() != document.content_sha256:
            raise ValueError("Stored SEC HTML failed its content hash check")
        return raw

    @staticmethod
    def _reference(digest: str) -> str:
        return f"sha256/{digest[:2]}/{digest}.html"

    def _write(self, reference: str, raw_html: bytes, digest: str) -> bool:
        target = self._root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            target.exists()
            and hashlib.sha256(target.read_bytes()).hexdigest() == digest
        ):
            return True
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
                temporary = file.name
                file.write(raw_html)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
            return False
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
