"""Dummy-задачи для tracked_cron-тестов (PA-021): резолвятся import_string'ом."""

from __future__ import annotations

from typing import Any


async def dummy_cron_task(ctx: dict[str, Any]) -> str:
    return "ok"


async def failing_cron_task(ctx: dict[str, Any]) -> None:
    raise RuntimeError("boom")
