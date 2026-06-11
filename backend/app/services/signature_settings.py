"""Storage for the email-signature runtime config.

Persists :class:`SignatureSettings` to ``/data/settings/signature.json`` using
the shared atomic-write helper. Single place that reads/parses the file so the
on-disk schema is defined in one spot (mirrors ``app.services.email_settings``).
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.schemas.signature import SignatureSettings

logger = get_logger(__name__)

SETTINGS_DIR = Path("/data/settings")
SIGNATURE_SETTINGS_FILE = SETTINGS_DIR / "signature.json"


def read_signature_settings() -> SignatureSettings | None:
    if SIGNATURE_SETTINGS_FILE.exists():
        try:
            return SignatureSettings.model_validate_json(
                SIGNATURE_SETTINGS_FILE.read_text("utf-8")
            )
        except Exception:
            logger.exception("signature_settings.load_failed")
    return None


def load_signature_settings() -> SignatureSettings:
    return read_signature_settings() or SignatureSettings()


def save_signature_settings(s: SignatureSettings) -> None:
    from app.core.system_config import atomic_write

    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(SIGNATURE_SETTINGS_FILE, s.model_dump_json(indent=2))
