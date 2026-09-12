"""Periodic health probes for external integrations.

Runs every 60 s via ARQ cron. Each integration (Keycloak, Nextcloud, SMTP,
Collabora) is probed with a short timeout; results (1 = up, 0 = down) are
written to the Redis hash ``INTEGRATION_HEALTH_KEY``. ``refresh_custom_metrics``
then includes them in ``metrics:snapshot`` so the API process can hydrate the
``portal_integration_up`` gauge.

Design constraints:
- A probe must **never** raise — wrap everything in try/except. A slow/hung
  integration should not stall the worker.
- Probes are **gated**: an integration is only checked when it is configured
  (settings present / module enabled). An unconfigured integration simply
  produces no data point.
- Timeouts are aggressive (3-5 s) — this is a liveness probe, not a full
  transaction. We want fast feedback when something is down.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

INTEGRATION_HEALTH_KEY = "integration:health"
INTEGRATION_PROBE_STATE_KEY = "integration:probe:state"
INTEGRATION_HEALTH_TTL = 300  # seconds — stale if not refreshed in 5 min

_PROBE_TIMEOUT = 5.0

# Заведомо несопоставленный логин для зонда согласования 1С: честные HTTP-коды
# после v2.1.0.0 остались только у GETTokenByLogin, 404 = «сервис жив, логина
# нет в регистре соответствий» — это up. Сами токены зонд не выдаёт,
# нагрузка —
# один lookup-промах в минуту. Домен .invalid зарезервирован (RFC 2606) —
# случайное совпадение с реальным сотрудником исключено.
ERP_APPROVALS_PROBE_LOGIN = "portal-health-probe@portal.invalid"


async def _probe_keycloak() -> bool | None:
    """Check Keycloak reachability via the public OIDC discovery endpoint.

    Returns ``None`` when Keycloak is not configured (no settings file) —
    in that case the probe is skipped (no data point emitted).
    """
    from app.services.keycloak.settings import _get_kc_settings

    kc = _get_kc_settings()
    if not kc.keycloak_url or not kc.keycloak_realm:
        return None  # not configured
    base = kc.keycloak_url.rstrip("/")
    url = f"{base}/realms/{kc.keycloak_realm}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(url)
        return cast(bool, resp.status_code == 200)
    except Exception as exc:
        logger.warning("integration.keycloak_probe_failed", error=str(exc))
        return False


async def _probe_nextcloud() -> bool | None:
    """Check Nextcloud reachability via ``status.php``.

    Returns ``None`` when the Nextcloud module is disabled.
    """
    from app.core.modules_config import load_modules
    from app.services.nextcloud import get_nextcloud_service

    modules = load_modules()
    if not modules.nextcloud.enabled:
        return None  # module disabled
    # Reuse the existing health_check (GET status.php), but guard against
    # misconfiguration: if service account isn't set, health_check still
    # works (it only hits the public status.php endpoint).
    try:
        nc = await get_nextcloud_service()
        return await nc.health_check()
    except Exception as exc:
        logger.warning("integration.nextcloud_probe_failed", error=str(exc))
        return False


async def _probe_smtp() -> bool | None:
    """Check SMTP reachability via a raw TCP connect (no SMTP handshake).

    Returns ``None`` when SMTP is not configured (empty host).
    """
    from app.services.email_settings import read_email_settings

    cfg = read_email_settings()
    if not cfg or not cfg.host:
        return None  # not configured
    try:
        _, _writer = await asyncio.wait_for(
            asyncio.open_connection(cfg.host, cfg.port), timeout=_PROBE_TIMEOUT
        )
        _writer.close()
        with contextlib.suppress(Exception):
            await _writer.wait_closed()
        return True
    except Exception as exc:
        logger.warning("integration.smtp_probe_failed", error=str(exc))
        return False


def _collabora_capabilities_url(wopi_url: str) -> str | None:
    """Return a safe Collabora capabilities URL advertised by richdocuments."""
    parsed = urlsplit(wopi_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None

    if not parsed.query:
        path = f"{parsed.path.rstrip('/')}/hosting/capabilities"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    # Built-in CODE advertises ``.../proxy.php?req=`` and expects the proxied
    # path to be appended after the equals sign.
    if parsed.path.endswith("/proxy.php") and parsed.query == "req=":
        return f"{wopi_url}/hosting/capabilities"
    return None


def _ocs_meta_ok(payload: Any) -> bool:
    """OCS envelope considered successful (meta.statuscode == 100)."""
    ocs = payload.get("ocs") if isinstance(payload, dict) else None
    meta = ocs.get("meta") if isinstance(ocs, dict) else None
    return isinstance(meta, dict) and str(meta.get("statuscode")) == "100"


def _extract_wopi_url(payload: Any) -> str | None:
    """Navigate the OCS capabilities envelope to richdocuments wopi_url.

    Every level must be a dict with the expected key; an unexpected shape
    anywhere means "capability absent" (``None``) → probe failure.
    """
    node: Any = payload
    for key in ("ocs", "data", "capabilities", "richdocuments", "config", "wopi_url"):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) else None


def _collabora_version(payload: Any) -> str | None:
    """Non-empty productVersion from the Collabora capabilities payload."""
    version = payload.get("productVersion") if isinstance(payload, dict) else None
    if isinstance(version, str) and version.strip():
        return version
    return None


async def _fetch_wopi_url(nc_url: str, username: str, app_password: str) -> str | None:
    """Authorized OCS capabilities lookup of the richdocuments wopi_url."""
    capabilities_url = f"{nc_url}/ocs/v1.php/cloud/capabilities?format=json"
    ocs_headers = {"OCS-APIRequest": "true", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT, follow_redirects=False) as nc_client:
        response = await nc_client.get(
            capabilities_url,
            headers=ocs_headers,
            auth=httpx.BasicAuth(username, app_password),
        )
    if response.status_code != 200:
        return None
    payload: Any = response.json()
    if not _ocs_meta_ok(payload):
        return None
    return _extract_wopi_url(payload)


async def _collabora_capabilities_ok(collabora_url: str) -> bool:
    """Direct Collabora /hosting/capabilities check: 200 + productVersion.

    A separate client prevents Nextcloud Basic auth from being sent to the
    Collabora origin.
    """
    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT, follow_redirects=False
    ) as collabora_client:
        response = await collabora_client.get(collabora_url, headers={"Accept": "application/json"})
    if response.status_code != 200:
        return False
    return _collabora_version(response.json()) is not None


async def _probe_collabora() -> bool | None:
    """Verify Nextcloud Office configuration and the configured Collabora server.

    ``None`` means the Nextcloud module is disabled. Once enabled, missing
    credentials, a missing richdocuments capability, redirects/login pages and
    unavailable Collabora are all real failures and return ``False``.
    """
    from app.core.modules_config import load_modules
    from app.core.system_config import load_system_settings

    modules = load_modules()
    if not modules.nextcloud.enabled:
        return None

    sys_cfg = load_system_settings()
    nc_url = (sys_cfg.nextcloud_url or "").rstrip("/")
    username = sys_cfg.nc_service_username or ""
    app_password = sys_cfg.nc_service_app_password or ""
    if not nc_url or not username or not app_password:
        return False

    try:
        async with asyncio.timeout(_PROBE_TIMEOUT):
            wopi_url = await _fetch_wopi_url(nc_url, username, app_password)
            collabora_url = _collabora_capabilities_url(wopi_url.strip()) if wopi_url else None
            if collabora_url is None:
                return False
            return await _collabora_capabilities_ok(collabora_url)
    except Exception as exc:
        logger.warning("integration.collabora_probe_failed", error=str(exc))
        return False


async def _probe_erp_sync() -> bool | None:
    """Свежесть ERP-синхронизации.

    Делегирует в :func:`erp_sync.probe_erp_sync` (читает ``erp_sync_runs`` для
    последнего успешного импорта). ``None`` — модуль/poll выключены;
    ``True`` — свежий импорт; ``False`` — протух/ошибок/не было.
    """
    from app.worker.tasks.erp_sync import probe_erp_sync

    return await probe_erp_sync()


async def _probe_erp_absences() -> bool | None:
    """Свежесть потока отсутствий ERP (отпуска/отгулы/болезни).

    Делегирует в :func:`erp_absences_sync.probe_erp_absences`. ``None`` —
    модуль или absence-поллинг выключены; ``True`` — свежий импорт; ``False`` —
    протух/ошибок/не было.
    """
    from app.worker.tasks.erp_absences_sync import probe_erp_absences

    return await probe_erp_absences()


async def _probe_directum() -> bool | None:
    """Свежесть прогонов Directum (просроченные задачи).

    Делегирует в :func:`directum_sync.probe_directum`. ``None`` — модуль или
    задача выключены; ``True`` — свежий прогон; ``False`` — протух/не было.
    """
    from app.worker.tasks.directum_sync import probe_directum

    return await probe_directum()


async def _probe_erp_approvals() -> bool | None:
    """Доступность HTTP-сервиса согласования 1С (модуль «Согласование»).

    Зонд — ``GETTokenByLogin`` с заведомо несопоставленным логином
    (``ERP_APPROVALS_PROBE_LOGIN``), т.е. `client.ping()` без побочных
    эффектов: 404 = «сервис и креды Portal в порядке, логина нет в регистре»
    — это up; 401 — креды отвергнуты; не-JSON — WAF/публикация.

    ``None`` — модуль выключен ИЛИ подключение не настроено (нет точки
    данных, как у остальных зондов). Настроено, но пароль не
    расшифровывается (например, сменился ``SECRET_KEY``) — ``False``: это
    реальная поломка модуля, а не «не настроено».
    """
    from app.core.modules_config import load_modules

    try:
        if not load_modules().approvals.enabled:
            return None
    except Exception:
        return None

    from app.core.database import AsyncSessionLocal
    from app.services.approvals import client
    from app.services.approvals.settings import (
        decrypt_password,
        is_configured,
        load_approvals_settings,
    )

    try:
        async with AsyncSessionLocal() as db:
            row = await load_approvals_settings(db)
    except Exception as exc:
        logger.warning("integration.erp_approvals_settings_failed", error=str(exc))
        return False
    if row is None or not is_configured(row):
        return None
    password = decrypt_password(row)
    if not password:
        logger.warning("integration.erp_approvals_password_undecryptable")
        return False

    try:
        ok, _message, _latency_ms = await client.ping(
            row.base_url,
            (row.token_base_url or "").strip() or row.base_url,
            (row.auth_username, password),
            ERP_APPROVALS_PROBE_LOGIN,
        )
    except Exception as exc:
        logger.warning("integration.erp_approvals_probe_failed", error=str(exc))
        return False
    return ok


async def probe_integrations(ctx: dict) -> dict[str, int]:
    """Run all integration probes and persist results to Redis.

    Called every 60 s by ARQ cron. Writes ``{integration: "1"|"0"}`` to the
    Redis hash ``INTEGRATION_HEALTH_KEY`` (TTL 5 min). ``refresh_custom_metrics``
    picks it up into the metrics snapshot on its own 30 s cadence.
    """
    probes: dict[str, Any] = {
        "keycloak": _probe_keycloak,
        "nextcloud": _probe_nextcloud,
        "smtp": _probe_smtp,
        "collabora": _probe_collabora,
        "erp_sync": _probe_erp_sync,
        "erp_absences": _probe_erp_absences,
        "directum": _probe_directum,
        "erp_approvals": _probe_erp_approvals,
    }

    redis = ctx.get("redis")
    results: dict[str, int] = {}
    expected: dict[str, int] = {}
    attempted_at: dict[str, float] = {}
    completed_at: dict[str, float] = {}
    for name, probe in probes.items():
        attempted_at[name] = time.time()
        if redis is not None:
            try:
                # Persist before awaiting the probe. Cancellation or a hung
                # dependency advances last_attempt but must not advance
                # last_completed.
                await redis.hset(
                    INTEGRATION_PROBE_STATE_KEY,
                    f"{name}:last_attempt",
                    str(attempted_at[name]),
                )
            except Exception as exc:  # pragma: no cover - never break the cron
                logger.warning(
                    "integration.probe_attempt_publish_failed",
                    integration=name,
                    error=str(exc),
                )
        try:
            outcome = await probe()
        except Exception as exc:  # pragma: no cover - belt and suspenders
            logger.warning("integration.probe_unexpected_error", integration=name, error=str(exc))
            outcome = False
        completed_at[name] = time.time()
        expected[name] = 0 if outcome is None else 1
        # None = not configured → no current result. 1/0 = up/down.
        if outcome is not None:
            results[name] = 1 if outcome else 0

    if redis is not None:
        try:
            # Publish a complete generation atomically. The persistent state
            # does not expire with the legacy result hash, so expected and
            # timestamps survive long enough to identify stale/no-data.
            state: dict[str, str] = {}
            for name in probes:
                state[f"{name}:expected"] = str(expected[name])
                state[f"{name}:last_attempt"] = str(attempted_at[name])
                state[f"{name}:last_completed"] = str(completed_at[name])
                if name in results:
                    state[f"{name}:result"] = str(results[name])
                    state[f"{name}:result_expires_at"] = str(
                        completed_at[name] + INTEGRATION_HEALTH_TTL
                    )

            pipe = redis.pipeline(transaction=True)
            pipe.delete(INTEGRATION_HEALTH_KEY)
            pipe.delete(INTEGRATION_PROBE_STATE_KEY)
            if results:
                pipe.hset(
                    INTEGRATION_HEALTH_KEY,
                    mapping={k: str(v) for k, v in results.items()},
                )
                pipe.expire(INTEGRATION_HEALTH_KEY, INTEGRATION_HEALTH_TTL)
            pipe.hset(INTEGRATION_PROBE_STATE_KEY, mapping=state)
            await pipe.execute()
        except Exception as exc:  # pragma: no cover - never break the cron
            logger.warning("integration.probe_publish_failed", error=str(exc))

    logger.info("integration.probed", results=results)
    return results
