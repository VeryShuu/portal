"""Shared helpers, constants and predicates for the news poll service."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.models.news import NewsPoll
from app.models.user import User

PRIVILEGED_ROLES = ("editor", "admin")

POLL_ALWAYS_EDITABLE = ("closes_at",)
POLL_FROZEN_AFTER_VOTE = ("is_anonymous", "allow_revote", "results_visibility")

QUESTION_ALWAYS_EDITABLE = ("text", "sort_order")
QUESTION_FROZEN_AFTER_VOTE = (
    "is_required",
    "is_multiple",
    "max_choices",
    "allow_custom_answer",
)


def _is_privileged(user: User | None) -> bool:
    return user is not None and user.role in PRIVILEGED_ROLES


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _forbid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def is_poll_closed(poll: NewsPoll, now: datetime) -> bool:
    if poll.closed_at is not None:
        return True
    return poll.closes_at is not None and _aware(poll.closes_at) <= now


def _can_see_results(
    poll: NewsPoll, user: User | None, has_voted: bool, is_closed: bool
) -> bool:
    if _is_privileged(user):
        return True
    if poll.results_visibility == "only_admin_editor":
        return False
    if poll.results_visibility == "always":
        return True
    if poll.results_visibility == "after_vote":
        return has_voted
    if poll.results_visibility == "after_close":
        return is_closed
    return False
