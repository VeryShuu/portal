"""Admin management of helpdesk agents (Этап 3).

CRUD над списком «агентов поддержки» — отдельной сущности, не роли портала
(ТЗ §2). Членство в этой таблице — единственный источник прав для
``require_helpdesk_agent``. Все мутации аудируются (``helpdesk.agent_*``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskAgent
from app.models.user import User
from app.schemas.helpdesk import AgentIn, AgentListOut, AgentOut
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(prefix="/helpdesk/agents", tags=["helpdesk"])


def _agent_to_out(agent: HelpdeskAgent) -> AgentOut:
    return AgentOut(
        user_id=agent.user_id,
        notify_new=agent.notify_new,
        added_at=agent.added_at,
        user_name=agent.user.full_name if agent.user else None,
        user_email=agent.user.email if agent.user else None,
    )


async def _load_agent(db: DbDep, user_id: uuid.UUID) -> HelpdeskAgent | None:
    res = await db.execute(
        select(HelpdeskAgent)
        .where(HelpdeskAgent.user_id == user_id)
        .options(selectinload(HelpdeskAgent.user))
    )
    agent = res.scalars().unique().one_or_none()
    return agent


@router.get("", response_model=AgentListOut, summary="Список агентов поддержки")
async def list_agents(
    _admin: AdminDep,
    db: DbDep,
) -> AgentListOut:
    res = await db.execute(
        select(HelpdeskAgent)
        .options(selectinload(HelpdeskAgent.user))
        .order_by(HelpdeskAgent.added_at)
    )
    agents = res.scalars().unique().all()
    return AgentListOut(items=[_agent_to_out(a) for a in agents], total=len(agents))


@router.post(
    "",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить агента поддержки",
)
async def add_agent(
    payload: AgentIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> AgentOut:
    # Проверяем существование пользователя.
    user_res = await db.execute(select(User).where(User.id == payload.user_id))
    if user_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Сохраняем admin-поля до commit: после него атрибуты могут expire
    # (особенно в SAVEPOINT-сессиях тестов), и audit не должен падать.
    admin_id = str(admin.id)
    admin_email = admin.email

    agent = HelpdeskAgent(
        user_id=payload.user_id,
        added_by=admin.id,
        notify_new=payload.notify_new,
    )
    db.add(agent)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already an agent"
        ) from None
    await db.refresh(agent)
    loaded = await _load_agent(db, agent.user_id)
    assert loaded is not None  # только что создан
    await push_audit_event(
        redis,
        event_type="helpdesk.agent_added",
        user_id=admin_id,
        user_email=admin_email,
        resource_type="helpdesk_agent",
        resource_id=str(payload.user_id),
        metadata={"notify_new": payload.notify_new},
    )
    return _agent_to_out(loaded)


@router.patch(
    "/{user_id}",
    response_model=AgentOut,
    summary="Изменить флаг notify_new агента",
)
async def update_agent(
    user_id: uuid.UUID,
    payload: AgentIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> AgentOut:
    agent = await _load_agent(db, user_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    admin_id = str(admin.id)
    admin_email = admin.email
    agent.notify_new = payload.notify_new
    await db.commit()
    await db.refresh(agent)
    await push_audit_event(
        redis,
        event_type="helpdesk.agent_updated",
        user_id=admin_id,
        user_email=admin_email,
        resource_type="helpdesk_agent",
        resource_id=str(user_id),
        metadata={"notify_new": payload.notify_new},
    )
    return _agent_to_out(agent)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить агента поддержки",
)
async def delete_agent(
    user_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    agent = await _load_agent(db, user_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    admin_id = str(admin.id)
    admin_email = admin.email
    await db.delete(agent)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="helpdesk.agent_removed",
        user_id=admin_id,
        user_email=admin_email,
        resource_type="helpdesk_agent",
        resource_id=str(user_id),
    )
