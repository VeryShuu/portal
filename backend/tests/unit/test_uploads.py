"""Unit-тесты для core/uploads.py.

Покрытие:
- stream_upload_to_path: happy path, size overflow → 413, MIME whitelist → 422
- stream_upload_to_path: magic=None → fallback to content_type
- stream_upload_to_path: allowed_mimes=None → skip MIME check
- iter_upload_chunks: yields all chunks, stops on empty read
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_upload_file(chunks: list[bytes], content_type: str = "image/jpeg") -> MagicMock:
    """Имитирует fastapi.UploadFile с заданными чанками."""
    uf = MagicMock()
    uf.content_type = content_type
    _chunks = [*list(chunks), b""]
    _idx = [0]

    async def _read(size: int = -1) -> bytes:
        if _idx[0] >= len(_chunks):
            return b""
        chunk = _chunks[_idx[0]]
        _idx[0] += 1
        return chunk

    uf.read = _read
    return uf


# ── stream_upload_to_path ─────────────────────────────────────────────────────


class TestStreamUploadToPath:
    async def test_happy_path_writes_file(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        data = b"hello world"
        dest = tmp_path / "out.txt"
        uf = _make_upload_file([data])

        with patch("app.core.uploads.magic", None):
            written, detected = await stream_upload_to_path(uf, dest, max_size=1024)

        assert written == len(data)
        assert detected is None
        assert dest.read_bytes() == data

    async def test_creates_parent_dirs(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "a" / "b" / "file.bin"
        uf = _make_upload_file([b"data"])

        with patch("app.core.uploads.magic", None):
            await stream_upload_to_path(uf, dest, max_size=1024)

        assert dest.exists()

    async def test_overflow_raises_413(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "big.bin"
        uf = _make_upload_file([b"x" * 100])

        with patch("app.core.uploads.magic", None):
            with pytest.raises(HTTPException) as exc_info:
                await stream_upload_to_path(uf, dest, max_size=50)

        assert exc_info.value.status_code == 413
        assert not dest.exists()

    async def test_overflow_deletes_partial_file(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "partial.bin"
        uf = _make_upload_file([b"x" * 200])

        with patch("app.core.uploads.magic", None), pytest.raises(HTTPException):
            await stream_upload_to_path(uf, dest, max_size=100)

        assert not dest.exists()

    async def test_allowed_mimes_none_skips_check(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "file.xyz"
        uf = _make_upload_file([b"data"], content_type="application/unknown")

        with patch("app.core.uploads.magic", None):
            written, _ = await stream_upload_to_path(uf, dest, max_size=1024, allowed_mimes=None)

        assert written == 4

    async def test_disallowed_mime_raises_422(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "evil.exe"
        uf = _make_upload_file([b"MZ\x90\x00"], content_type="application/x-msdownload")

        with patch("app.core.uploads.magic", None):
            with pytest.raises(HTTPException) as exc_info:
                await stream_upload_to_path(
                    uf, dest, max_size=1024, allowed_mimes={"image/jpeg", "image/png"}
                )

        assert exc_info.value.status_code == 422
        assert not dest.exists()

    async def test_disallowed_mime_deletes_file(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "bad.bin"
        uf = _make_upload_file([b"data"], content_type="application/octet-stream")

        with patch("app.core.uploads.magic", None), pytest.raises(HTTPException):
            await stream_upload_to_path(uf, dest, max_size=1024, allowed_mimes={"image/jpeg"})

        assert not dest.exists()

    async def test_magic_detected_mime_used_for_check(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "img.jpg"
        uf = _make_upload_file([b"\xff\xd8\xff\xe0" + b"\x00" * 10], content_type="image/jpeg")

        mock_magic = MagicMock()
        mock_magic.from_buffer = MagicMock(return_value="image/jpeg")

        with patch("app.core.uploads.magic", mock_magic):
            written, detected = await stream_upload_to_path(
                uf, dest, max_size=1024, allowed_mimes={"image/jpeg"}
            )

        assert detected == "image/jpeg"
        assert dest.exists()

    async def test_magic_detected_wrong_mime_raises_422(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "fake.jpg"
        uf = _make_upload_file([b"MZ\x90\x00"], content_type="image/jpeg")

        mock_magic = MagicMock()
        mock_magic.from_buffer = MagicMock(return_value="application/x-msdownload")

        with patch("app.core.uploads.magic", mock_magic):
            with pytest.raises(HTTPException) as exc_info:
                await stream_upload_to_path(
                    uf, dest, max_size=1024, allowed_mimes={"image/jpeg", "image/png"}
                )

        assert exc_info.value.status_code == 422

    async def test_magic_exception_falls_back_to_content_type(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        dest = tmp_path / "file.jpg"
        uf = _make_upload_file([b"data"], content_type="image/jpeg")

        mock_magic = MagicMock()
        mock_magic.from_buffer = MagicMock(side_effect=Exception("libmagic error"))

        with patch("app.core.uploads.magic", mock_magic):
            written, detected = await stream_upload_to_path(
                uf, dest, max_size=1024, allowed_mimes={"image/jpeg"}
            )

        assert detected is None
        assert dest.exists()

    async def test_multipart_upload_accumulates_bytes(self, tmp_path: Path):
        from app.core.uploads import stream_upload_to_path

        chunks = [b"aa", b"bb", b"cc"]
        dest = tmp_path / "multi.bin"
        uf = _make_upload_file(chunks)

        with patch("app.core.uploads.magic", None):
            written, _ = await stream_upload_to_path(uf, dest, max_size=1024)

        assert written == 6
        assert dest.read_bytes() == b"aabbcc"


# ── iter_upload_chunks ────────────────────────────────────────────────────────


class TestIterUploadChunks:
    async def test_yields_all_chunks(self):
        from app.core.uploads import iter_upload_chunks

        uf = _make_upload_file([b"chunk1", b"chunk2", b"chunk3"])
        result = []
        async for chunk in iter_upload_chunks(uf):
            result.append(chunk)

        assert result == [b"chunk1", b"chunk2", b"chunk3"]

    async def test_empty_file_yields_nothing(self):
        from app.core.uploads import iter_upload_chunks

        uf = _make_upload_file([])
        result = []
        async for chunk in iter_upload_chunks(uf):
            result.append(chunk)

        assert result == []

    async def test_single_chunk(self):
        from app.core.uploads import iter_upload_chunks

        uf = _make_upload_file([b"only"])
        result = [chunk async for chunk in iter_upload_chunks(uf)]
        assert result == [b"only"]
