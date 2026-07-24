"""Streaming upload helpers with hard size cap and real MIME detection.

Avoids `await file.read()` which buffers the entire payload in memory before
we can reject it. Instead we read in chunks and break early as soon as the
declared limit is exceeded.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Set as AbstractSet
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile

from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = ["CHUNK_SIZE", "iter_upload_chunks", "magic", "stream_upload_to_path"]

try:
    import magic
except Exception:  # pragma: no cover - optional fallback when libmagic missing
    magic = None  # type: ignore[assignment]  # optional-import fallback: Module | None

CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def stream_upload_to_path(
    file: UploadFile,
    dest: Path,
    *,
    max_size: int,
    allowed_mimes: AbstractSet[str] | None = None,
) -> tuple[int, str | None]:
    """Stream `file` into `dest` aborting early when `max_size` is exceeded.

    Returns ``(bytes_written, detected_mime)``.
    Raises ``413`` on overflow, ``422`` on disallowed real MIME.
    MIME detection happens before the output file is opened so rejected uploads
    never touch the filesystem.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    first_chunk = await file.read(CHUNK_SIZE)
    head = first_chunk[:2048]

    detected: str | None = None
    if magic is not None and head:
        try:
            detected = magic.from_buffer(head, mime=True)
        except Exception:
            detected = None

    if allowed_mimes is not None:
        effective = detected or file.content_type
        if effective not in allowed_mimes:
            logger.warning(
                "upload.rejected.mime_not_allowed",
                dest=str(dest),
                detected_mime=detected,
                content_type=file.content_type,
                effective=effective,
            )
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {effective or 'unknown'}",
            )

    written = 0
    overflow = False
    async with aiofiles.open(dest, "wb") as out:
        if first_chunk:
            written += len(first_chunk)
            if written > max_size:
                overflow = True
            else:
                await out.write(first_chunk)

        if not overflow:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_size:
                    overflow = True
                    break
                await out.write(chunk)

    if overflow:
        dest.unlink(missing_ok=True)
        logger.warning(
            "upload.rejected.too_large",
            dest=str(dest),
            written=written,
            max_size=max_size,
        )
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {max_size} bytes)",
        )

    return written, detected


async def iter_upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    """Async iterator over an UploadFile in fixed-size chunks."""
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        yield chunk
