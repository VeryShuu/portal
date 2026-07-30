from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbDep
from app.api.meetings import MeetingsGuard
from app.api.users.users_repo import (
    find_active_by_emails,
    find_by_full_name_exact,
    find_by_full_name_substring,
)
from app.core.logging import get_logger
from app.core.modules_config import load_modules
from app.models.user import User
from app.schemas.meetings import (
    InvitedUser,
    ResolveAmbiguousCandidate,
    ResolveAmbiguousItem,
    ResolveParticipantsRequest,
    ResolveParticipantsResponse,
)

router = APIRouter(
    prefix="/meetings/participants",
    tags=["meetings"],
    dependencies=[MeetingsGuard],
)
logger = get_logger(__name__)

# Разделители записей при bulk-resolve: запятая, точка с запятой, перенос, таб.
_BULK_SPLIT_RE = re.compile(r"[,\n;\t]+")
# Классификация токена как email. Используем whitelist разрешённых символов
# (как в app.schemas.user._EMAIL_RE) вместо [^\s@]+ — последний уязвим к ReDoS
# (CodeQL: polynomial regexp on uncontrolled data). Точную валидацию домена
# всё равно выполняет EmailStr в InvitedUser.
_BULK_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,63}$")
# Верхний порог записей для одной bulk-операции (поверх max_length=50 в схеме
# защищает от раздувания одним элементом с десятками записей).
_BULK_MAX_TOKENS = 50


@router.get("/search", response_model=list[InvitedUser])
async def search_participants(
    user: CurrentUser,
    q: str = Query(max_length=100),
    limit: int = Query(default=20, le=50),
) -> list[InvitedUser]:
    min_chars = load_modules().meetings.min_search_chars
    if len(q.strip()) < min_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


def _user_id_of(u: User) -> str:
    """``user_id`` для InvitedUser: keycloak_id (как у single-search) с fallback на БД id.

    ``invited_users`` хранится как JSONB-слепок без FK, дедуп в UI идёт по email,
    поэтому расхождение с single-search (который отдаёт keycloak GUID) безопасно.
    """
    return u.keycloak_id or str(u.id)


def _to_invited(u: User) -> InvitedUser:
    return InvitedUser(
        user_id=_user_id_of(u),
        full_name=u.full_name,
        email=u.email,
        source="keycloak",
    )


def _to_candidate(u: User) -> ResolveAmbiguousCandidate:
    return ResolveAmbiguousCandidate(
        user_id=_user_id_of(u),
        full_name=u.full_name,
        email=u.email,
        department=u.department,
        position=u.position,
    )


def _tokenize_bulk(queries: list[str]) -> list[str]:
    """Плоский дедуплицированный список записей из набора строк.

    Каждая строка ``queries`` разбивается по запятым/переносам/табам; пустые
    фрагменты и дубликаты (CI) отбрасываются.
    """
    seen: set[str] = set()
    tokens: list[str] = []
    for raw in queries:
        for part in _BULK_SPLIT_RE.split(raw):
            token = part.strip()
            if token and token.lower() not in seen:
                seen.add(token.lower())
                tokens.append(token)
    return tokens


@router.post("/resolve", response_model=ResolveParticipantsResponse)
async def resolve_participants(
    data: ResolveParticipantsRequest,
    db: DbDep,
    user: CurrentUser,
) -> ResolveParticipantsResponse:
    """Разобрать список ФИО/email в участников встречи.

    - **email** — точный CI-lookup по ``users`` (индекс ``idx_users_email_ci_active``);
      ненайденный email становится внешним участником (``source=external``), как в single-search.
    - **ФИО** — точное CI-совпадение (с вариантами раскладки клавиатуры) → resolved;
      при 0 точных — подстрочный матч: 1 кандидат → resolved, >1 → ambiguous;
      иначе → unresolved.
    """
    tokens = _tokenize_bulk(data.queries)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No non-empty entries provided",
        )
    if len(tokens) > _BULK_MAX_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Too many entries (max {_BULK_MAX_TOKENS})",
        )

    email_tokens: list[str] = []
    name_tokens: list[str] = []
    for token in tokens:
        (email_tokens if _BULK_EMAIL_RE.match(token) else name_tokens).append(token)

    resolved: list[InvitedUser] = []
    unresolved: list[str] = []
    ambiguous: list[ResolveAmbiguousItem] = []
    # Дедуп по ключу участника (``user_id`` для keycloak, ``email`` для external).
    # Один сотрудник может быть найден и по email, и по ФИО — должен попасть в
    # resolved один раз (как дедупит UI по email).
    seen_keys: set[str] = set()

    def _take(invited: InvitedUser) -> None:
        key = invited.email.lower()
        if key in seen_keys:
            return
        seen_keys.add(key)
        resolved.append(invited)

    # Email: один bulk-запрос по всем адресам, ненайденные → external.
    by_email = await find_active_by_emails(db, {t.lower() for t in email_tokens})
    for token in email_tokens:
        found = by_email.get(token.lower())
        if found is not None:
            _take(_to_invited(found))
        else:
            _take(
                InvitedUser(
                    user_id=f"ext:{token.lower()}",
                    full_name=token,
                    email=token,
                    source="external",
                )
            )

    # ФИО: точный матч → resolved; 0 → подстрочный (ambiguous при >1); иначе unresolved.
    for token in name_tokens:
        exact = await find_by_full_name_exact(db, token)
        if len(exact) == 1:
            _take(_to_invited(exact[0]))
            continue
        if len(exact) > 1:
            ambiguous.append(
                ResolveAmbiguousItem(query=token, candidates=[_to_candidate(u) for u in exact[:5]])
            )
            continue
        subs = await find_by_full_name_substring(db, token)
        if len(subs) == 1:
            _take(_to_invited(subs[0]))
        elif len(subs) > 1:
            ambiguous.append(
                ResolveAmbiguousItem(query=token, candidates=[_to_candidate(u) for u in subs[:5]])
            )
        else:
            unresolved.append(token)

    logger.info(
        "meetings.participants.resolve",
        total_tokens=len(tokens),
        resolved=len(resolved),
        unresolved=len(unresolved),
        ambiguous=len(ambiguous),
    )
    return ResolveParticipantsResponse(
        resolved=resolved, unresolved=unresolved, ambiguous=ambiguous
    )
