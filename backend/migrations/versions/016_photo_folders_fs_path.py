"""photo_folders.fs_path — зеркало структуры папок на диске с реальными именами

Revision ID: 016
Revises: 015
Create Date: 2026-04-25
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_folder_name(name: str) -> str:
    norm = unicodedata.normalize("NFC", name or "").strip()
    cleaned = _INVALID_FS.sub("-", norm).strip(". ")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "folder"
    if len(cleaned) > 200:
        h = hashlib.sha256((name or "").encode("utf-8", "ignore")).hexdigest()[:8]
        cleaned = cleaned[:180] + "-" + h
    return cleaned


def upgrade() -> None:
    op.add_column(
        "photo_folders",
        sa.Column("fs_path", sa.String(2000), nullable=False, server_default=""),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, parent_id, name FROM photo_folders ORDER BY parent_id NULLS FIRST")
    ).fetchall()

    fs_by_id: dict = {}
    parents: dict = {}
    names: dict = {}
    children_of: dict = {}
    for r in rows:
        parents[r.id] = r.parent_id
        names[r.id] = r.name or ""
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
            _build(parent_id)
            siblings = [
                cid for cid in children_of.get(parent_id, []) if cid != node_id and cid in fs_by_id
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


def downgrade() -> None:
    op.drop_column("photo_folders", "fs_path")
