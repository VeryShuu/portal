"""News categories: лёгкое управление списком категорий новостей.

Категории хранятся в JSON-файле /data/settings/news_categories.json как
плоский список строк. Поле news.category — свободная строка, поэтому
удаление категории из списка не затрагивает уже существующие новости.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, EditorDep
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/news-categories", tags=["news-categories"])

_SETTINGS_DIR = Path("/data/settings")
_CATEGORIES_FILE = _SETTINGS_DIR / "news_categories.json"

_MAX_NAME_LEN = 100
_MAX_CATEGORIES = 100


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_LEN)


class CategoriesResponse(BaseModel):
    items: list[str]


def _load() -> list[str]:
    if not _CATEGORIES_FILE.exists():
        return []
    try:
        data = json.loads(_CATEGORIES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("news_categories.load_failed", error=str(exc))
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def _save(items: list[str]) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="news_categories.",
        suffix=".json",
        dir=str(_SETTINGS_DIR),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _CATEGORIES_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


@router.get("", response_model=CategoriesResponse, summary="Список категорий новостей")
async def list_categories(_: CurrentUser) -> CategoriesResponse:
    return CategoriesResponse(items=_load())


@router.post(
    "",
    response_model=CategoriesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить категорию новостей",
)
async def add_category(body: CategoryIn, _: EditorDep) -> CategoriesResponse:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty name")

    items = _load()
    if any(c.lower() == name.lower() for c in items):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")
    if len(items) >= _MAX_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Too many categories",
        )

    items.append(name)
    _save(items)
    return CategoriesResponse(items=items)


@router.delete(
    "/{name}",
    response_model=CategoriesResponse,
    summary="Удалить категорию из списка",
)
async def delete_category(name: str, _: EditorDep) -> CategoriesResponse:
    items = _load()
    target = name.strip().lower()
    new_items = [c for c in items if c.lower() != target]
    if len(new_items) == len(items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    _save(new_items)
    return CategoriesResponse(items=new_items)
