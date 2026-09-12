"""Admin API helpers: user/group lookups, membership maps."""

from __future__ import annotations

from typing import Any, cast


async def search_users(q: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search users in Keycloak by username/email/name."""
    from app.services import keycloak as _kc

    token = await _kc._get_directory_token()
    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users",
        headers={"Authorization": f"Bearer {token}"},
        params={"search": q, "max": max_results, "briefRepresentation": "false"},
    )
    response.raise_for_status()
    return cast(list[dict[str, Any]], response.json())


async def search_groups(q: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search groups in Keycloak by name."""
    from app.services import keycloak as _kc

    token = await _kc._get_directory_token()
    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/groups",
        headers={"Authorization": f"Bearer {token}"},
        params={"search": q, "max": max_results, "briefRepresentation": "true"},
    )
    response.raise_for_status()
    return cast(list[dict[str, Any]], response.json())


async def get_admin_users(page: int = 0, size: int = 100) -> list[dict[str, Any]]:
    """Fetch users from Keycloak Admin API using sync service account (view-users only)."""
    from app.services import keycloak as _kc

    token = await _kc._get_sync_token()
    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users",
        headers={"Authorization": f"Bearer {token}"},
        params={"first": page * size, "max": size, "briefRepresentation": "false"},
        timeout=30.0,
    )
    response.raise_for_status()
    return cast(list[dict[str, Any]], response.json())


async def get_user_groups(user_id: str) -> list[str]:
    """Fetch group paths for a single user from Keycloak Admin API."""
    from app.services import keycloak as _kc

    token = await _kc._get_sync_token()
    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users/{user_id}/groups",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return [g.get("path", g.get("name", "")) for g in response.json()]


async def get_groups_members_map(page_size: int = 100) -> dict[str, list[str]]:
    """Return inverted mapping ``{keycloak_user_id: [group_path, ...]}``.

    Walks all top-level groups via ``/admin/realms/{realm}/groups`` (paginated),
    then fetches ``/groups/{id}/members`` for each group. Avoids the N+1
    ``/users/{id}/groups`` pattern of the per-user sync.
    """
    from app.services import keycloak as _kc

    token = await _kc._get_sync_token()
    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()

    base = f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}"
    headers = {"Authorization": f"Bearer {token}"}

    all_groups: list[dict[str, Any]] = []
    first = 0
    while True:
        resp = await client.get(
            f"{base}/groups",
            headers=headers,
            params={"first": first, "max": page_size, "briefRepresentation": "false"},
            timeout=30.0,
        )
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        all_groups.extend(chunk)
        if len(chunk) < page_size:
            break
        first += page_size

    def _flatten(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        stack = list(groups)
        while stack:
            g = stack.pop()
            flat.append(g)
            sub = g.get("subGroups") or []
            if sub:
                stack.extend(sub)
        return flat

    flat_groups = _flatten(all_groups)

    user_to_groups: dict[str, list[str]] = {}
    for g in flat_groups:
        gid = g.get("id")
        gpath = g.get("path") or g.get("name") or ""
        if not gid:
            continue
        first_m = 0
        while True:
            mresp = await client.get(
                f"{base}/groups/{gid}/members",
                headers=headers,
                params={"first": first_m, "max": page_size, "briefRepresentation": "true"},
                timeout=30.0,
            )
            mresp.raise_for_status()
            members = mresp.json()
            if not members:
                break
            for m in members:
                uid = m.get("id")
                if not uid:
                    continue
                user_to_groups.setdefault(uid, []).append(gpath)
            if len(members) < page_size:
                break
            first_m += page_size

    return user_to_groups
