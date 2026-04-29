"""Streaming upload helpers with hard size cap and real MIME detection.

Avoids `await file.read()` which buffers the entire payload in memory before
we can reject it. Instead we read in chunks and break early as soon as the
declared limit is exceeded.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

try:
    import magic  # type: ignore
except Exception:  # pragma: no cover - optional fallback when libmagic missing
    magic = None  # type: ignore

CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def stream_upload_to_path(
    file: UploadFile,
    dest: Path,
    *,
    max_size: int,
    allowed_mimes: set[str] | None = None,
) -> tuple[int, str | None]:
    """Stream `file` into `dest` aborting early when `max_size` is exceeded.

    Returns ``(bytes_written, detected_mime)``.
    Raises ``413`` on overflow, ``422`` on disallowed real MIME.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    head = b""
    detected: str | None = None

    async with aiofiles.open(dest, "wb") as out:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > max_size:
                await out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large (max {max_size} bytes)",
                )
            if len(head) < 2048:
                head += chunk[: 2048 - len(head)]
            await out.write(chunk)

    if magic is not None and head:
        try:
            detected = magic.from_buffer(head, mime=True)
        except Exception:
            detected = None

    if allowed_mimes is not None:
        effective = detected or file.content_type
        if effective not in allowed_mimes:
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type: {effective or 'unknown'}",
            )

    return written, detected


async def iter_upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    """Async iterator over an UploadFile in fixed-size chunks."""
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        yield chunk
