"""photo_folders.fs_path — зеркало структуры папок на диске с реальными именами

Revision ID: 016
Revises: 015
Create Date: 2026-04-25
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ORIGINALS_ROOT = Path("/data/photos/originals")


def _sanitize_folder_name(name: str) -> str:
    norm = unicodedata.normalize("NFC", name or "").strip()
    cleaned = _INVALID_FS.sub("-", norm).strip(". ")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "folder"
    if len(cleaned) > 200:
        cleaned = cleaned[:200]
    return cleaned


def _legacy_slug_path_to_fs(legacy_path: str) -> Path | None:
    parts = [p for p in (legacy_path or "").split("/") if p]
    if not parts:
        return None
    return _ORIGINALS_ROOT.joinpath(*parts)


def upgrade() -> None:
    op.add_column(
        "photo_folders",
        sa.Column("fs_path", sa.String(2000), nullable=False, server_default=""),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, parent_id, name, path FROM photo_folders ORDER BY parent_id NULLS FIRST"
        )
    ).fetchall()

    fs_by_id: dict = {}
    parents: dict = {}
    names: dict = {}
    legacy_paths: dict = {}
    children_of: dict = {}
    for r in rows:
        parents[r.id] = r.parent_id
        names[r.id] = r.name or ""
        legacy_paths[r.id] = r.path or ""
        children_of.setdefault(r.parent_id, []).append(r.id)

    def _build(node_id) -> str:
        if node_id in fs_by_id:
            return fs_by_id[node_id]
        seg = _sanitize_folder_name(names[node_id])
        parent_id = parents[node_id]
        if parent_id is None:
            siblings = [
                cid for cid in children_of.get(None, []) if cid != node_id and cid in fs_by_id
            ]
        else:
            parent_fs = _build(parent_id)
            siblings = [
                cid
                for cid in children_of.get(parent_id, [])
                if cid != node_id and cid in fs_by_id
            ]
        used = {fs_by_id[cid].split("/")[-1] for cid in siblings}
        candidate = seg
        i = 2
        while candidate in used:
            candidate = f"{seg} ({i})"
            i += 1
        if parent_id is None:
            full = candidate
        else:
            full = f"{fs_by_id[parent_id]}/{candidate}"
        fs_by_id[node_id] = full
        return full

    def _walk(parent_id):
        for cid in children_of.get(parent_id, []):
            _build(cid)
            _walk(cid)

    _walk(None)

    for fid, fs_path in fs_by_id.items():
        bind.execute(
            sa.text("UPDATE photo_folders SET fs_path = :fs WHERE id = :id"),
            {"fs": fs_path, "id": fid},
        )

    for fid, fs_path in fs_by_id.items():
        legacy = _legacy_slug_path_to_fs(legacy_paths.get(fid) or "")
        if legacy is None:
            continue
        new_path = _ORIGINALS_ROOT.joinpath(*fs_path.split("/"))
        try:
            if legacy.exists() and legacy.is_dir() and legacy.resolve() != new_path.resolve():
                new_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    for child in legacy.iterdir():
                        target = new_path / child.name
                        if not target.exists():
                            shutil.move(str(child), str(target))
                    try:
                        legacy.rmdir()
                    except OSError:
                        pass
                else:
                    shutil.move(str(legacy), str(new_path))
        except Exception:
            pass


def downgrade() -> None:
    op.drop_column("photo_folders", "fs_path")
