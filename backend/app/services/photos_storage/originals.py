"""I/O оригиналов фотогалереи: сохранение и удаление файлов.

Часть пакета :mod:`app.services.photos_storage` (см. его ``__init__``).
"""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from typing import BinaryIO


def save_original(folder_path: str, original_name: str, data: bytes | BinaryIO) -> tuple[str, int]:
    """Сохраняет оригинал, возвращает (filename_on_disk, size_bytes).

    Использует open(path, 'xb') для атомарного эксклюзивного создания файла —
    исключает race condition при одновременной загрузке файлов с одинаковым именем.
    """
    from app.services import photos_storage as _ps

    safe = _ps.sanitize_filename(original_name)
    stem = Path(safe).stem
    ext = Path(safe).suffix.lower() or ".bin"

    target_dir = _ps.folder_fs_path(folder_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    fpath: Path | None = None
    out_f = None
    for i in range(10001):
        if i == 0:
            candidate = safe
        elif i <= 9999:
            candidate = f"{stem}-{i}{ext}"
        else:
            candidate = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"

        try:
            p = target_dir / candidate
            out_f = p.open("xb")
            fpath = p
            break
        except FileExistsError:
            continue

    if fpath is None or out_f is None:
        raise OSError(f"Cannot create unique file for '{original_name}' in {target_dir}")

    size = 0
    with out_f:
        if isinstance(data, bytes):
            out_f.write(data)
            size = len(data)
        else:
            while True:
                chunk = data.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                size += len(chunk)
    return fpath.name, size


def delete_photo_files(original_path: Path | None, photo_id: uuid.UUID) -> None:
    from app.services import photos_storage as _ps

    try:
        if original_path and original_path.exists():
            original_path.unlink()
    except OSError:
        pass
    try:
        d = _ps.THUMBS_ROOT / str(photo_id)
        if d.exists():
            for f in d.iterdir():
                with contextlib.suppress(OSError):
                    f.unlink()
            d.rmdir()
    except OSError:
        pass
