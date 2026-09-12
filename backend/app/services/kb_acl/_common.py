"""Common constants, cache-key helpers and permission ranking for KB ACL."""

from __future__ import annotations

import uuid

from app.core.constants import PERM_EDITOR, PERM_MANAGER, PERM_VIEWER
from app.core.logging import get_logger
from app.services.acl_base import (
    ACL_TTL as _ACL_TTL,
)
from app.services.acl_base import (
    get_cached as _get_cached,
)
from app.services.acl_base import (
    scan_and_delete as _scan_and_delete,
)
from app.services.acl_base import (
    set_cached as _set_cached,
)
from app.services.acl_base import (
    subject_ids_for_user as _subject_ids_for_user,
)

logger = get_logger(__name__)

_PERM_RANK = {PERM_VIEWER: 1, PERM_EDITOR: 2, PERM_MANAGER: 3}


def perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


# Backward-compatible alias (preferred name is perm_gte without underscore).
_perm_gte = perm_gte


def _cache_key(user_id: uuid.UUID, resource: str, resource_id: uuid.UUID) -> str:
    return f"kb_acl:{user_id}:{resource}:{resource_id}"


__all__ = [
    "PERM_EDITOR",
    "PERM_MANAGER",
    "PERM_VIEWER",
    "_ACL_TTL",
    "_PERM_RANK",
    "_cache_key",
    "_get_cached",
    "_perm_gte",
    "_scan_and_delete",
    "_set_cached",
    "_subject_ids_for_user",
    "logger",
    "perm_gte",
]
