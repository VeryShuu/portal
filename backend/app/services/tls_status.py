from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class TlsStatusOut(BaseModel):
    cert_exists: bool
    key_exists: bool
    cert_expires_at: str | None
    cert_subject: str | None


async def get_tls_status_info(cert_path: Path, key_path: Path) -> TlsStatusOut:
    cert_expires_at = None
    cert_subject = None

    if cert_path.exists():
        try:
            proc = await asyncio.create_subprocess_exec(
                "openssl",
                "x509",
                "-noout",
                "-enddate",
                "-subject",
                "-in",
                str(cert_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            for line in stdout.decode().splitlines():
                if line.startswith("notAfter="):
                    cert_expires_at = line.removeprefix("notAfter=").strip()
                elif line.startswith("subject="):
                    cert_subject = line.removeprefix("subject=").strip()
        except Exception as exc:
            logger.debug("tls_status.openssl_read_failed", error=str(exc))

    return TlsStatusOut(
        cert_exists=cert_path.exists(),
        key_exists=key_path.exists(),
        cert_expires_at=cert_expires_at,
        cert_subject=cert_subject,
    )
