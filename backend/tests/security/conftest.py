"""Auto-mark security/ tests with the `security` marker."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    marker = pytest.mark.security
    for item in items:
        item.add_marker(marker)
