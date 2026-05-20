from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser
from app.api.meetings import MeetingsGuard
from app.core.logging import get_logger
from app.core.modules_config import load_modules
from app.schemas.meetings import InvitedUser

router = APIRouter(
    prefix="/meetings/participants",
    tags=["meetings"],
    dependencies=[MeetingsGuard],
)
logger = get_logger(__name__)


@router.get("/search", response_model=list[InvitedUser])
async def search_participants(
    user: CurrentUser,
    q: str = Query(max_length=100),
    limit: int = Query(default=20, le=50),
) -> list[InvitedUser]:
    min_chars = load_modules().meetings.min_search_chars
    if len(q.strip()) < min_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query must be at least {min_chars} characters",
        )
    from app.services.keycloak.directory import search_users

    results = await search_users(q, max_results=limit)

    out: list[InvitedUser] = []
    for u in results:
        email = u.get("email")
        if not email:
            continue
        first = u.get("firstName", "") or ""
        last = u.get("lastName", "") or ""
        full_name = f"{first} {last}".strip() or u.get("username", "")
        out.append(InvitedUser(user_id=u["id"], full_name=full_name, email=email))

    return out
