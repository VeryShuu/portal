"""Users API package — combined router."""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

from . import routes_admin, routes_me, routes_staff  # noqa: E402,F401
from ._common import settings  # noqa: E402

__all__ = ["router", "settings"]
