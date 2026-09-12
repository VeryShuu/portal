"""Contract tests for the GET /meetings/bookings `limit` cap.

The calendar endpoint caps `limit` at ``BOOKINGS_LIMIT_MAX`` (default 100,
max 200). These tests assert the cap directly against the FastAPI route's
query-parameter metadata (the ``Query`` FieldInfo), which is the source of
truth that FastAPI turns into 422 errors for out-of-range values and into
the OpenAPI schema. This needs no HTTP client, auth, or DB.

Rationale for not testing the HTTP 422 directly: FastAPI resolves the
endpoint's dependencies (``get_current_user`` → 401, ``MeetingsGuard`` →
404) before surfacing query-param validation errors, so an unauthenticated
or module-disabled request never reaches the limit validation. Asserting
the route's ``FieldInfo`` (``default`` + the ``Ge``/``Le`` constraints in
``metadata``) is the deterministic equivalent.

The service-layer SQL clamp that mirrors this cap is covered by
``tests/unit/test_bookings_queries.py::TestListBookings::test_limit_capped_at_max``.
"""

from __future__ import annotations

import pytest


def _list_bookings_route():
    """Return the GET /meetings/bookings (calendar list) route."""
    from app.api.meetings.bookings import router as bookings_router

    # The bookings router has prefix="/meetings/bookings", so the list
    # endpoint (registered with path "") is exposed at "/meetings/bookings".
    for route in bookings_router.routes:
        methods = getattr(route, "methods", None)
        if getattr(route, "path", None) == "/meetings/bookings" and methods and "GET" in methods:
            return route
    pytest.fail("GET /meetings/bookings route not found on bookings router")


def _limit_param(route):
    for p in route.dependant.query_params:
        if p.name == "limit":
            return p
    pytest.fail("'limit' query param not found on route")


def _bounds(field_info):
    """Extract (ge, le) from a Query FieldInfo's metadata (annotated_types)."""
    ge = le = None
    for constraint in field_info.metadata:
        # annotated_types.Ge / Le expose .ge / .le
        if hasattr(constraint, "ge"):
            ge = constraint.ge
        if hasattr(constraint, "le"):
            le = constraint.le
    return ge, le


class TestBookingsListLimitCap:
    def test_default_and_bounds(self, app):
        from app.services.meetings.bookings_service import BOOKINGS_LIMIT_MAX

        route = _list_bookings_route()
        param = _limit_param(route)
        ge, le = _bounds(param.field_info)

        assert param.field_info.default == 100, param.field_info.default
        assert ge == 1, ge
        # The endpoint cap must mirror the service-layer constant.
        assert le == BOOKINGS_LIMIT_MAX == 200, (le, BOOKINGS_LIMIT_MAX)

    def test_my_endpoint_cap_unchanged(self, app):
        """Only the calendar list endpoint was reduced; /my keeps its own cap."""
        from app.api.meetings.bookings import router as bookings_router
        from app.services.meetings.bookings_service import MY_BOOKINGS_LIMIT_MAX

        my_route = None
        for route in bookings_router.routes:
            if getattr(route, "path", None) == "/meetings/bookings/my":
                my_route = route
                break
        assert my_route is not None

        my_limit = next(p for p in my_route.dependant.query_params if p.name == "limit")
        ge, le = _bounds(my_limit.field_info)
        assert my_limit.field_info.default == 5, my_limit.field_info.default
        assert ge == 1
        assert le == MY_BOOKINGS_LIMIT_MAX == 50, (le, MY_BOOKINGS_LIMIT_MAX)
