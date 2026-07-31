"""Centralized audit event-type taxonomy.

Single source of truth for the ``event_type`` strings emitted via
:func:`app.services.audit.push_audit_event`. Event types are spread across the
codebase as string literals — without a registry, a typo
(``event_type="links.vistied"``) silently creates a new bucket in
``audit_log`` and only surfaces in ``/audit/event-types`` after ~90 days.

This module provides:

- :class:`EventType` — ``StrEnum`` of all known event types. ``StrEnum`` so
  ``EventType.AUTH_LOGIN == "auth.login"`` → ``True`` (backward-compatible
  with every existing ``push_audit_event(event_type="auth.login")`` call).
- :func:`is_known_event_type` — runtime validator, used by tests.
- :func:`iter_event_types` — for tooling (docgen, consistency checks).

The test :mod:`tests/unit/test_audit_events.py` enforces that every string
literal ``event_type="..."`` in ``app/`` is present in this enum — that's the
real protection against typos and drift. The test already caught a missing
entry during this refactor (``files.file_shared`` hidden inside an
``IfExp`` at the call site). Existing call sites are intentionally NOT
mass-migrated to ``EventType.XXX`` in this refactor; new code should prefer
the enum, and the test will catch any new literal that isn't registered here.

When to add a new event type
----------------------------
1. Add a member to :class:`EventType` below (alphabetical within its prefix).
2. Use it at the call site: ``event_type=EventType.LINKS_VISITED`` (or keep
   the string literal — the test will pass either way once registered here).
3. Update ``docs/audit.md`` §«События аудита» if the event is a new category.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum


class EventType(StrEnum):
    """All known ``event_type`` values emitted to ``audit_log``.

    Naming convention: ``<domain>.<action>`` in lowercase, dot-separated.
    Domains mirror the backend module structure (auth, files, kb, news, ...).
    """

    # --- auth -----------------------------------------------------------
    AUTH_ACCOUNT_LINKED = "auth.account_linked"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_NONCE_MISMATCH = "auth.nonce_mismatch"
    AUTH_SSO_FAILED = "auth.sso_failed"
    AUTH_SSO_LOOP_DETECTED = "auth.sso_loop_detected"

    # --- branding -------------------------------------------------------
    BRANDING_UPDATED = "branding.updated"

    # --- directories ----------------------------------------------------
    DIRECTORIES_ENTRIES_REORDERED = "directories.entries_reordered"
    DIRECTORIES_ENTRY_CREATED = "directories.entry_created"
    DIRECTORIES_ENTRY_DELETED = "directories.entry_deleted"
    DIRECTORIES_ENTRY_UPDATED = "directories.entry_updated"
    DIRECTORIES_TYPE_CREATED = "directories.type_created"
    DIRECTORIES_TYPE_DELETED = "directories.type_deleted"
    DIRECTORIES_TYPE_UPDATED = "directories.type_updated"

    # --- file_icons -----------------------------------------------------
    FILE_ICONS_DELETED = "file_icons.deleted"
    FILE_ICONS_UPDATED = "file_icons.updated"

    # --- files ----------------------------------------------------------
    FILES_BULK_DELETED = "files.bulk_deleted"
    FILES_BULK_MOVE_DRIFT = "files.bulk_move_drift"
    FILES_BULK_MOVED = "files.bulk_moved"
    FILES_FILE_DELETED = "files.file_deleted"
    FILES_FILE_DOWNLOADED = "files.file_downloaded"
    FILES_FILE_OPENED_COLLABORA = "files.file_opened_collabora"
    FILES_FILE_SHARED = "files.file_shared"
    FILES_FILE_SHARE_REVOKED = "files.file_share_revoked"
    FILES_FILE_SHARE_UPDATED = "files.file_share_updated"
    FILES_FILE_UPLOADED = "files.file_uploaded"
    FILES_FOLDER_CREATED = "files.folder_created"
    FILES_FOLDER_DELETE_NC_DRIFT = "files.folder_delete_nc_drift"
    FILES_FOLDER_DELETED = "files.folder_deleted"
    FILES_FOLDER_INHERITANCE_CHANGED = "files.folder_inheritance_changed"
    FILES_FOLDER_RENAMED = "files.folder_renamed"
    FILES_PERMISSION_GRANTED = "files.permission_granted"
    FILES_PERMISSION_REVOKED = "files.permission_revoked"
    FILES_SYNC_FROM_NC = "files.sync_from_nc"
    FILES_UPLOAD_DB_COMMIT_DRIFT = "files.upload_db_commit_drift"

    # --- erp_sync -------------------------------------------------------
    ERP_SYNC_SETTINGS_UPDATED = "erp_sync.settings_updated"

    # --- helpdesk -------------------------------------------------------
    HELPDESK_AGENT_ADDED = "helpdesk.agent_added"
    HELPDESK_AGENT_REMOVED = "helpdesk.agent_removed"
    HELPDESK_AGENT_UPDATED = "helpdesk.agent_updated"
    HELPDESK_ASSIGNED = "helpdesk.assigned"
    HELPDESK_DIGEST_SETTINGS_CHANGED = "helpdesk.digest_settings_changed"
    HELPDESK_MAILBOX_SETTINGS_CHANGED = "helpdesk.mailbox_settings_changed"
    HELPDESK_MAX_BOT_SETTINGS_CHANGED = "helpdesk.max_bot_settings_changed"
    HELPDESK_MESSAGE_ADDED = "helpdesk.message_added"
    HELPDESK_STATUS_CHANGED = "helpdesk.status_changed"
    HELPDESK_TICKET_DELETED = "helpdesk.ticket_deleted"

    # --- kb -------------------------------------------------------------
    KB_ARTICLE_CREATED = "kb.article_created"
    KB_ARTICLE_DELETED = "kb.article_deleted"
    KB_ARTICLE_EXPORTED_DOCX = "kb.article_exported_docx"
    KB_ARTICLE_EXPORTED_MD = "kb.article_exported_md"
    KB_ARTICLE_EXPORTED_PDF = "kb.article_exported_pdf"
    KB_ARTICLE_PURGED = "kb.article_purged"
    KB_ARTICLE_RESTORED = "kb.article_restored"
    KB_ARTICLE_UPDATED = "kb.article_updated"
    KB_FILE_DOWNLOAD = "kb.file_download"
    KB_FILE_UPLOAD = "kb.file_upload"
    KB_PERMISSION_GRANT = "kb.permission_grant"
    KB_PERMISSION_REVOKE = "kb.permission_revoke"
    KB_SECTION_DELETED = "kb.section_deleted"
    KB_TRASH_PURGED = "kb.trash_purged"

    # --- keycloak -------------------------------------------------------
    KEYCLOAK_USER_UPDATED = "keycloak.user_updated"

    # --- links ----------------------------------------------------------
    LINKS_CREATED = "links.created"
    LINKS_DELETED = "links.deleted"
    LINKS_REORDERED = "links.reordered"
    LINKS_UPDATED = "links.updated"
    LINKS_VISITED = "links.visited"

    # --- mailing_recipients ---------------------------------------------
    MAILING_RECIPIENTS_CREATED = "mailing_recipients.created"
    MAILING_RECIPIENTS_DELETED = "mailing_recipients.deleted"
    MAILING_RECIPIENTS_UPDATED = "mailing_recipients.updated"

    # --- modules --------------------------------------------------------
    MODULES_TOGGLED = "modules.toggled"

    # --- news -----------------------------------------------------------
    NEWS_ATTACHMENT_DELETED = "news.attachment_deleted"
    NEWS_COVER_DELETED = "news.cover_deleted"
    NEWS_COVER_UPLOADED = "news.cover_uploaded"
    NEWS_CREATED = "news.created"
    NEWS_DELETED = "news.deleted"
    NEWS_EMAIL_SHARED = "news.email_shared"
    NEWS_GALLERY_IMAGE_DELETED = "news.gallery_image_deleted"
    NEWS_PURGED = "news.purged"
    NEWS_RESTORED = "news.restored"
    NEWS_UPDATED = "news.updated"

    # --- photos ---------------------------------------------------------
    PHOTOS_FOLDER_CREATED = "photos.folder_created"
    PHOTOS_FOLDER_DELETED = "photos.folder_deleted"
    PHOTOS_FOLDER_PURGED = "photos.folder_purged"
    PHOTOS_FOLDER_RESTORED = "photos.folder_restored"
    PHOTOS_FOLDER_SHARE_CREATED = "photos.folder_share_created"
    PHOTOS_FOLDER_SHARE_REVOKED = "photos.folder_share_revoked"
    PHOTOS_PERMISSION_GRANTED = "photos.permission_granted"
    PHOTOS_PERMISSION_REVOKED = "photos.permission_revoked"
    PHOTOS_PHOTO_DELETED = "photos.photo_deleted"
    PHOTOS_PHOTO_DOWNLOADED = "photos.photo_downloaded"
    PHOTOS_PHOTO_PURGED = "photos.photo_purged"
    PHOTOS_PHOTO_RESTORED = "photos.photo_restored"
    PHOTOS_PHOTO_UPLOADED = "photos.photo_uploaded"
    PHOTOS_SHARE_CREATED = "photos.share_created"
    PHOTOS_SHARE_REVOKED = "photos.share_revoked"
    PHOTOS_TRASH_EMPTIED = "photos.trash_emptied"
    PHOTOS_TRASH_EMPTY_REQUESTED = "photos.trash_empty_requested"

    # --- poll -----------------------------------------------------------
    POLL_CLOSED = "poll.closed"
    POLL_CREATED = "poll.created"
    POLL_DELETED = "poll.deleted"
    POLL_REOPENED = "poll.reopened"
    POLL_UPDATED = "poll.updated"

    # --- signature ------------------------------------------------------
    SIGNATURE_SETTINGS_UPDATED = "signature.settings_updated"

    # --- system_settings ------------------------------------------------
    SYSTEM_SETTINGS_ONBOARDING_RESET = "system_settings.onboarding_reset"
    SYSTEM_SETTINGS_ONBOARDING_STEP_RESET_VIEWS = "system_settings.onboarding_step_reset_views"
    SYSTEM_SETTINGS_UPDATED = "system_settings.updated"

    # --- user -----------------------------------------------------------
    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_SYNC_REQUESTED = "user.sync_requested"

    # --- user_attribute_mappings ----------------------------------------
    USER_ATTRIBUTE_MAPPINGS_CREATED = "user_attribute_mappings.created"
    USER_ATTRIBUTE_MAPPINGS_DELETED = "user_attribute_mappings.deleted"
    USER_ATTRIBUTE_MAPPINGS_UPDATED = "user_attribute_mappings.updated"


# Pre-built set for O(1) membership check.
_KNOWN: frozenset[str] = frozenset(e.value for e in EventType)


def is_known_event_type(value: str) -> bool:
    """Return ``True`` if ``value`` is a registered event type.

    Used by ``tests/unit/test_audit_events.py`` to enforce that every string
    literal ``event_type="..."`` in ``app/`` has a matching enum entry.
    """
    return value in _KNOWN


def iter_event_types() -> Iterator[str]:
    """Iterate all known event-type strings (sorted, deterministic)."""
    return iter(sorted(_KNOWN))


def all_event_types() -> list[str]:
    """Return all known event-type strings as a sorted list (for docs/tooling)."""
    return sorted(_KNOWN)
