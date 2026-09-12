"""Межпроцессный advisory-лок (``fcntl.flock``) для JSON-файлов состояния.

In-memory ``asyncio.Lock`` сериализует корутины внутри одного воркера, но не
защищает от гонки между процессами (несколько воркеров Gunicorn/uvicorn): два
процесса могут одновременно выполнить read-modify-write одного JSON и затереть
правки друг друга (F4 — потеря шар/прав).

``interprocess_lock`` берёт эксклюзивный flock на отдельном lock-файле, тем
самым сериализуя критическую секцию read-modify-write между всеми процессами
на одной машине. Используется внутри ``asyncio.to_thread`` (flock — блокирующий
syscall), поверх per-process ``asyncio.Lock`` как fast-path.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def interprocess_lock(lock_path: Path) -> Iterator[None]:
    """Эксклюзивный flock на ``lock_path`` на время критической секции."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
