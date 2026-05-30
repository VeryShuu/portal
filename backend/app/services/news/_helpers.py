"""Shared helpers, constants, cover-variants and targeting filter for news service."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from sqlalchemy import Select

from app.core.logging import get_logger
from app.models.news import News
from app.models.user import User

logger = get_logger(__name__)

_NEWS_MEDIA_DIR = Path("/data/news_media")

_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

NEWS_COVER_VARIANT_WIDTHS: tuple[int, ...] = (400, 800, 1200, 1600)
_NEWS_COVER_QUALITY = 82


def _build_cover_variants(
    src: Path, out_dir: Path
) -> tuple[list[int], str | None]:
    """Generate WebP+AVIF variants and return (widths_generated, dominant_hex).

    Best-effort: failures are logged and an empty list is returned, the
    original cover file remains usable as a fallback.
    """
    try:
        from PIL import Image, ImageOps  # lazy
    except Exception as e:
        logger.warning("news.cover.pillow_missing", error=str(e))
        return [], None

    widths_done: list[int] = []
    dominant_hex: str | None = None
    try:
        with Image.open(src) as src_img:
            pil = ImageOps.exif_transpose(src_img)
            if pil.mode == "P":
                pil = pil.convert("RGBA" if "transparency" in pil.info else "RGB")
            elif pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGB")
            try:
                tiny = pil.copy()
                tiny.thumbnail((1, 1), Image.Resampling.LANCZOS)
                px = tiny.convert("RGB").getpixel((0, 0))
                if isinstance(px, tuple) and len(px) >= 3:
                    dominant_hex = f"#{int(px[0]):02x}{int(px[1]):02x}{int(px[2]):02x}"
            except Exception as e:
                logger.warning("news.cover.dominant_failed", error=str(e))

            orig_w = pil.width
            for target_w in NEWS_COVER_VARIANT_WIDTHS:
                if target_w > orig_w:
                    continue
                copy = pil.copy()
                copy.thumbnail((target_w, target_w * 4), Image.Resampling.LANCZOS)
                webp_path = out_dir / f"cover-{target_w}.webp"
                try:
                    copy.save(webp_path, "WEBP", quality=_NEWS_COVER_QUALITY, method=6)
                    widths_done.append(target_w)
                except Exception as e:
                    logger.warning(
                        "news.cover.webp_failed", width=target_w, error=str(e)
                    )
                    continue
                with contextlib.suppress(Exception):
                    copy.save(
                        out_dir / f"cover-{target_w}.avif",
                        "AVIF",
                        quality=_NEWS_COVER_QUALITY,
                    )
            if not widths_done:
                copy = pil.copy()
                webp_path = out_dir / f"cover-{orig_w}.webp"
                try:
                    copy.save(webp_path, "WEBP", quality=_NEWS_COVER_QUALITY, method=6)
                    widths_done.append(orig_w)
                except Exception as e:
                    logger.warning(
                        "news.cover.webp_failed", width=orig_w, error=str(e)
                    )
    except Exception as e:
        logger.warning("news.cover.variants_failed", error=str(e))
    return widths_done, dominant_hex


def _remove_cover_variants(news_id_dir: Path) -> None:
    if not news_id_dir.exists():
        return
    for p in news_id_dir.glob("cover-*.webp"):
        p.unlink(missing_ok=True)
    for p in news_id_dir.glob("cover-*.avif"):
        p.unlink(missing_ok=True)


def news_targeting_conditions(user: User) -> list[Any]:
    """Возвращает SQL-условия таргетинга новостей для пользователя.

    Новость доступна, если ОБА условия истинны:
    - target_departments пуст ИЛИ содержит отдел пользователя
    - target_roles пуст ИЛИ содержит роль пользователя

    Вынесено отдельно, чтобы вызывающие, собирающие список условий (например
    глобальный поиск), переиспользовали ровно тот же ACL и не плодили
    собственные (потенциально дырявые) реализации таргетинга.
    """
    from sqlalchemy import String, cast, or_
    from sqlalchemy.dialects.postgresql import ARRAY

    dept_clause = or_(
        News.target_departments.is_(None),
        News.target_departments == [],
    )
    if user.department is not None:
        dept_clause = or_(
            dept_clause,
            News.target_departments.contains(cast([user.department], ARRAY(String))),
        )

    role_clause = or_(
        News.target_roles.is_(None),
        News.target_roles == [],
        News.target_roles.contains(cast([user.role], ARRAY(String))),
    )

    return [dept_clause, role_clause]


def _targeting_filter(stmt: Select[Any], user: User) -> Select[Any]:
    """Фильтр по таргетингу: показывать новость, если ОБА условия:
    - target_departments пуст ИЛИ содержит отдел пользователя
    - target_roles пуст ИЛИ содержит роль пользователя
    """
    for clause in news_targeting_conditions(user):
        stmt = stmt.where(clause)
    return stmt
