"""Unit-тесты межпроцессного flock-хелпера (F4).

Покрытие:
- interprocess_lock создаёт lock-файл и его родителя
- блокирующая взаимная эксклюзивность: второй держатель ждёт освобождения
- lock освобождается после выхода из with (повторный захват не висит)
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from app.services._persistence_lock import interprocess_lock


def test_creates_lock_file_and_parent(tmp_path):
    lock_file = tmp_path / "nested" / "dir" / "state.lock"
    with interprocess_lock(lock_file):
        assert lock_file.exists()


def test_reacquire_after_release_does_not_hang(tmp_path):
    lock_file = tmp_path / "state.lock"
    with interprocess_lock(lock_file):
        pass
    # Если бы lock не освобождался, повторный захват завис бы.
    with interprocess_lock(lock_file):
        assert True


def test_mutual_exclusion_serializes_holders(tmp_path):
    """Два независимых держателя (отдельные fd) не могут владеть locked одновременно.

    flock привязан к open file description, поэтому даже в одном процессе два
    ``os.open`` конкурируют — это и эмулирует двух воркеров.
    """
    lock_file = tmp_path / "state.lock"
    events: list[str] = []
    second_may_start = threading.Event()

    def holder() -> None:
        with interprocess_lock(lock_file):
            events.append("A-in")
            second_may_start.set()
            time.sleep(0.2)
            events.append("A-out")

    def contender() -> None:
        second_may_start.wait()
        # A уже внутри критической секции; этот захват обязан подождать A-out.
        with interprocess_lock(lock_file):
            events.append("B-in")

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=contender)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert events == ["A-in", "A-out", "B-in"]


@pytest.mark.asyncio
async def test_shares_persistence_uses_lock_file(tmp_path):
    """save_file_shares (через _mutate) создаёт lock-файл рядом с JSON."""
    import app.services.files_shares_persistence as mod

    f = tmp_path / "files-shares.json"
    with (
        patch.object(mod, "_SHARES_FILE", f),
        patch.object(mod, "_SETTINGS_DIR", tmp_path),
    ):
        mod._write_lock = None
        await mod.save_file_shares(
            "HR/r.xlsx",
            [
                {
                    "subject_type": "user",
                    "subject_id": "u1",
                    "subject_name": "T",
                    "permission": "viewer",
                    "expires_at": None,
                }
            ],
        )
        mod._write_lock = None
    assert (tmp_path / "files-shares.lock").exists()
    assert f.exists()
