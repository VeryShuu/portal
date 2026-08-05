"""Unit-тесты маппинга ERP-kind → категория статуса (absences_status).

SQL-пересчёт покрыт integration-тестами (нужна реальная БД). Здесь — чистая
логика маппинга и приоритета, без БД.
"""

from __future__ import annotations

from app.services.erp_sync.absences_status import (
    _KIND_TO_CATEGORY,
    ABSENCE_CATEGORY_VALUES,
    category_priority,
    kind_to_category,
)


class TestKindToCategory:
    def test_all_seven_kinds_mapped(self) -> None:
        # Каждый canonical ERP-kind должен маппиться в одну из 4 категорий.
        for kind in (
            "vacation_main",
            "vacation_extra",
            "unpaid_leave",
            "sick",
            "business_trip",
            "day_off_paid",
            "day_off_unpaid",
        ):
            category = kind_to_category(kind)
            assert category in ABSENCE_CATEGORY_VALUES, f"{kind} → {category}"

    def test_vacation_kinds_collapse_to_vacation(self) -> None:
        for kind in (
            "vacation_main",
            "vacation_extra",
            "unpaid_leave",
            "day_off_paid",
            "day_off_unpaid",
        ):
            assert kind_to_category(kind) == "vacation", kind

    def test_sick_maps_to_sick(self) -> None:
        assert kind_to_category("sick") == "sick"

    def test_business_trip_maps_to_business_trip(self) -> None:
        assert kind_to_category("business_trip") == "business_trip"

    def test_unknown_kind_falls_back_to_working(self) -> None:
        # Защита от будущих значений ERP — неизвестный kind не валит пересчёт.
        assert kind_to_category("some_future_kind") == "working"

    def test_kind_map_covers_all_canonical_values(self) -> None:
        # Если в models/erp_sync добавят новый kind, тест заставит явно решить
        # его категорию (не молча уронит в working).
        canonical_kinds = {
            "vacation_main",
            "vacation_extra",
            "unpaid_leave",
            "sick",
            "business_trip",
            "day_off_paid",
            "day_off_unpaid",
        }
        assert set(_KIND_TO_CATEGORY.keys()) == canonical_kinds


class TestCategoryPriority:
    def test_sick_has_highest_priority(self) -> None:
        # Больной в командировке → показываем «болезнь».
        assert category_priority("sick") < category_priority("business_trip")
        assert category_priority("sick") < category_priority("vacation")

    def test_vacation_beats_business_trip(self) -> None:
        # В отпуске и в командировке → показываем «отпуск».
        assert category_priority("vacation") < category_priority("business_trip")

    def test_working_is_lowest(self) -> None:
        # Нет absence → working, наинизший приоритет.
        assert category_priority("working") > category_priority("sick")
        assert category_priority("working") > category_priority("vacation")
        assert category_priority("working") > category_priority("business_trip")

    def test_unknown_category_defaults_to_working(self) -> None:
        assert category_priority("???") == category_priority("working")
