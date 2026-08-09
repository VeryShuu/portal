"""Centralized audit event-type registry.

Single source of truth for the ``event_type`` strings emitted via
:func:`app.services.audit.push_audit_event`. Event types are spread across the
codebase as string literals — without a registry, a typo
(``event_type="links.vistied"``) silently creates a new bucket in
``audit_log`` and only surfaces in ``/audit/event-types`` after ~90 days.

This module provides:

- :data:`KNOWN_EVENT_TYPES` — ``frozenset[str]`` of all registered event-type
  strings. Plain strings (not a ``StrEnum``) because every call site passes a
  string literal anyway, and the public contract — the ``/audit/event-types``
  endpoint and the frontend dropdown — derives from
  ``SELECT DISTINCT event_type FROM audit_log``, not from this set.
- :func:`is_known_event_type` — runtime validator, used by tests.
- :func:`iter_event_types` — for tooling (docgen, consistency checks).

The test :mod:`tests/unit/test_audit_events.py` enforces that every string
literal ``event_type="..."`` in ``app/`` is present in this registry — that's
the real protection against typos and drift. The test already caught a missing
entry during this refactor (``files.file_shared`` hidden inside an
``IfExp`` at the call site).

Why a ``frozenset`` and not a ``StrEnum``?
A ``StrEnum`` was originally introduced here as a source of truth, but **zero
call sites ever used it** — all 27+ ``push_audit_event`` callers pass plain
string literals. Keeping a ~115-member ``StrEnum`` that nobody references is
dead abstraction: it gives a false sense of type safety while the actual
protection lives in the AST scan in ``test_audit_events.py``. A ``frozenset``
is honest about what this is — a registry the test checks against — with no
maintenance burden of keeping enum member names in sync. See audit task [H6]
(``audit.md``) for the full rationale.

When to add a new event type
----------------------------
1. Add the string to :data:`KNOWN_EVENT_TYPES` below (alphabetical within its
   prefix group).
2. Use it at the call site: ``event_type="links.visited"``.
3. Update ``docs/audit.md`` §«События аудита» if the event is a new category.
"""

from __future__ import annotations

from collections.abc import Iterator

# Single source of truth for all known ``event_type`` values.
#
# Naming convention: ``<domain>.<action>`` in lowercase, dot-separated.
# Domains mirror the backend module structure (auth, files, kb, news, ...).
#
# NOTE: keep values sorted within each domain group; the AST-based test in
# ``tests/unit/test_audit_events.py`` will fail if any literal in ``app/`` is
# missing here OR if any value here has no matching literal (bidirectional).
KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # --- auth -----------------------------------------------------------
        "auth.account_linked",
        "auth.login",
        "auth.logout",
        "auth.nonce_mismatch",
        "auth.sso_failed",
        "auth.sso_loop_detected",
        # --- branding -------------------------------------------------------
        "branding.updated",
        # --- directories ----------------------------------------------------
        "directories.entries_reordered",
        "directories.entry_created",
        "directories.entry_deleted",
        "directories.entry_updated",
        "directories.type_created",
        "directories.type_deleted",
        "directories.type_updated",
        # --- file_icons -----------------------------------------------------
        "file_icons.deleted",
        "file_icons.updated",
        # --- files ----------------------------------------------------------
        "files.bulk_deleted",
        "files.bulk_move_drift",
        "files.bulk_moved",
        "files.file_deleted",
        "files.file_downloaded",
        "files.file_opened_collabora",
        "files.file_shared",
        "files.file_share_revoked",
        "files.file_share_updated",
        "files.file_uploaded",
        "files.folder_created",
        "files.folder_delete_nc_drift",
        "files.folder_deleted",
        "files.folder_inheritance_changed",
        "files.folder_renamed",
        "files.permission_granted",
        "files.permission_revoked",
        "files.sync_from_nc",
        "files.upload_db_commit_drift",
        # --- erp_sync -------------------------------------------------------
        "erp_sync.settings_updated",
        # --- helpdesk -------------------------------------------------------
        "helpdesk.agent_added",
        "helpdesk.agent_removed",
        "helpdesk.agent_updated",
        "helpdesk.assigned",
        "helpdesk.digest_settings_changed",
        "helpdesk.mailbox_settings_changed",
        "helpdesk.max_bot_settings_changed",
        "helpdesk.message_added",
        "helpdesk.status_changed",
        "helpdesk.ticket_deleted",
        # --- kb -------------------------------------------------------------
        "kb.article_created",
        "kb.article_deleted",
        "kb.article_exported_docx",
        "kb.article_exported_md",
        "kb.article_exported_pdf",
        "kb.article_purged",
        "kb.article_restored",
        "kb.article_updated",
        "kb.file_download",
        "kb.file_upload",
        "kb.permission_grant",
        "kb.permission_revoke",
        "kb.section_deleted",
        "kb.trash_purged",
        # --- keycloak -------------------------------------------------------
        "keycloak.user_updated",
        # --- links ----------------------------------------------------------
        "links.created",
        "links.deleted",
        "links.reordered",
        "links.updated",
        "links.visited",
        # --- mailing_recipients ---------------------------------------------
        "mailing_recipients.created",
        "mailing_recipients.deleted",
        "mailing_recipients.updated",
        # --- modules --------------------------------------------------------
        "modules.toggled",
        # --- news -----------------------------------------------------------
        "news.attachment_deleted",
        "news.cover_deleted",
        "news.cover_uploaded",
        "news.created",
        "news.deleted",
        "news.email_shared",
        "news.gallery_image_deleted",
        "news.purged",
        "news.restored",
        "news.updated",
        # --- photos ---------------------------------------------------------
        "photos.folder_created",
        "photos.folder_deleted",
        "photos.folder_purged",
        "photos.folder_restored",
        "photos.folder_share_created",
        "photos.folder_share_revoked",
        "photos.permission_granted",
        "photos.permission_revoked",
        "photos.photo_deleted",
        "photos.photo_downloaded",
        "photos.photo_purged",
        "photos.photo_restored",
        "photos.photo_uploaded",
        "photos.share_created",
        "photos.share_revoked",
        "photos.trash_emptied",
        "photos.trash_empty_requested",
        # --- poll -----------------------------------------------------------
        "poll.closed",
        "poll.created",
        "poll.deleted",
        "poll.reopened",
        "poll.updated",
        # --- signature ------------------------------------------------------
        "signature.settings_updated",
        # --- system_settings ------------------------------------------------
        "system_settings.onboarding_reset",
        "system_settings.onboarding_step_reset_views",
        "system_settings.updated",
        # --- user -----------------------------------------------------------
        "user.created",
        "user.deleted",
        "user.password_changed",
        "user.password_reset",
        "user.profile_updated",
        "user.role_changed",
        "user.sync_requested",
        # --- user_attribute_mappings ----------------------------------------
        "user_attribute_mappings.created",
        "user_attribute_mappings.deleted",
        "user_attribute_mappings.updated",
    }
)


def is_known_event_type(value: str) -> bool:
    """Return ``True`` if ``value`` is a registered event type.

    Used by ``tests/unit/test_audit_events.py`` to enforce that every string
    literal ``event_type="..."`` in ``app/`` is registered here.
    """
    return value in KNOWN_EVENT_TYPES


def iter_event_types() -> Iterator[str]:
    """Iterate all known event-type strings (sorted, deterministic)."""
    return iter(sorted(KNOWN_EVENT_TYPES))


def all_event_types() -> list[str]:
    """Return all known event-type strings as a sorted list (for docs/tooling)."""
    return sorted(KNOWN_EVENT_TYPES)
