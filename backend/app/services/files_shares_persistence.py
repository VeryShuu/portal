"""Persistent per-file share storage — survives PostgreSQL wipes.

Stored at /data/settings/files-shares.json.
Written atomically (tempfile + os.replace), chmod 0600.

Format::

    {
      "HR/Docs/report.xlsx": [
        {"subject_type": "user", "subject_id": "...", "subject_name": "Petrov",
         "permission": "editor", "expires_at": null}
      ]
    }

Keys are nc_path values of the file (folder.nc_path + '/' + filename).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import TypedDict, cast

from app.core.logging import get_logger

logger = get_logger(__name__)

_SHARES_FILE = Path("/data/settings/files-shares.json")
_SETTINGS_DIR = _SHARES_FILE.parent

_write_lock: asyncio.Lock | None = None


def _get_write_lock() -> asyncio.Lock:
    global _write_lock
    if _write_lock is None:
        _write_lock = asyncio.Lock()
    return _write_lock


class ShareEntry(TypedDict):
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str
    expires_at: str | None


SharesBackup = dict[str, list[ShareEntry]]


def _read_raw() -> SharesBackup:
    if not _SHARES_FILE.exists():
        return {}
    try:
        return cast(SharesBackup, json.loads(_SHARES_FILE.read_text("utf-8")))
    except Exception:
        logger.warning("files_shares_persistence.parse_failed", path=str(_SHARES_FILE))
        return {}


def _write_raw(data: SharesBackup) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_SETTINGS_DIR, prefix=".files-shares-", suffix=".json")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _SHARES_FILE)
        with contextlib.suppress(OSError):
            os.chmod(_SHARES_FILE, 0o600)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


async def save_file_shares(nc_path: str, entries: list[ShareEntry]) -> None:
    """Persist active shares for a single file. Thread-safe."""
    async with _get_write_lock():
        data = await asyncio.to_thread(_read_raw)
        if entries:
            data[nc_path] = entries
        else:
            data.pop(nc_path, None)
        await asyncio.to_thread(_write_raw, data)


async def drop_file_shares(nc_path: str) -> None:
    """Remove the persisted entry for a file (called on portal-side deletion)."""
    async with _get_write_lock():
        data = await asyncio.to_thread(_read_raw)
        if nc_path in data:
            data.pop(nc_path)
            await asyncio.to_thread(_write_raw, data)


async def rename_file_shares(old_nc_path: str, new_nc_path: str) -> None:
    """Move the persisted entry from old_nc_path to new_nc_path (move/rename)."""
    async with _get_write_lock():
        data = await asyncio.to_thread(_read_raw)
        if old_nc_path in data:
            data[new_nc_path] = data.pop(old_nc_path)
            await asyncio.to_thread(_write_raw, data)


async def drop_file_shares_under_prefix(folder_nc_path: str) -> None:
    """Remove all file-share entries whose file lives under folder_nc_path.

    Called when a folder is deleted portal-side (DB rows cascade separately).
    """
    prefix = folder_nc_path.rstrip("/") + "/"
    async with _get_write_lock():
        data = await asyncio.to_thread(_read_raw)
        to_drop = [k for k in data if k.startswith(prefix)]
        if to_drop:
            for k in to_drop:
                data.pop(k, None)
            await asyncio.to_thread(_write_raw, data)


def load_all() -> SharesBackup:
    """Return full shares dict. Synchronous."""
    return _read_raw()
