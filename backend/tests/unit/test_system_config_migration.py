"""Unit tests for `migrate_env_to_system_settings()` (audit [M22]).

Covers the parallel-startup race fixed by `_migration_lock.migration_lock`:
when `docker compose up` starts backend + worker + migrations simultaneously,
exactly one process must perform the one-shot legacy-env → `system.json`
write. The other processes must observe the freshly-created file inside the
`flock` and bail out without writing.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def tmp_settings_dir(tmp_path: Path, monkeypatch):
    """Redirect `_SYSTEM_SETTINGS_FILE` to a clean tmp dir (no seed file)."""
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()

    import app.core.system_config as sc

    monkeypatch.setattr(sc, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(sc, "_SYSTEM_SETTINGS_FILE", settings_dir / "system.json")
    monkeypatch.setattr(sc, "_settings_cache", {})

    return {
        "settings_dir": settings_dir,
        "settings_file": settings_dir / "system.json",
    }


@pytest.fixture()
def clean_legacy_env(monkeypatch):
    """Clear every legacy env var so tests start from a known baseline."""
    from app.core.system_config._migrations import _LEGACY_ENV_MAP

    for env_key in _LEGACY_ENV_MAP:
        monkeypatch.delenv(env_key, raising=False)


class TestMigrateEnvToSystemSettings:
    def test_returns_false_and_no_write_when_no_legacy_env(
        self, tmp_settings_dir, clean_legacy_env
    ):
        """Spec case 1: nothing to migrate → False, file not created."""
        from app.core.system_config import migrate_env_to_system_settings

        assert not tmp_settings_dir["settings_file"].exists()
        assert migrate_env_to_system_settings() is False
        assert not tmp_settings_dir["settings_file"].exists()

    def test_writes_json_and_returns_true_when_legacy_env_and_no_file(
        self, tmp_settings_dir, clean_legacy_env, monkeypatch
    ):
        """Spec case 2: legacy env present + no file → write + True."""
        from app.core.system_config import (
            SystemSettings,
            _settings_cache,
            load_system_settings,
            migrate_env_to_system_settings,
        )

        _settings_cache.clear()

        monkeypatch.setenv("PORTAL_BASE_URL", "https://migrated.example")
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "250")
        monkeypatch.setenv("ALLOWED_CIDR", "192.168.10.0/24")

        assert migrate_env_to_system_settings() is True
        assert tmp_settings_dir["settings_file"].exists()

        loaded = load_system_settings()
        assert isinstance(loaded, SystemSettings)
        assert loaded.portal_base_url == "https://migrated.example"
        assert loaded.max_upload_size_mb == 250
        assert loaded.allowed_cidr == "192.168.10.0/24"

    def test_returns_false_and_logs_deprecation_when_file_exists(
        self, tmp_settings_dir, clean_legacy_env, monkeypatch
    ):
        """Spec case 3: file already exists → False, no rewrite, deprecation
        warning emitted (structlog capture, since caplog doesn't see structlog).
        """
        import structlog

        from app.core.system_config import (
            SystemSettings,
            _save_system_settings,
            migrate_env_to_system_settings,
        )

        existing = SystemSettings(portal_base_url="https://existing.example")
        _save_system_settings(existing)
        original_content = tmp_settings_dir["settings_file"].read_text("utf-8")

        monkeypatch.setenv("PORTAL_BASE_URL", "https://should.be.ignored")
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "999")

        with structlog.testing.capture_logs() as caplog:
            result = migrate_env_to_system_settings()

        assert result is False
        # File untouched — same bytes, same mtime semantics.
        assert tmp_settings_dir["settings_file"].read_text("utf-8") == original_content

        deprecated_events = [
            e for e in caplog if e["event"] == "config.deprecated_env_vars_ignored"
        ]
        assert len(deprecated_events) == 1, f"expected one deprecation log, got {caplog!r}"
        warned_vars = set(deprecated_events[0]["vars"])
        assert "PORTAL_BASE_URL" in warned_vars
        assert "MAX_UPLOAD_SIZE_MB" in warned_vars

    def test_idempotent_on_second_call(self, tmp_settings_dir, clean_legacy_env, monkeypatch):
        """First call migrates; second call sees the file and returns False."""
        from app.core.system_config import _settings_cache, migrate_env_to_system_settings

        _settings_cache.clear()
        monkeypatch.setenv("PORTAL_BASE_URL", "https://once.example")

        assert migrate_env_to_system_settings() is True
        assert migrate_env_to_system_settings() is False

    def test_concurrent_callers_write_exactly_once(
        self, tmp_settings_dir, clean_legacy_env, monkeypatch
    ):
        """Spec case 4 (race test): N concurrent callers → exactly one True,
        exactly one persist call, exactly one file on disk.

        `flock` is kernel-level so contention works across threads in the same
        process (each `migration_lock()` opens its own fd). We patch
        `_save_system_settings` with a thread-safe counter to assert that the
        write path was entered exactly once.
        """
        import threading

        import app.core.system_config as sc
        from app.core.system_config import migrate_env_to_system_settings

        _save_calls: list[int] = []
        counter_lock = threading.Lock()
        original_save = sc._save_system_settings

        def _counting_save(s):
            with counter_lock:
                _save_calls.append(1)
            # Real write so the other threads' re-check observes the file.
            return original_save(s)

        monkeypatch.setenv("PORTAL_BASE_URL", "https://race.example")
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "333")

        n_workers = 8
        with (
            patch(
                "app.core.system_config._save_system_settings",
                side_effect=_counting_save,
            ),
            ThreadPoolExecutor(max_workers=n_workers) as pool,
        ):
            results = list(pool.map(lambda _: migrate_env_to_system_settings(), range(n_workers)))

        # Exactly one caller performed the migration.
        assert results.count(True) == 1, f"expected one True, got {results!r}"
        assert results.count(False) == n_workers - 1
        # Exactly one write hit the storage layer.
        assert len(_save_calls) == 1, (
            f"expected exactly one _save_system_settings call, got {len(_save_calls)}"
        )
        # File present and valid.
        assert tmp_settings_dir["settings_file"].exists()
        raw = json.loads(tmp_settings_dir["settings_file"].read_text("utf-8"))
        assert raw["portal_base_url"] == "https://race.example"
        assert raw["max_upload_size_mb"] == 333


class TestMigrationLock:
    """Direct tests for the `_migration_lock.migration_lock` primitive."""

    def test_serializes_concurrent_access(self, tmp_path: Path):
        """Two threads: the second blocks until the first releases."""
        import threading

        from app.core.system_config._migration_lock import migration_lock

        ordering: list[str] = []
        order_lock = threading.Lock()
        second_holder_ready = threading.Event()
        first_can_release = threading.Event()

        def _first():
            with migration_lock(tmp_path):
                with order_lock:
                    ordering.append("first_acquired")
                first_can_release.set()
                # Hold long enough for thread 2 to register as waiting.
                second_holder_ready.wait(timeout=5.0)
                with order_lock:
                    ordering.append("first_releasing")

        def _second():
            first_can_release.wait(timeout=5.0)
            # Signal that we're about to try — we'll block until first releases.
            with migration_lock(tmp_path):
                with order_lock:
                    ordering.append("second_acquired")
                second_holder_ready.set()

        t1 = threading.Thread(target=_first)
        t2 = threading.Thread(target=_second)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert ordering == [
            "first_acquired",
            "first_releasing",
            "second_acquired",
        ], f"lock did not serialize: {ordering!r}"

    def test_acquires_then_releases(self, tmp_path: Path):
        """Trivial acquire/release round-trip yields True."""
        from app.core.system_config._migration_lock import migration_lock

        with migration_lock(tmp_path) as acquired:
            assert acquired is True
        # Re-acquirable immediately after release.
        with migration_lock(tmp_path) as acquired:
            assert acquired is True

    def test_creates_lock_file(self, tmp_path: Path):
        """The lock file is materialized on disk (empty; only flock matters)."""
        from app.core.system_config._migration_lock import migration_lock

        lock_path = tmp_path / ".migration.lock"
        assert not lock_path.exists()
        with migration_lock(tmp_path):
            assert lock_path.exists()
