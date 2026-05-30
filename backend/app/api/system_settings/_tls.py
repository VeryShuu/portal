"""TLS cert / key + nginx reload admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api import system_settings as _ss
from app.api.deps import AdminDep, RedisDep
from app.core.logging import get_logger
from app.services import nginx_config as _nginx_config
from app.services.nginx_config import trigger_nginx_reload
from app.services.tls_status import TlsStatusOut, get_tls_status_info

logger = get_logger(__name__)

router = APIRouter(tags=["system-settings"])

_VALID_PRIVATE_KEY_HEADERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)

_TLS_FILE_MAX_BYTES = 64 * 1024  # 64 KiB is sufficient for any PEM cert/key


@router.post("/admin/system/nginx/reload")
async def nginx_reload(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    # The nginx-config sidecar already keeps the rendered configs in sync
    # with system.json / certs via inotify; this endpoint just forces an
    # immediate nginx reload without waiting for the next sidecar cycle.
    trigger_nginx_reload()
    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["nginx"]},
    )
    return {"status": "reload_triggered"}


@router.get("/admin/system/tls/status", response_model=TlsStatusOut)
async def get_tls_status(_: AdminDep) -> TlsStatusOut:
    return await get_tls_status_info(
        cert_path=_nginx_config._CERTS_DIR / "portal.crt",
        key_path=_nginx_config._CERTS_DIR / "portal.key",
    )


@router.post("/admin/system/tls/cert")
async def upload_tls_cert(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    content = await file.read(_TLS_FILE_MAX_BYTES + 1)
    if len(content) > _TLS_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл сертификата слишком большой (максимум 64 KiB)",
        )
    if not content.strip().startswith(b"-----BEGIN CERTIFICATE-----"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат сертификата. Ожидается PEM (-----BEGIN CERTIFICATE-----)",
        )
    _nginx_config._CERTS_DIR.mkdir(parents=True, exist_ok=True)
    (_nginx_config._CERTS_DIR / "portal.crt").write_bytes(content)
    # nginx-config sidecar inotifies /data/certs/, re-renders ssl_server.conf
    # (HTTP→HTTPS variant once both crt+key are present) and touches the
    # nginx reload trigger automatically.
    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    logger.info("admin.tls_cert_uploaded")
    return {"status": "ok"}


@router.post("/admin/system/tls/key")
async def upload_tls_key(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    content = await file.read(_TLS_FILE_MAX_BYTES + 1)
    if len(content) > _TLS_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл ключа слишком большой (максимум 64 KiB)",
        )
    head = content.strip()
    if not any(head.startswith(h) for h in _VALID_PRIVATE_KEY_HEADERS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Неверный формат ключа. Ожидается PEM-файл приватного ключа "
                "(-----BEGIN PRIVATE KEY-----, -----BEGIN RSA PRIVATE KEY----- и т.п.). "
                "Сертификаты и CSR сюда загружать нельзя."
            ),
        )
    _nginx_config._CERTS_DIR.mkdir(parents=True, exist_ok=True)
    key_path = _nginx_config._CERTS_DIR / "portal.key"
    key_path.write_bytes(content)
    try:
        import os as _os

        _os.chmod(key_path, 0o600)
    except OSError:
        pass
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    logger.info("admin.tls_key_uploaded")
    return {"status": "ok"}


@router.delete("/admin/system/tls/cert")
async def delete_tls_cert(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    cert_path = _nginx_config._CERTS_DIR / "portal.crt"
    if cert_path.exists():
        cert_path.unlink()
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    return {"status": "ok"}


@router.delete("/admin/system/tls/key")
async def delete_tls_key(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    key_path = _nginx_config._CERTS_DIR / "portal.key"
    if key_path.exists():
        key_path.unlink()
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    return {"status": "ok"}
