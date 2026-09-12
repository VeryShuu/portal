"""Поиск пользователей для CC-селектора агента (блок «Ответить всем»).

Симметрично ``meetings/participants.py``: typeahead по справочнику Keycloak
(ФИО/email). В отличие от meetings-endpoint, не зависит от модуля meetings —
гейтится только мастер-флагом ``helpdesk.enabled`` (через parent router).

Фронт (``CcRecipientPicker.vue``) использует результаты как опции dropdown;
если введён email, которого нет в справочнике, фронт сам добавляет синтетическую
«external»-опцию (см. meetings ``ParticipantPicker.vue`` — паттерн скопирован).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, RedisDep
from app.schemas.helpdesk import HelpdeskUserOption

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])

# Минимум символов для поиска (хардкод, как meetings default). SystemSettings
# ради одного селектора избыточны — операционный параметр, меняется редко.
_MIN_SEARCH_CHARS = 3


@router.get(
    "/users/search",
    response_model=list[HelpdeskUserOption],
    summary="Поиск пользователя для CC (ответить всем) по справочнику",
)
async def search_helpdesk_users(
    user: CurrentUser,
    redis: RedisDep,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, le=50),
) -> list[HelpdeskUserOption]:
    # <3 символов → пустой список (не 422): n-select на фронте покажет empty-state,
    # а 422 ломал бы его внутреннюю обработку ошибок. Симметрично meetings, где
    # короткий запрос возвращает 422, но там фронт сам отсекает по minChars раньше.
    if len(q.strip()) < _MIN_SEARCH_CHARS:
        return []
    from app.services.keycloak.directory import search_users

    results = await search_users(q, max_results=limit)

    out: list[HelpdeskUserOption] = []
    for u in results:
        email = u.get("email")
        if not email:
            # Пользователи без email (сервисные/технические аккаунты Keycloak)
            # бесполезны для CC — пропускаем.
            continue
        first = u.get("firstName", "") or ""
        last = u.get("lastName", "") or ""
        full_name = f"{first} {last}".strip() or u.get("username", "")
        out.append(HelpdeskUserOption(user_id=u["id"], full_name=full_name, email=email))
    return out
