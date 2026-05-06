#!/usr/bin/env bash
# Flush Nextcloud richdocuments federation cache.
#
# Why this script exists:
#   richdocuments кэширует результат FederationService::getRemoteFileDetails()
#   под ключом md5(remote+remoteToken) в distributed cache (richdocuments_remote/*).
#   Если portal не был добавлен в gs.trustedHosts на момент открытия документа,
#   NC закэширует "remote not trusted" и уже открытые в Collabora сессии будут
#   показывать «Анонимный пользователь» до закрытия документа.
#
#   Новые открытия документов получают свежий initiator-token (новый ключ кэша)
#   и работают сразу. Этот скрипт нужен ровно один раз — после первой настройки
#   gs.trustedHosts, чтобы расцепить уже залипшие сессии.
#
# Usage:
#   ./scripts/flush-nc-richdocuments-cache.sh [nextcloud-service-name]
#
# Default service name is "nextcloud" (имя в docker-compose файле NC).
# Выполняется через `docker compose exec`, поэтому запускать из директории,
# где лежит соответствующий docker-compose.yml (обычно — где живёт NC,
# не обязательно эта же репа).

set -euo pipefail

SERVICE="${1:-nextcloud}"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker не найден в PATH" >&2
    exit 1
fi

if ! docker compose ps --services 2>/dev/null | grep -qx "$SERVICE"; then
    echo "ERROR: сервис '$SERVICE' не найден в docker compose проекта в $(pwd)." >&2
    echo "Запустите скрипт из директории compose-проекта Nextcloud, или передайте имя сервиса:" >&2
    echo "  $0 my-nextcloud-service" >&2
    exit 2
fi

echo "==> Flushing Nextcloud caches via 'occ maintenance:repair' on service '$SERVICE'..."
docker compose exec -T --user www-data "$SERVICE" php occ maintenance:repair

echo
echo "==> Done. Уже открытые в Collabora документы рекомендуется закрыть и переоткрыть,"
echo "    чтобы NC сходил в портал за свежим guestDisplayname."
