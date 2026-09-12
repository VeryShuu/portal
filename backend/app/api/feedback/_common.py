"""Shared constants and schema mappers for the feedback API package."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.schemas.feedback import (
    FeedbackAdminOut,
    FeedbackAttachmentOut,
    FeedbackCategory,
    FeedbackOut,
    FeedbackReplyOut,
    FeedbackStatus,
)

logger = get_logger(__name__)

FEEDBACK_FILES_DIR = Path("/data/feedback/files")
FEEDBACK_ATTACHMENT_MAX_SIZE = 10 * 1024 * 1024
FEEDBACK_ATTACHMENT_MAX_PER_TICKET = 5
FEEDBACK_ATTACHMENT_ALLOWED_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
    "text/plain",
    "application/zip",
    "application/x-zip-compressed",
}


def reply_to_out(reply: FeedbackReply) -> FeedbackReplyOut:
    admin_name = reply.admin.full_name if reply.admin else None
    return FeedbackReplyOut(
        id=reply.id,
        admin_id=reply.admin_id,
        admin_name=admin_name,
        message=reply.message,
        created_at=reply.created_at,
    )


def attachment_to_out(att: FeedbackAttachment) -> FeedbackAttachmentOut:
    return FeedbackAttachmentOut(
        id=att.id,
        original_name=att.original_name,
        size_bytes=att.size_bytes,
        mime_type=att.mime_type,
        created_at=att.created_at,
        download_url=f"/api/v1/feedback/{att.feedback_id}/attachments/{att.id}",
    )


def feedback_to_out(fb: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=fb.id,
        category=FeedbackCategory(fb.category),
        message=fb.message,
        page_url=fb.page_url,
        status=FeedbackStatus(fb.status),
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        replies=[reply_to_out(r) for r in (fb.replies or [])],
        attachments=[attachment_to_out(a) for a in (fb.attachments or [])],
    )


def feedback_to_admin_out(fb: Feedback) -> FeedbackAdminOut:
    author_name = fb.author.full_name if fb.author else None
    author_email = fb.author.email if fb.author else None
    return FeedbackAdminOut(
        id=fb.id,
        category=FeedbackCategory(fb.category),
        message=fb.message,
        page_url=fb.page_url,
        status=FeedbackStatus(fb.status),
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        replies=[reply_to_out(r) for r in (fb.replies or [])],
        attachments=[attachment_to_out(a) for a in (fb.attachments or [])],
        user_id=fb.user_id,
        author_name=author_name,
        author_email=author_email,
    )


__all__ = [
    "FEEDBACK_ATTACHMENT_ALLOWED_MIMES",
    "FEEDBACK_ATTACHMENT_MAX_PER_TICKET",
    "FEEDBACK_ATTACHMENT_MAX_SIZE",
    "FEEDBACK_FILES_DIR",
    "attachment_to_out",
    "feedback_to_admin_out",
    "feedback_to_out",
    "logger",
    "reply_to_out",
]
