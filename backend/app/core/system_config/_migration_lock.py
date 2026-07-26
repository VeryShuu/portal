"""File-based lock for the one-shot legacy → JSON migration.

Multiple processes (backend, worker, alembic) may start simultaneously on
`docker compose up`. Without coordination, three processes could race on
read-modify-write of /data/settings/system.json. This lock serializes the
migration so it runs exactly once, atomically.

The lock is process-wide (`fcntl.flock` is kernel-level). It is *not* reentrant
across separate processes — that's the point: whoever acquires it first performs
the migration; the others see the file already present on their re-check and bail
out without writing.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def migration_lock(settings_dir: Path, *, timeout_s: float = 30.0) -> Iterator[bool]:
    """Acquire an exclusive `flock` on `<settings_dir>/.migration.lock`.

    Yields ``True`` once the lock is held (always — we block until acquired).
    Creates the lock file if missing. The file itself is empty — only the
    kernel-level flock matters.

    Acquisition strategy:
    1. Try non-blocking first. If we get it immediately, great.
    2. Otherwise poll every 200 ms until ``timeout_s`` elapses (avoids a hard
       signal-alarm and bounds startup contention).
    3. As a last resort, fall back to a blocking `flock`. We never raise —
       a hung peer is a deployment problem, and blocking matches the original
       semantics where the migration ran unconditionally at import time.

    The lock is released on context exit (or any exception) via ``flock(UN)``.
    """
    settings_dir.mkdir(parents=True, exist_ok=True)
    lock_path = settings_dir / ".migration.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            # Fast path: acquire without blocking.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (BlockingIOError, OSError):
            logger.debug(
                "config.migration_lock_busy_waiting",
                timeout_s=timeout_s,
                lock_path=str(lock_path),
            )
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                time.sleep(0.2)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError):
                    continue
            if not acquired:
                # Final blocking attempt — give up waiting, just block.
                logger.warning("config.migration_lock_timeout_blocking", timeout_s=timeout_s)
                fcntl.flock(fd, fcntl.LOCK_EX)
                acquired = True
        yield acquired
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
