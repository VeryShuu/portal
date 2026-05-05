PERM_VIEWER = "viewer"
IDEMPOTENCY_TTL = 86400
PERM_EDITOR = "editor"
PERM_MANAGER = "manager"
PERM_UPLOADER = "uploader"
VIEW_DEDUP_TTL_SECONDS = 3600

ALLOWED_AVATAR_IMG_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_NEWS_COVER_IMG_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
