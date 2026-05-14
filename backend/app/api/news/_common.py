"""Shared helpers and constants for the news API package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, status

from app.api.deps import RedisDep
from app.core.logging import get_logger
from app.models.news import News as NewsModel
from app.models.user import User
from app.services.audit import push_audit_event

logger = get_logger(__name__)

NEWS_MEDIA_DIR = Path("/data/news_media")
ALLOWED_INLINE_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def require_news_read_access(news: NewsModel, user: User) -> None:
    """Allow reads to anyone for published news; gate drafts/archived to editors+."""
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def emit_news_audit(
    redis: RedisDep,
    *,
    event_type: str,
    actor: User,
    request: Request,
    resource_type: str = "news",
    resource_id: str,
    resource_title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Centralised audit event emission for news routes (DRY)."""
    await push_audit_event(
        redis,
        event_type=event_type,
        user_id=str(actor.id),
        user_email=actor.email,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_title=resource_title,
        ip_address=request.client.host if request.client else None,
        metadata=metadata,
    )
