"""News categories: управление списком категорий новостей с цветовой маркировкой.

Категории хранятся в JSON-файле /data/settings/news_categories.json как список
объектов {name, color}. При удалении категории из реестра она удаляется и из всех
новостей через SQL array_remove(). Старый формат (плоский список строк) читается
для обратной совместимости.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, update
from sqlalchemy import select as sa_select

from app.api.deps import CurrentUser, DbDep, EditorDep
from app.core.logging import get_logger
from app.models.news import News

logger = get_logger(__name__)

router = APIRouter(prefix="/news-categories", tags=["news-categories"])

_SETTINGS_DIR = Path("/data/settings")
_CATEGORIES_FILE = _SETTINGS_DIR / "news_categories.json"

_MAX_NAME_LEN = 100
_MAX_CATEGORIES = 100
_DEFAULT_COLOR = "#6B7AE8"


class NewsCategory(BaseModel):
    name: str
    color: str


class NewsCategoryWithCount(BaseModel):
    name: str
    color: str
    news_count: int


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_LEN)
    color: str = Field(default=_DEFAULT_COLOR, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name cannot be empty or whitespace only")
        return stripped


class ColorIn(BaseModel):
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_LEN)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name cannot be empty or whitespace only")
        return stripped


class CategoriesResponse(BaseModel):
    items: list[NewsCategoryWithCount]


def _load() -> list[NewsCategory]:
    if not _CATEGORIES_FILE.exists():
        return []
    try:
        data = json.loads(_CATEGORIES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("news_categories.load_failed", error=str(exc))
        return []
    if not isinstance(data, list):
        return []
    out: list[NewsCategory] = []
    seen: set[str] = set()
    for item in data:
        if isinstance(item, str):
            name = item.strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(NewsCategory(name=name, color=_DEFAULT_COLOR))
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            color = str(item.get("color", _DEFAULT_COLOR))
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(NewsCategory(name=name, color=color))
    return out


def _save(items: list[NewsCategory]) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="news_categories.",
        suffix=".json",
        dir=str(_SETTINGS_DIR),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                [{"name": c.name, "color": c.color} for c in items],
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp_path, _CATEGORIES_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def ensure_category_exists(name: str) -> None:
    """Add *name* to the categories list if it is not already present."""
    stripped = name.strip()
    if not stripped:
        return
    items = _load()
    if any(c.name.lower() == stripped.lower() for c in items):
        return
    if len(items) >= _MAX_CATEGORIES:
        return
    items.append(NewsCategory(name=stripped, color=_DEFAULT_COLOR))
    try:
        _save(items)
    except Exception as exc:
        logger.warning("news_categories.auto_add_failed", error=str(exc))


@router.get("", response_model=CategoriesResponse, summary="Список категорий новостей")
async def list_categories(_: CurrentUser, db: DbDep) -> CategoriesResponse:
    items = _load()
    if not items:
        return CategoriesResponse(items=[])

    result = await db.execute(
        sa_select(
            func.unnest(News.categories).label("cat"),
            func.count().label("cnt"),
        )
        .where(News.deleted_at.is_(None))
        .group_by("cat")
    )
    counts: dict[str, int] = {}
    for row in result:
        key = row.cat.lower()
        counts[key] = counts.get(key, 0) + row.cnt

    return CategoriesResponse(
        items=[
            NewsCategoryWithCount(
                name=c.name,
                color=c.color,
                news_count=counts.get(c.name.lower(), 0),
            )
            for c in items
        ]
    )


@router.post(
    "",
    response_model=CategoriesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить категорию новостей",
)
async def add_category(body: CategoryIn, _: EditorDep) -> CategoriesResponse:
    name = body.name

    items = _load()
    if any(c.name.lower() == name.lower() for c in items):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")
    if len(items) >= _MAX_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many categories",
        )

    items.append(NewsCategory(name=name, color=body.color))
    _save(items)
    return CategoriesResponse(
        items=[NewsCategoryWithCount(name=c.name, color=c.color, news_count=0) for c in items]
    )


@router.patch(
    "/{name}/color",
    response_model=CategoriesResponse,
    summary="Обновить цвет категории",
)
async def update_category_color(name: str, body: ColorIn, _: EditorDep) -> CategoriesResponse:
    items = _load()
    target = name.strip().lower()
    found = False
    for cat in items:
        if cat.name.lower() == target:
            cat.color = body.color
            found = True
            break
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    _save(items)
    return CategoriesResponse(
        items=[NewsCategoryWithCount(name=c.name, color=c.color, news_count=0) for c in items]
    )


@router.patch(
    "/{name}",
    response_model=CategoriesResponse,
    summary="Переименовать категорию (обновляет имя и во всех новостях)",
)
async def rename_category(name: str, body: RenameIn, _: EditorDep, db: DbDep) -> CategoriesResponse:
    items = _load()
    target = name.strip().lower()
    actual_name = next((c.name for c in items if c.name.lower() == target), None)
    if actual_name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    new_name = body.name
    new_lower = new_name.lower()
    if new_lower != target and any(c.name.lower() == new_lower for c in items):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")

    for cat in items:
        if cat.name.lower() == target:
            cat.name = new_name
            break
    _save(items)

    if new_name != actual_name:
        await db.execute(
            update(News)
            .where(News.deleted_at.is_(None))
            .where(func.array_position(News.categories, actual_name).is_not(None))
            .values(categories=func.array_replace(News.categories, actual_name, new_name))
        )
        await db.commit()

    logger.info("news_categories.renamed", old=actual_name, new=new_name)

    return CategoriesResponse(
        items=[NewsCategoryWithCount(name=c.name, color=c.color, news_count=0) for c in items]
    )


@router.delete(
    "/{name}",
    response_model=CategoriesResponse,
    summary="Удалить категорию из списка и из всех новостей",
)
async def delete_category(name: str, _: EditorDep, db: DbDep) -> CategoriesResponse:
    items = _load()
    target = name.strip().lower()
    actual_name = next((c.name for c in items if c.name.lower() == target), None)
    if actual_name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    new_items = [c for c in items if c.name.lower() != target]
    _save(new_items)

    await db.execute(
        update(News)
        .where(News.deleted_at.is_(None))
        .where(func.array_position(News.categories, actual_name).is_not(None))
        .values(categories=func.array_remove(News.categories, actual_name))
    )
    await db.commit()

    logger.info("news_categories.deleted", name=actual_name)

    return CategoriesResponse(
        items=[NewsCategoryWithCount(name=c.name, color=c.color, news_count=0) for c in new_items]
    )
