"""Роутеры модуля обучения. Регистрация — в app.api.__init__ (prefix /api/v1)."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    admin_categories,
    admin_courses,
    admin_routes,
    admin_tests,
    auth_routes,
    me_routes,
    meta_routes,
    methodists,
)

router = APIRouter()
router.include_router(auth_routes.router)
router.include_router(admin_courses.router)
router.include_router(admin_routes.router)
# порядок не важен: префиксы не пересекаются
router.include_router(admin_tests.router)
router.include_router(me_routes.router)
router.include_router(methodists.router)
router.include_router(meta_routes.router)
router.include_router(admin_categories.router)
