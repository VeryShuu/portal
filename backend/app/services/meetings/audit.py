from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)

ROOM_CREATED = "ROOM_CREATED"
ROOM_UPDATED = "ROOM_UPDATED"
ROOM_DELETED = "ROOM_DELETED"
MEETING_CREATED = "MEETING_CREATED"
MEETING_UPDATED = "MEETING_UPDATED"
MEETING_DELETED = "MEETING_DELETED"
MEETING_PARTICIPANT_ADDED = "MEETING_PARTICIPANT_ADDED"
MEETING_PARTICIPANT_REMOVED = "MEETING_PARTICIPANT_REMOVED"
MEETING_SERIES_CREATED = "MEETING_SERIES_CREATED"
SERIES_UPDATED = "SERIES_UPDATED"
SERIES_DELETED = "SERIES_DELETED"
EMAIL_SENT = "EMAIL_SENT"
EMAIL_FAILED = "EMAIL_FAILED"


async def push_meetings_audit(
    *,
    action: str,
    user: User | None,
    request: Request | None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    resource_title: str | None = None,
    details: dict | None = None,
) -> None:
    ip_address: str | None = None
    user_agent: str | None = None
    if request is not None:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        else:
            ip_address = getattr(request.client, "host", None)
        user_agent = request.headers.get("User-Agent")

    metadata: dict = {}
    if user is not None:
        if user.role:
            metadata["user_role"] = user.role
        if user.full_name:
            metadata["username"] = user.full_name
    if details:
        metadata.update(details)

    try:
        async with AsyncSessionLocal() as audit_db:
            await audit_db.execute(
                text(
                    "INSERT INTO audit_log "
                    "(event_type, user_id, user_email, resource_type, resource_id, "
                    "resource_title, ip_address, user_agent, metadata, created_at) "
                    "VALUES (:event_type, :user_id, :user_email, :resource_type, :resource_id, "
                    ":resource_title, CAST(:ip_address AS inet), :user_agent, "
                    "CAST(:metadata AS jsonb), :created_at)"
                ),
                {
                    "event_type": action,
                    "user_id": user.id if user else None,
                    "user_email": user.email if user else None,
                    "resource_type": resource_type,
                    "resource_id": str(resource_id) if resource_id else None,
                    "resource_title": resource_title,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "metadata": json.dumps(metadata),
                    "created_at": datetime.now(UTC),
                },
            )
            await audit_db.commit()
    except Exception as exc:
        logger.warning(
            "meetings.audit.log_failed",
            error=str(exc),
            action=action,
        )

    logger.info(
        "meetings.audit",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
    )
