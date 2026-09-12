#!/bin/sh
set -e

# This image runs as the unprivileged ``portal`` user. Bind-mount ownership is
# prepared before startup by ``data-permissions-init`` (Compose).

# Prometheus multiprocess: снести per-pid mmap-файлы от предыдущего запуска
# контейнера. docker restart сохраняет writable layer — без чистки файлы
# мёртвых воркеров продолжали бы вносить вклад в агрегаты MultiProcessCollector.
# mkdir именно здесь (не в Dockerfile): каталог должен принадлежать
# непривилегированному portal, а build-слой создаёт его от root →
# PermissionError при mmap-записи (поймано compose-smoke CI).
if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
    mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
    rm -f "${PROMETHEUS_MULTIPROC_DIR}"/*.db
fi

exec "$@"
