"""Shared constants/logger for the users API package."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import ALLOWED_AVATAR_IMG_TYPES
from app.core.logging import get_logger

logger = get_logger("app.api.users")
settings = get_settings()

AVATARS_DIR = Path(os.getenv("DATA_DIR", "/data")) / "avatars"
ALLOWED_IMG_TYPES = ALLOWED_AVATAR_IMG_TYPES
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

__all__ = [
    "ALLOWED_IMG_TYPES",
    "AVATARS_DIR",
    "CONTENT_TYPE_TO_EXT",
    "MAX_AVATAR_SIZE",
    "logger",
    "settings",
]
