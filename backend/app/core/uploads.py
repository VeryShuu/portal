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
from fastapi import HTTPException, UploadFile, status

from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "CHUNK_SIZE",
    "iter_upload_chunks",
    "magic",
    "safe_join_within",
    "save_bytes_to_path",
    "stream_upload_to_path",
]

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


async def save_bytes_to_path(
    data: bytes,
    base_dir: Path,
    rel_segments: tuple[str, ...],
    *,
    max_size: int,
    allowed_mimes: AbstractSet[str] | None = None,
) -> tuple[int, str | None]:
    """Write already-in-memory ``data`` to ``base_dir / *rel_segments`` with guards.

    Mirrors the contract of :func:`stream_upload_to_path` but takes ``bytes``
    (e.g. re-hosted remote image fetched server-side) instead of a streaming
    ``UploadFile``. MIME detection uses libmagic on the head, identical to the
    streaming variant, so rejected payloads never reach the filesystem.

    The destination is built **inside** via :func:`safe_join_within` (the
    project's recognized ``py/path-injection`` guard) from the trusted
    ``base_dir`` and ``rel_segments``. Accepting relative segments rather than
    a pre-built ``dest`` keeps user-derived components (article id, sanitized
    filename) flowing through the recognized sanitizer, so no tainted path
    reaches a FS sink — this is what closes the CodeQL alert.

    Returns ``(bytes_written, detected_mime)``.
    Raises ``413`` on overflow, ``422`` on disallowed real MIME, ``404`` on
    path escape.
    """
    if len(data) > max_size:
        logger.warning(
            "upload.rejected.too_large",
            base=str(base_dir),
            segments=list(rel_segments),
            written=len(data),
            max_size=max_size,
        )
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {max_size} bytes)",
        )

    head = data[:2048]
    detected: str | None = None
    if magic is not None and head:
        try:
            detected = magic.from_buffer(head, mime=True)
        except Exception:
            detected = None

    if allowed_mimes is not None and detected is not None and detected not in allowed_mimes:
        logger.warning(
            "upload.rejected.mime_not_allowed",
            base=str(base_dir),
            segments=list(rel_segments),
            detected_mime=detected,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {detected}",
        )

    # dest построен из доверенного base_dir + сегментов через признанный CodeQL
    # py/path-injection guard — tainted-компоненты (article_id, sanitized name)
    # проходят валидацию здесь, до FS-sinks ниже.
    dest = safe_join_within(base_dir, *rel_segments)
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, "wb") as out:
        await out.write(data)

    return len(data), detected


def safe_join_within(base: Path, *segments: str) -> Path:
    """Join ``segments`` under ``base`` rejecting anything that escapes it.

    Defense-in-depth guard for FS sinks that build a path from DB-sourced
    components (news/KB/feedback attachment filenames). Callers already write
    server-generated UUIDs / sanitized names, so this is not fixing an
    exploitable bug — it closes CodeQL ``py/path-injection`` alerts and
    protects against future regressions if a writer ever stores a raw
    user-supplied name.

    Resolves the final path (following ``..``) and verifies it stays inside
    ``base.resolve()``. Raises ``HTTPException(404)`` on escape: a traversal
    attempt never points at a real stored file, so 404 is the honest answer.

    Mirrors the ``resolve()`` + ``is_relative_to()`` pattern already used in
    ``app/services/photos_storage/paths.py`` and ``app/services/kb_trash.py``.
    """
    resolved_base = base.resolve()
    candidate = (resolved_base.joinpath(*segments)).resolve()
    if not candidate.is_relative_to(resolved_base):
        logger.warning(
            "uploads.path_traversal_blocked",
            base=str(resolved_base),
            segments=list(segments),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return candidate
