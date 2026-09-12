from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

_SETTINGS_DIR = Path("/data/settings")
_SYSTEM_SETTINGS_FILE = _SETTINGS_DIR / "system.json"

_SECRET_MASK = "***"
_settings_cache: dict[str, Any] = {}
_settings_cache_lock = asyncio.Lock()
_CACHE_TTL = 60
_CACHE_VERSION_KEY = "system_settings"

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def atomic_write(path: Path, content: str | bytes, *, mode: int | None = None) -> None:
    """Write *content* to *path* atomically using a temp file + os.replace().

    Prevents a partial-read race where nginx (or another process) reads the
    file while it is still being written. When *mode* is given (e.g. ``0o600``),
    it is applied to the temp file **before** the rename, so the final file
    never appears with looser permissions (no 0644 window).

    Note (audit [H4]): no ``fsync`` — for runtime settings, durability-after-crash
    is not critical and the fsync cost on every admin-save is unjustified. The
    atomic rename guarantees readers never see a half-written file.
    """
    import os as _os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(content, bytes):
        tmp.write_bytes(content)
    else:
        tmp.write_text(content, encoding="utf-8")
    if mode is not None:
        with contextlib.suppress(OSError):
            _os.chmod(tmp, mode)
    _os.replace(tmp, path)


_atomic_write = atomic_write


def _save_system_settings(s: Any) -> None:
    import os as _os

    from app.core import system_config as _root

    _root._SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _root.atomic_write(_root._SYSTEM_SETTINGS_FILE, s.model_dump_json(indent=2))
    with contextlib.suppress(OSError):
        _os.chmod(_root._SYSTEM_SETTINGS_FILE, 0o600)
    _root._settings_cache.clear()


def invalidate_settings_cache() -> None:
    from app.core import system_config as _root

    _root._settings_cache.clear()
