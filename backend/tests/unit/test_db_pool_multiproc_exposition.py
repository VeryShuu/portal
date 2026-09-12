"""MON-09 / AT-09: per-process DB-pool series in real multiprocess exposition.

Два дочерних процесса пишут pool-гаuges в общий ``PROMETHEUS_MULTIPROC_DIR``;
родитель собирает экспозицию через ``MultiProcessCollector``. Доказывается:

- насыщение одного воркера и свободный пул второго видны ОДНОВРЕМЕННО, хотя
  ни один процесс не «обслуживал scrape» (суть MON-09: mostrecent показывал
  только состояние одного случайного процесса);
- смерть процесса убирает его ряды из liveall-экспозиции.

Дочерние процессы — ``subprocess`` (свежие интерпретаторы), чтобы не
переключать реестр родителя в multiproc-режим: ``PROMETHEUS_MULTIPROC_DIR``
читается при импорте prometheus_client, поэтому env выставляется только в env
дочернего процесса, не в родителе.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_CHILD = r"""
import os, signal, sys, time

multiproc_dir, backend_root, in_use, idle = (
    sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
)
os.environ["PROMETHEUS_MULTIPROC_DIR"] = multiproc_dir
sys.path.insert(0, backend_root)

from app.core import metrics  # noqa: E402 — env обязан быть выставлен ДО импорта
from prometheus_client.multiprocess import mark_process_dead  # noqa: E402

metrics.db_pool_limit.set(10.0)
metrics.db_pool_size.labels(state="in_use").set(in_use)
metrics.db_pool_size.labels(state="idle").set(idle)
metrics.db_pool_update_timestamp.set(time.time())


def _on_term(signum, frame):
    # Тот же путь очистки, что в app/core/lifespan.py при graceful-рестарте
    # uvicorn-воркера: liveall-ряды процесса удаляются из экспозиции.
    mark_process_dead(os.getpid(), multiproc_dir)
    os._exit(0)


signal.signal(signal.SIGTERM, _on_term)
print("ready", flush=True)
time.sleep(120)
"""


def _collect(multiproc_dir: Path) -> dict[str, list[tuple[dict[str, str], float]]]:
    """Собрать экспозицию как это делает /metrics scrape (merge per-pid файлов)."""
    from prometheus_client import CollectorRegistry, generate_latest
    from prometheus_client.multiprocess import MultiProcessCollector

    registry = CollectorRegistry()
    MultiProcessCollector(registry, path=str(multiproc_dir))
    families: dict[str, list[tuple[dict[str, str], float]]] = {}
    for line in generate_latest(registry).decode().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, _, value = line.rpartition(" ")
        labels: dict[str, str] = {}
        header, _, label_part = name.partition("{")
        if label_part:
            label_part = label_part.rstrip("}")
            for pair in _split_labels(label_part):
                k, _, v = pair.partition("=")
                labels[k.strip()] = v.strip().strip('"')
        families.setdefault(header, []).append((labels, float(value)))
    return families


def _split_labels(label_part: str) -> list[str]:
    out, buf, in_quotes = [], "", False
    for ch in label_part:
        if ch == '"':
            in_quotes = not in_quotes
            buf += ch
        elif ch == "," and not in_quotes:
            out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def _pids(samples: list[tuple[dict[str, str], float]]) -> set[str]:
    return {labels["pid"] for labels, _ in samples}


def test_two_process_pool_state_visible_without_scrape(tmp_path: Path):
    """AT-09: пул каждого из двух процессов виден; смерть процесса чистит ряды."""
    backend_root = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}

    def _spawn(in_use: int, idle: int) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path), backend_root, str(in_use), str(idle)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    proc_saturated = _spawn(in_use=9, idle=1)  # насыщен: 9/10 = 0.9 > 0.8
    proc_idle = _spawn(in_use=1, idle=9)  # свободен: 0.1
    try:
        # Дети готовы, когда записали свои значения и напечатали "ready".
        for proc in (proc_saturated, proc_idle):
            line = proc.stdout.readline() if proc.stdout else ""
            assert line.strip() == "ready", (
                f"child failed: {proc.stderr.read() if proc.stderr else ''}"
            )

        fam = _collect(tmp_path)

        in_use = fam["portal_db_pool_size"]
        in_use_samples = [(lb, v) for lb, v in in_use if lb.get("state") == "in_use"]
        # Оба процесса видны одновременно — независимо от «обслужившего scrape».
        assert {v for _, v in in_use_samples} == {9.0, 1.0}
        assert len(_pids(in_use_samples)) == 2
        assert {v for _, v in fam["portal_db_pool_limit"]} == {10.0}
        # Порог алерта PortalDBPoolHigh по насыщенному ряду, свободный молчит.
        limits = {lb["pid"]: v for lb, v in fam["portal_db_pool_limit"]}
        ratios = {
            lb["pid"]: v / limits[lb["pid"]] for lb, v in in_use_samples if lb["pid"] in limits
        }
        assert any(r > 0.8 for r in ratios.values())
        assert any(r <= 0.8 for r in ratios.values())
        assert (
            len(_pids([(lb, v) for lb, v in fam["portal_db_pool_update_timestamp_seconds"]])) == 2
        )

        # Смерть процесса: SIGTERM → graceful-обработчик вызывает
        # mark_process_dead (как lifespan при остановке uvicorn-воркера) →
        # liveall-ряды процесса исчезают из экспозиции.
        saturated_pid = proc_saturated.pid
        proc_saturated.terminate()
        proc_saturated.wait(timeout=15)

        fam_after = _collect(tmp_path)
        alive_pids = _pids(
            [(lb, v) for lb, v in fam_after["portal_db_pool_size"] if lb.get("state") == "in_use"]
        )
        assert str(saturated_pid) not in alive_pids
        assert proc_idle.pid in {int(p) for p in alive_pids}
    finally:
        for proc in (proc_saturated, proc_idle):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=15)
