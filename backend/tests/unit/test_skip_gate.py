"""Subprocess regression-tests for the skip gate, including nested xdist."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.conftest import _DAILY_SKIP_CAPS

_BACKEND = Path(__file__).resolve().parents[2]

_PASS_ONLY = """def test_ok():
    assert True
"""

_ALLOWED_WITHIN_CAP = """import pytest


@pytest.mark.nightly
def test_allowed_one():
    assert True
"""

_FORGED_NIGHTLY_REASON = """import pytest


@pytest.mark.skip(reason="nightly marker: set NIGHTLY=true to run")
def test_forged_reason_without_marker():
    assert True
"""

# Число probe-тестов = актуальный потолок unit-контура + 1 (заведомо over-cap).
# НЕ хардкодим 7: потолок — осознанно меняемая величина (см. _DAILY_SKIP_CAPS),
# гейт-тест должен ломаться от «превышения», а не от смены конкретного числа.
_UNIT_NIGHTLY_CAP = _DAILY_SKIP_CAPS[("unit", "nightly marker: set NIGHTLY=true to run")]
_OVER_CAP_COUNT = _UNIT_NIGHTLY_CAP + 1

_SEVEN_OVER_CAP = """import pytest
""" + "".join(
    f"""

@pytest.mark.nightly
def test_over_{i}():
    assert True
"""
    for i in range(_OVER_CAP_COUNT)
)

_COLLECT_ALLOWED_LOOKING = """import pytest

pytest.skip("NIGHTLY=true required", allow_module_level=True)
"""

_INTEGRATION_NO_MARKER = """async def test_needs_db(real_db_session):
    assert real_db_session is not None
"""

_INTEGRATION_WITH_MARKER = """import pytest


@pytest.mark.unit_with_db
async def test_needs_db(real_db_session):
    assert real_db_session is not None
"""

_TWO_INTEGRATION_NIGHTLY = """import pytest


@pytest.mark.nightly
def test_nightly_one():
    assert True


@pytest.mark.nightly
def test_nightly_two():
    assert True
"""

# Для проб nightly-контракта. ВАЖНО: при NIGHTLY=true маркированные тесты
# ВЫПОЛНАЮТСЯ (auto-skip не навешивается) — поэтому проба «маркированный skip в
# nightly» невозможна by design. Ночное нарушение — это ДРУГИЕ источники skip:
# безусловный skip с произвольной причиной и collection-skip на импорте.
_ARBITRARY_REASON_SKIP = """import pytest


@pytest.mark.skip(reason="локально мне так удобнее")
def test_arbitrary_skip():
    assert True
"""

_NIGHTLY_COLLECTION_SKIP = """import pytest

pytest.skip("NIGHTLY=true required", allow_module_level=True)
"""


@pytest.fixture
def probe_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    """Create a unique repo-local probe for every test and outer xdist worker."""
    worker_input = getattr(request.config, "workerinput", {})
    worker_id = str(worker_input.get("workerid", "master"))
    path = _BACKEND / "tests" / "unit" / f"test_skip_gate_probe_{worker_id}_{uuid.uuid4().hex}.py"
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture
def integration_probe_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    worker_input = getattr(request.config, "workerinput", {})
    worker_id = str(worker_input.get("workerid", "master"))
    path = (
        _BACKEND
        / "tests"
        / "integration"
        / f"test_skip_gate_probe_{worker_id}_{uuid.uuid4().hex}.py"
    )
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# Пробы проверяют daily-контракт гейта (бюджеты/[МАРКЕР]/[COLLECTION]) и обязаны
# запускаться в daily-контуре независимо от окружения самого файла: nightly-flakes
# гоняет suite с NIGHTLY=true + INTEGRATION_DB/REDIS=true, и наследованный env
# уводит пробы в nightly-ветку («любой skip проваливает прогон» без меток) —
# 8 тестов падали только в nightly-прогоне (run #829, attempt 3).
_HERMETIC_ENV_EXCLUDE = frozenset({"NIGHTLY", "INTEGRATION_DB", "INTEGRATION_REDIS"})


def _run_pytest(
    probe: Path, extra_args: list[str] | None = None, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _HERMETIC_ENV_EXCLUDE}
    env.update(env_extra or {})
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe),
            "-s",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            *(extra_args or []),
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def _output(proc: subprocess.CompletedProcess[str]) -> str:
    return f"{proc.stdout}\n{proc.stderr}"


def _assert_gate_failure(proc: subprocess.CompletedProcess[str], marker: str) -> None:
    assert proc.returncode == 1, _output(proc)
    assert marker in _output(proc)


def test_gate_passes_without_skips(probe_path: Path):
    probe_path.write_text(_PASS_ONLY, encoding="utf-8")
    proc = _run_pytest(probe_path)
    assert proc.returncode == 0, _output(proc)


def test_gate_allows_budgeted_nightly_marker(probe_path: Path):
    probe_path.write_text(_ALLOWED_WITHIN_CAP, encoding="utf-8")
    proc = _run_pytest(probe_path)
    assert proc.returncode == 0, _output(proc)


def test_gate_rejects_forged_nightly_reason(probe_path: Path):
    probe_path.write_text(_FORGED_NIGHTLY_REASON, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path), "nightly-skip допустим только тестам")


def test_gate_fails_over_cap(probe_path: Path):
    probe_path.write_text(_SEVEN_OVER_CAP, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path), "[БЮДЖЕТ]")


def test_gate_fails_over_cap_under_xdist(probe_path: Path):
    probe_path.write_text(_SEVEN_OVER_CAP, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path, ["-n", "2"]), "[БЮДЖЕТ]")


def test_collection_skip_with_allowed_reason_fails(probe_path: Path):
    probe_path.write_text(_COLLECT_ALLOWED_LOOKING, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path), "[COLLECTION]")


def test_collection_skip_fails_under_xdist(probe_path: Path):
    probe_path.write_text(_COLLECT_ALLOWED_LOOKING, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path, ["-n", "2"]), "[COLLECTION]")


def test_collection_skip_importorskip_missing_dep_fails(probe_path: Path):
    probe_path.write_text(
        "import pytest\npytest.importorskip('definitely-missing-pkg-xyz')\n",
        encoding="utf-8",
    )
    _assert_gate_failure(_run_pytest(probe_path), "[COLLECTION]")


def test_integration_skip_without_marker_fails(probe_path: Path):
    probe_path.write_text(_INTEGRATION_NO_MARKER, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path), "INTEGRATION_*-skip")


def test_integration_skip_with_marker_passes(probe_path: Path):
    probe_path.write_text(_INTEGRATION_WITH_MARKER, encoding="utf-8")
    proc = _run_pytest(probe_path)
    assert proc.returncode == 0, _output(proc)


def test_integration_skip_with_marker_passes_under_xdist(probe_path: Path):
    probe_path.write_text(_INTEGRATION_WITH_MARKER, encoding="utf-8")
    proc = _run_pytest(probe_path, ["-n", "2"])
    assert proc.returncode == 0, _output(proc)


def test_integration_context_has_independent_nightly_cap(integration_probe_path: Path):
    integration_probe_path.write_text(_TWO_INTEGRATION_NIGHTLY, encoding="utf-8")
    _assert_gate_failure(_run_pytest(integration_probe_path), "контур «integration»")


# ── Nightly-контракт гейта ─────────────────────────────────────────────────────
# Фикс a8899f8 вырезает NIGHTLY из env проб — пробы всегда проверяют daily-контракт,
# и nightly-ветка гейта (pytest_sessionfinish: «любой skip проваливает прогон»)
# осталась без регрессионного покрытия: мутация session.exitstatus=1 → pass была бы
# незамечена. Пробы ниже восстанавливают покрытие nightly-ветки явным env_extra.


def test_gate_nightly_contract_rejects_arbitrary_reason_skip(probe_path: Path):
    """В NIGHTLY-прогоне skip с произвольной причиной — провал (бюджетов нет)."""
    probe_path.write_text(_ARBITRARY_REASON_SKIP, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path, env_extra={"NIGHTLY": "true"}), "неожиданных skip")


def test_gate_nightly_contract_rejects_collection_skip(probe_path: Path):
    """В NIGHTLY-прогоне module-level skip — провал (вне любых бюджетов)."""
    probe_path.write_text(_NIGHTLY_COLLECTION_SKIP, encoding="utf-8")
    _assert_gate_failure(_run_pytest(probe_path, env_extra={"NIGHTLY": "true"}), "неожиданных skip")


def test_gate_nightly_enables_marked_tests_instead_of_skipping(probe_path: Path):
    """NIGHTLY=true: маркированные тесты выполняются, а не скипаются.

    Ловит инверсию условия в pytest_collection_modifyitems (early-return при
    NIGHTLY): если её убрать, маркированные тесты скипнутся даже в nightly —
    прогон провалится по контракту «любой skip = провал».
    """
    probe_path.write_text(_ALLOWED_WITHIN_CAP, encoding="utf-8")
    proc = _run_pytest(probe_path, env_extra={"NIGHTLY": "true"})
    assert proc.returncode == 0, _output(proc)
    assert "1 passed" in _output(proc)
