"""Unit-тесты absence-enrichment: чистая логика helpers (без БД).

SQL-запросы и приоритет схлопывания покрыты integration-тестами (нужна реальная
БД с erp_absences). Здесь — только быстрые проверки helpers.
"""

from __future__ import annotations

from app.services.meetings.absence_enrichment import (
    _category_priority,
    _extract_email,
    _is_keycloak,
)


class TestHelpers:
    def test_extract_email_from_dict(self) -> None:
        assert _extract_email({"email": "a@b.com"}) == "a@b.com"

    def test_extract_email_from_dict_missing(self) -> None:
        assert _extract_email({}) == ""

    def test_extract_email_from_invited_user(self) -> None:
        from app.schemas.meetings import InvitedUser

        u = InvitedUser(user_id="x", full_name="A", email="a@b.com")
        assert _extract_email(u) == "a@b.com"

    def test_is_keycloak_default_for_dict(self) -> None:
        # Запись без source трактуется как keycloak (обратная совместимость).
        assert _is_keycloak({"email": "a@b.com"}) is True

    def test_is_keycloak_explicit_keycloak(self) -> None:
        assert _is_keycloak({"source": "keycloak"}) is True

    def test_is_keycloak_external_skipped(self) -> None:
        assert _is_keycloak({"source": "external"}) is False

    def test_is_keycloak_invited_user_external(self) -> None:
        from app.schemas.meetings import InvitedUser

        u = InvitedUser(user_id="ext:a@b.com", full_name="A", email="a@b.com", source="external")
        assert _is_keycloak(u) is False


class TestCategoryPriority:
    def test_sick_highest(self) -> None:
        assert _category_priority("sick") < _category_priority("vacation")
        assert _category_priority("sick") < _category_priority("business_trip")

    def test_vacation_beats_business_trip(self) -> None:
        assert _category_priority("vacation") < _category_priority("business_trip")

    def test_unknown_lowest(self) -> None:
        # Неизвестная категория не должна перебивать canonical — 99.
        assert _category_priority("???") > _category_priority("sick")
        assert _category_priority("???") > _category_priority("business_trip")
