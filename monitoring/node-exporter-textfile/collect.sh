#!/bin/sh
# =============================================================================
# storage-collector — сбор размеров папок данных портала, Docker json-file
# логов и named Docker volumes в формате Prometheus textfile.
#
# Запускается по cron (см. crontab) каждые 5 минут. Результат — атомарно в
# /textfile/storage.prom, который скрейпит node-exporter через
# --collector.textfile.directory=/textfile.
#
# Окружение:
#   PORTAL_HOST_PATH — абсолютный путь к корню портала НА ХОСТЕ
#                      (по умолчанию /home/snow/portal). Все пути сбора
#                      пересчитываются относительно /host (rootfs бинд-маунт).
#
# Метрики:
#   portal_storage_folder_bytes{folder="<path>"}      — папки данных портала
#   portal_storage_docker_logs_bytes{service="<name>"} — json-file логи per-container
#   portal_storage_docker_volume_bytes{volume="<name>"} — named Docker volumes
#
# Все размеры — apparent size в байтах (du -bs). Метрики gauge.
# =============================================================================
set -eu

HOST_ROOT="${HOST_ROOT:-/host}"
PORTAL_HOST_PATH="${PORTAL_HOST_PATH:-/home/snow/portal}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/textfile}"
OUT="${TEXTFILE_DIR}/storage.prom.tmp"

mkdir -p "${TEXTFILE_DIR}"

# --- sanitize label value: \\ → \\\\, " → \", newline → \n -------------------
esc() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\n/\\n/g'
}

# du -bs apparent size в байтах; 0 если папки нет (напр. модуль выключен).
dir_bytes() {
    [ -d "$1" ] && du -bs "$1" | awk '{print $1}' || echo 0
}

# Сумма размеров файлов по glob; 0 если glob пуст.
glob_bytes() {
    total=0
    for f in $1; do
        [ -f "$f" ] || continue
        sz=$(stat -c '%s' "$f" 2>/dev/null || echo 0)
        total=$((total + sz))
    done
    echo "$total"
}

{
    echo "# HELP portal_storage_folder_bytes Apparent size of portal data folders on host (bytes)."
    echo "# TYPE portal_storage_folder_bytes gauge"

    PORTAL="${HOST_ROOT}${PORTAL_HOST_PATH}"

    # upload_data/* — пользовательский контент (фото, KB, feedback, helpdesk ...)
    for sub in \
        upload_data/photos/originals \
        upload_data/photos/thumbs \
        upload_data/photos/zips \
        upload_data/kb \
        upload_data/feedback \
        upload_data/helpdesk \
        upload_data/avatars \
        upload_data/news_media \
        upload_data/branding \
        upload_data/link_icons \
        upload_data/file-icons; do
        label=$(esc "$sub")
        bytes=$(dir_bytes "${PORTAL}/${sub}")
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$bytes"
    done

    # base_data/* — данные инфра-сервисов (PG data dir, Redis AOF/RDB)
    for sub in base_data/postgres base_data/redis; do
        label=$(esc "$sub")
        bytes=$(dir_bytes "${PORTAL}/${sub}")
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$bytes"
    done

    # system_data/* — runtime-настройки/секреты/certs/nginx-conf (обычно мало)
    for sub in system_data/settings system_data/secrets system_data/certs system_data/nginx; do
        label=$(esc "$sub")
        bytes=$(dir_bytes "${PORTAL}/${sub}")
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$bytes"
    done

    echo
    echo "# HELP portal_storage_docker_logs_bytes Size of Docker json-file logs per container on host (bytes)."
    echo "# TYPE portal_storage_docker_logs_bytes gauge"

    # /var/lib/docker/containers/<id>/{<id>-json.log, <id>-json.log.*}
    # Имя контейнера — из config.v2.json::Name (с ведущим '/'), напр. /portal-postgres-1.
    # Для compose-проектов в .Config.Labels лежит реальное имя сервиса:
    #   com.docker.compose.service → "postgres", "backend", ...
    # Приоритет: compose-service (осмысленное имя) → .Name (имя контейнера).
    CONTAINERS="${HOST_ROOT}/var/lib/docker/containers"
    if [ -d "${CONTAINERS}" ]; then
        for cdir in "${CONTAINERS}"/*/; do
            [ -d "$cdir" ] || continue
            cfg="${cdir}config.v2.json"
            [ -f "$cfg" ] || continue
            if command -v jq >/dev/null 2>&1; then
                # compose-service — осмысленное имя; фолбэк на имя контейнера.
                name=$(jq -r \
                    '.Config.Labels["com.docker.compose.service"] // (.Name | ltrimstr("/")) // empty' \
                    "$cfg" 2>/dev/null)
            else
                name=$(grep -oE '"com.docker.compose.service"[[:space:]]*:[[:space:]]*"[^"]+"' "$cfg" \
                    | head -1 | sed -E 's#.*:"([^"]+)"$#\1#')
                [ -n "$name" ] || name=$(grep -oE '"Name"[[:space:]]*:[[:space:]]*"[^"]+"' "$cfg" \
                    | head -1 | sed -E 's#.*"([^"]+)"$#\1#' | sed 's#^/##')
            fi
            [ -n "$name" ] || name="unknown"
            label=$(esc "$name")
            bytes=$(glob_bytes "${cdir}*-json.log*")
            printf 'portal_storage_docker_logs_bytes{container="%s"} %s\n' "$label" "$bytes"
        done
    fi

    echo
    echo "# HELP portal_storage_docker_volume_bytes Apparent size of named Docker volumes on host (bytes)."
    echo "# TYPE portal_storage_docker_volume_bytes gauge"

    # Named volumes: /var/lib/docker/volumes/<name>/_data
    # Анонимные volume'ы (build-cache и т.п.) имеют хэш-имена (64 hex-символа)
    # и плодят cardinality — пропускаем их, оставляя только осмысленные имена.
    VOLROOT="${HOST_ROOT}/var/lib/docker/volumes"
    if [ -d "${VOLROOT}" ]; then
        for vdir in "${VOLROOT}"/*/; do
            [ -d "$vdir" ] || continue
            volname=$(basename "$vdir")
            # Пропуск анонимных хэш-volume'ов (64 hex-символа) и metadata-директорий.
            case "$volname" in
                metadata | backingFsBlockDev) continue ;;
            esac
            if printf '%s' "$volname" | grep -qE '^[0-9a-f]{64}$'; then
                continue
            fi
            data="${vdir}_data"
            [ -d "$data" ] || continue
            label=$(esc "$volname")
            bytes=$(dir_bytes "$data")
            printf 'portal_storage_docker_volume_bytes{volume="%s"} %s\n' "$label" "$bytes"
        done
    fi
} > "${OUT}"

# Атомарная замена — node-exporter не увидит недописанный файл.
mv "${OUT}" "${TEXTFILE_DIR}/storage.prom"
