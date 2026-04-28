"""
Физический перенос каталогов после миграции 016_photo_folders_fs_path.

Запуск:
  python -m scripts.migrate_016_fs
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import asyncpg

ORIGINALS_ROOT = Path("/data/photos/originals")


def _to_path(value: str) -> Path | None:
    parts = [p for p in (value or "").split("/") if p]
    if not parts:
        return None
    return ORIGINALS_ROOT.joinpath(*parts)


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)

    moved = 0
    merged = 0
    skipped = 0

    try:
        rows = await conn.fetch(
            """
            SELECT id, path, fs_path
            FROM photo_folders
            WHERE fs_path IS NOT NULL AND fs_path <> ''
            """
        )

        for row in rows:
            legacy = _to_path(row["path"] or "")
            target = _to_path(row["fs_path"] or "")
            if legacy is None or target is None:
                skipped += 1
                continue
            if legacy == target:
                skipped += 1
                continue
            if not legacy.exists() or not legacy.is_dir():
                skipped += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.is_dir():
                for child in legacy.iterdir():
                    dest = target / child.name
                    if not dest.exists():
                        shutil.move(str(child), str(dest))
                try:
                    legacy.rmdir()
                except OSError:
                    pass
                merged += 1
            else:
                shutil.move(str(legacy), str(target))
                moved += 1

        print(f"Moved folders: {moved}")
        print(f"Merged folders: {merged}")
        print(f"Skipped folders: {skipped}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
