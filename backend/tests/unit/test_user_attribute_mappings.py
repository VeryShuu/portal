"""Тесты для маппингов атрибутов пользователей.

Покрытие:
- Pydantic-схемы (валидация Create/Update DTO)
- _flatten_kc_attributes — нормализация атрибутов из Keycloak Admin API
- Контроль доступа: только admin может управлять маппингами,
  /schema доступен любому аутентифицированному.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── Pydantic-схемы ──────────────────────────────────────────────────────────
class TestCreateUserAttributeMappingRequest:
    def test_valid_minimal(self):
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        req = CreateUserAttributeMappingRequest(attr_key="city", label_ru="Город")
        assert req.attr_key == "city"
        assert req.label_ru == "Город"
        assert req.label_en is None
        assert req.sort_order == 0
        assert req.enabled is True

    def test_attr_key_stripped(self):
        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        req = CreateUserAttributeMappingRequest(attr_key="  city  ", label_ru="Город")
        assert req.attr_key == "city"

    def test_attr_key_blank_rejected(self):
        from pydantic import ValidationError

        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        with pytest.raises(ValidationError):
            CreateUserAttributeMappingRequest(attr_key="   ", label_ru="X")

    def test_label_ru_required(self):
        from pydantic import ValidationError

        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        with pytest.raises(ValidationError):
            CreateUserAttributeMappingRequest(attr_key="city", label_ru="")

    def test_attr_key_max_length(self):
        from pydantic import ValidationError

        from app.schemas.user_attribute_mapping import CreateUserAttributeMappingRequest

        with pytest.raises(ValidationError):
            CreateUserAttributeMappingRequest(attr_key="x" * 256, label_ru="X")


class TestUpdateUserAttributeMappingRequest:
    def test_all_fields_optional(self):
        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        req = UpdateUserAttributeMappingRequest()
        dumped = req.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_partial_update(self):
        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        req = UpdateUserAttributeMappingRequest(enabled=False)
        dumped = req.model_dump(exclude_unset=True)
        assert dumped == {"enabled": False}

    def test_label_ru_blank_rejected(self):
        from pydantic import ValidationError

        from app.schemas.user_attribute_mapping import UpdateUserAttributeMappingRequest

        with pytest.raises(ValidationError):
            UpdateUserAttributeMappingRequest(label_ru="")


# ── _flatten_kc_attributes ──────────────────────────────────────────────────
class TestFlattenKcAttributes:
    def test_empty_dict(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        assert _flatten_kc_attributes({}) == {}

    def test_non_dict_input(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        assert _flatten_kc_attributes(None) == {}  # type: ignore[arg-type]
        assert _flatten_kc_attributes("string") == {}  # type: ignore[arg-type]

    def test_single_value_unwrapped(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        result = _flatten_kc_attributes({"city": ["Москва"]})
        assert result == {"city": "Москва"}

    def test_multi_value_kept_as_list(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        result = _flatten_kc_attributes({"groups": ["a", "b", "c"]})
        assert result == {"groups": ["a", "b", "c"]}

    def test_drops_ldap_internal(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        result = _flatten_kc_attributes(
            {
                "city": ["Москва"],
                "LDAP_ID": ["abc"],
                "LDAP_ENTRY_DN": ["dn"],
                "KERBEROS_PRINCIPAL": ["p"],
                "modifyTimestamp": ["t"],
                "createTimestamp": ["t"],
                "objectClass": ["user"],
            }
        )
        assert result == {"city": "Москва"}

    def test_drops_empty_lists_and_nones(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        result = _flatten_kc_attributes(
            {
                "empty_list": [],
                "all_blanks": ["", None],
                "city": ["Москва"],
            }
        )
        assert result == {"city": "Москва"}

    def test_scalar_value(self):
        from app.worker.tasks.news import _flatten_kc_attributes

        result = _flatten_kc_attributes({"flag": True, "blank": ""})
        assert result == {"flag": True}


# ── Зарезервированные ключи (мапятся в нативные колонки users.*) ────────────
class TestReservedNativeAttrKeys:
    def test_includes_known_kc_attrs(self):
        from app.api.user_attribute_mappings import _RESERVED_NATIVE_ATTR_KEYS

        # Ключи, которые sync_users_from_keycloak записывает в users.email/full_name/
        # department/position/phone — их не должно быть в /discover и нельзя создавать.
        for k in (
            "email",
            "firstName",
            "lastName",
            "name",
            "cn",
            "department",
            "job_title",
            "post",
            "title",
            "phone",
            "telephoneNumber",
        ):
            assert k in _RESERVED_NATIVE_ATTR_KEYS, f"{k} must be reserved"

    def test_does_not_include_neutral_keys(self):
        from app.api.user_attribute_mappings import _RESERVED_NATIVE_ATTR_KEYS

        for k in ("city", "company", "l", "manager"):
            assert k not in _RESERVED_NATIVE_ATTR_KEYS


# ── Контроль доступа к API ──────────────────────────────────────────────────
@pytest.mark.asyncio
class TestUserAttributeMappingsAuthz:
    async def test_list_requires_admin(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.get("/api/v1/user-attribute-mappings")
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_discover_requires_admin(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.get("/api/v1/user-attribute-mappings/discover")
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_create_requires_admin(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.post(
                "/api/v1/user-attribute-mappings",
                json={"attr_key": "city", "label_ru": "Город"},
            )
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_update_requires_admin(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.put(
                f"/api/v1/user-attribute-mappings/{uuid.uuid4()}",
                json={"enabled": False},
            )
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_delete_requires_admin(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.delete(f"/api/v1/user-attribute-mappings/{uuid.uuid4()}")
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_schema_available_for_any_authenticated(self, authed_client_factory):
        """GET /schema — публичная (для любого аутентифицированного)."""
        for role in ("reader", "editor", "admin"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.get("/api/v1/user-attribute-mappings/schema")
            # Authz должен пройти. Body может быть пустым (мокнутый DB → []).
            assert r.status_code == 200, f"role={role} should get 200, got {r.status_code}"
            assert r.json() == {"items": []}
