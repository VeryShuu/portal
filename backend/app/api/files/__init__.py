"""Files API package — aggregator router + back-compat re-exports.

Original monolith `app/api/files.py` was split into focused submodules
(see ref.md task 1.1.c). API contracts (paths, methods, operationIds)
remain identical — verified via OpenAPI snapshot.
"""

from __future__ import annotations

from fastapi import APIRouter

from .download import router as _download_router
from .files_ops import (
    _bulk_inflight_key,
    _clear_inflight,
    _try_set_inflight,
    _validate_bulk_names,
)
from .files_ops import router as _files_ops_router
from .folders import router as _folders_router
from .permissions import router as _permissions_router
from .shares import router as _shares_router
from .sync import router as _sync_router
from .upload import router as _upload_router

router = APIRouter()

# Order: tree/detail/CRUD → upload → download/preview → file ops →
# permissions → sync. Aggregation order doesn't affect routing semantics —
# FastAPI routes by exact path+method.
router.include_router(_folders_router)
router.include_router(_upload_router)
router.include_router(_download_router)
router.include_router(_files_ops_router)
router.include_router(_permissions_router)
router.include_router(_shares_router)
router.include_router(_sync_router)

__all__ = [
    "_bulk_inflight_key",
    "_clear_inflight",
    "_try_set_inflight",
    "_validate_bulk_names",
    "router",
]
