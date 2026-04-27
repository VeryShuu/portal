#!/bin/sh
set -e
# Запуск API.
# Миграции применяет отдельный compose-сервис `migrations` (одноразовый init-job),
# чтобы избежать race при `--workers >= 2` и горизонтальном масштабировании.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --limit-concurrency 100
