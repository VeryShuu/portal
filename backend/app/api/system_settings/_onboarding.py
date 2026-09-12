"""Onboarding-related routes (public + admin reset)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.engine import CursorResult

from app.api import system_settings as _ss
from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.core.system_config import (
    _CACHE_VERSION_KEY,
    OnboardingStep,
    _save_system_settings,
    load_system_settings_shared,
)

logger = get_logger(__name__)

router = APIRouter(tags=["system-settings"])


class OnboardingPublicOut(BaseModel):
    onboarding_enabled: bool
    onboarding_reset_trigger: str
    onboarding_steps: list[OnboardingStep] | None = None


class OnboardingResetOut(BaseModel):
    updated: int
    reset_trigger: str


class OnboardingStepResetViewsIn(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)


class OnboardingStepResetViewsOut(BaseModel):
    updated: int
    step_id: str


class OnboardingStatsOut(BaseModel):
    total_users: int
    completed: int
    completed_via_finished: int
    completed_via_skipped: int
    seen_step_counts: dict[str, int]


@router.get("/portal/onboarding", response_model=OnboardingPublicOut)
async def get_onboarding_public(
    _: CurrentUser,
    redis: RedisDep,
) -> OnboardingPublicOut:
    s = await load_system_settings_shared(redis)
    return OnboardingPublicOut(
        onboarding_enabled=s.onboarding_enabled,
        onboarding_reset_trigger=s.onboarding_reset_trigger,
        onboarding_steps=s.onboarding_steps,
    )


@router.post(
    "/admin/system/settings/onboarding/reset",
    response_model=OnboardingResetOut,
)
async def reset_onboarding(
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> OnboardingResetOut:
    current = await load_system_settings_shared(redis)
    result = await db.execute(
        sa_text(
            "UPDATE users "
            "SET preferences = preferences - 'onboarding_completed' "
            "WHERE preferences ? 'onboarding_completed'"
        )
    )
    await db.commit()
    updated = int(cast(CursorResult, result).rowcount or 0)

    reset_trigger = datetime.now(UTC).isoformat()
    new_settings = current.model_copy(update={"onboarding_reset_trigger": reset_trigger})
    _save_system_settings(new_settings)
    await bump_version(redis, _CACHE_VERSION_KEY)

    await _ss._emit_audit(
        redis,
        event_type="system_settings.onboarding_reset",
        user_id=str(admin.id),
        metadata={"updated_users": updated, "reset_trigger": reset_trigger},
    )
    logger.info(
        "admin.onboarding_reset",
        admin_id=str(admin.id),
        updated_users=updated,
        reset_trigger=reset_trigger,
    )
    return OnboardingResetOut(updated=updated, reset_trigger=reset_trigger)


@router.get(
    "/admin/system/settings/onboarding/stats",
    response_model=OnboardingStatsOut,
)
async def get_onboarding_stats(admin: AdminDep, db: DbDep) -> OnboardingStatsOut:
    """Агрегаты прохождения экскурса (без персональных данных).

    ``completed`` считает всех, у кого стоит ``onboarding_completed=true``
    (независимо от способа завершения); ``completed_via_*`` разбивают на
    «дошёл до конца» / «пропустил». Пользователи, завершившие тур до
    внедрения метрики, попадают только в ``completed`` (via-брекдауны их
    не считают). ``seen_step_counts`` — сколько сотрудников видели каждый
    шаг (ключ = id шага).
    """
    totals = await db.execute(
        sa_text(
            "SELECT "
            "count(*), "
            "count(*) FILTER (WHERE preferences @> "
            "'{\"onboarding_completed\": true}'::jsonb), "
            "count(*) FILTER (WHERE preferences->>'onboarding_completed_via' "
            "= 'finished'), "
            "count(*) FILTER (WHERE preferences->>'onboarding_completed_via' "
            "= 'skipped') "
            "FROM users WHERE deleted_at IS NULL"
        )
    )
    total_users, completed, via_finished, via_skipped = totals.one()

    seen = await db.execute(
        sa_text(
            "SELECT s.id, count(*) "
            "FROM users, jsonb_array_elements_text("
            "preferences->'onboarding_seen_step_ids') AS s(id) "
            "WHERE deleted_at IS NULL "
            "GROUP BY s.id"
        )
    )
    seen_counts = {row[0]: int(row[1]) for row in seen.fetchall()}

    return OnboardingStatsOut(
        total_users=int(total_users),
        completed=int(completed),
        completed_via_finished=int(via_finished),
        completed_via_skipped=int(via_skipped),
        seen_step_counts=seen_counts,
    )


@router.post(
    "/admin/system/settings/onboarding/steps/reset-views",
    response_model=OnboardingStepResetViewsOut,
)
async def reset_onboarding_step_views(
    body: OnboardingStepResetViewsIn,
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> OnboardingStepResetViewsOut:
    """Remove the given step_id from every user's onboarding_seen_step_ids array."""
    result = await db.execute(
        sa_text(
            "UPDATE users "
            "SET preferences = jsonb_set("
            "    preferences, "
            "    '{onboarding_seen_step_ids}', "
            "    (preferences->'onboarding_seen_step_ids') - :sid"
            ") "
            "WHERE jsonb_typeof(preferences->'onboarding_seen_step_ids') = 'array' "
            "  AND preferences->'onboarding_seen_step_ids' ? :sid"
        ),
        {"sid": body.step_id},
    )
    await db.commit()
    updated = int(cast(CursorResult, result).rowcount or 0)

    await _ss._emit_audit(
        redis,
        event_type="system_settings.onboarding_step_reset_views",
        user_id=str(admin.id),
        metadata={
            "step_id": body.step_id,
            "updated_users": updated,
        },
    )
    logger.info(
        "admin.onboarding_step_reset_views",
        admin_id=str(admin.id),
        step_id=body.step_id,
        updated_users=updated,
    )
    return OnboardingStepResetViewsOut(updated=updated, step_id=body.step_id)
