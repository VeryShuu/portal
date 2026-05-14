"""Users API package — re-exports combined router."""

from ._common import settings
from .routes import router

__all__ = ["router", "settings"]
