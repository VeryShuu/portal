"""Persistent ACL storage for file folders — survives PostgreSQL wipes.

Stored at /data/settings/files-acl.json.
Written atomically (tempfile + os.replace), chmod 0600.

Format::

    {
      "HR": [
        {"subject_type": "user", "subject_id": "...", "subject_name": "Petrov",
         "permission": "editor"}
      ],
      "HR/Docs": [...]
    }

Keys are nc_path values (relative to files_root, e.g. "HR/Docs").
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

from app.core.logging import get_logger
from app.services._persistence_lock import interprocess_lock

logger = get_logger(__name__)

_ACL_FILE = Path("/data/settings/files-acl.json")
_SETTINGS_DIR = _ACL_FILE.parent

_write_lock: asyncio.Lock | None = None


def _get_write_lock() -> asyncio.Lock:
    global _write_lock
    if _write_lock is None:
        _write_lock = asyncio.Lock()
    return _write_lock


def _mutate(mutator: Callable[[AclBackup], None]) -> None:
    """Read-modify-write под межпроцессным flock (F4).

    Весь цикл чтение→правка→запись держит эксклюзивный flock, поэтому
    параллельные воркеры не затирают правки друг друга.
    """
    with interprocess_lock(_ACL_FILE.with_suffix(".lock")):
        data = _read_raw()
        mutator(data)
        _write_raw(data)


class AclEntry(TypedDict):
    subject_type: str
    subject_id: str
    subject_name: str
    permission: str


AclBackup = dict[str, list[AclEntry]]


def _read_raw() -> AclBackup:
    if not _ACL_FILE.exists():
        return {}
    try:
        return cast(AclBackup, json.loads(_ACL_FILE.read_text("utf-8")))
    except Exception:
        logger.warning("files_acl_persistence.parse_failed", path=str(_ACL_FILE))
        return {}


def _write_raw(data: AclBackup) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_SETTINGS_DIR, prefix=".files-acl-", suffix=".json")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _ACL_FILE)
        with contextlib.suppress(OSError):
            os.chmod(_ACL_FILE, 0o600)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


async def save_folder_perms(nc_path: str, entries: list[AclEntry]) -> None:
    """Persist permissions for a single folder. Thread- and process-safe."""

    def _apply(data: AclBackup) -> None:
        if entries:
            data[nc_path] = entries
        else:
            data.pop(nc_path, None)

    async with _get_write_lock():
        await asyncio.to_thread(_mutate, _apply)


async def drop_folder_perms(nc_path: str) -> None:
    """Remove ACL entry for a folder (called on portal-side deletion)."""

    def _apply(data: AclBackup) -> None:
        data.pop(nc_path, None)

    async with _get_write_lock():
        await asyncio.to_thread(_mutate, _apply)


def get_folder_perms(nc_path: str) -> list[AclEntry]:
    """Return persisted ACL entries for nc_path. Synchronous — safe to call from any context."""
    data = _read_raw()
    return data.get(nc_path, [])


def load_all() -> AclBackup:
    """Return full ACL dict. Synchronous."""
    return _read_raw()
