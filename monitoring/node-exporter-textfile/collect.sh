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
#   portal_storage_docker_logs_bytes{container="<name>",project="<p>",service="<s>"}
#                                       — json-file логи per-container.
#                                       container — УНИКАЛЬНОЕ имя контейнера
#                                       (включает проект и номер реплики);
#                                       project/service — compose-лейблы для
#                                       агрегации (пустые у не-compose
#                                       контейнеров отбрасываются Prometheus).
#                                       Мониторинг двух compose-проектов или
#                                       двух реплик одного сервиса даёт
#                                       РАЗЛИЧНЫЕ labelset'ы, а не дубли
#                                       рядов (MON-12; раньше лейбл был только
#                                       compose-service — дубли ломали scrape).
#   portal_storage_docker_volume_bytes{volume="<name>"} — named Docker volumes
#   portal_storage_collector_error{reason="root_missing"} — 1, если корень
#                                       PORTAL_HOST_PATH не найден (опечатка
#                                       в .env / нет бинд-маунта). Неверный
#                                       корень НЕ равен «пустым папкам» —
#                                       без этой метрики сбой выглядел бы
#                                       как вечно свежие нули (MON-12).
#   portal_storage_collector_read_errors  — число сущестующих, но нечитаемых
#                                       путей (права). Пустая папка —
#                                       легитимный 0, ошибка чтения — нет.
#   portal_storage_collector_last_run_seconds          — freshness: unix-time
#                              последнего УСПЕШНОГО прогона (основа алерта
#                              PortalStorageCollectorStale). При ошибке
#                              (root_missing / read_errors > 0) НЕ
#                              обновляется — ошибка не подменяет успех,
#                              stale-алерт честно срабатывает.
#
# Все размеры — apparent size в байтах (du -bs). Метрики gauge. Публикация
# атомарная (mv поверх storage.prom). Это падение du на существующей папке
# считается ошибкой, а не нулём.
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

# Последний успешный прогон из существующего storage.prom. Вызывать В
# ТЕКУЩЕМ шелле (не в $()) — при ошибке текущего прогона это значение
# сохраняется в новый файл, чтобы stale-алерт видел реальный возраст.
prev_last_run() {
    if [ -f "${TEXTFILE_DIR}/storage.prom" ]; then
        sed -n 's/^portal_storage_collector_last_run_seconds \([0-9][0-9]*\)$/\1/p' \
            "${TEXTFILE_DIR}/storage.prom" | tail -n 1
    fi
}

# Глобальные счётчики ошибок текущего прогона (см. шапку).
READ_ERRORS=0

# du -bs apparent size в байтах для СУЩЕСТВУЮЩЕГО пути; отсутствие папки —
# легитимный 0 (модуль выключен), ошибка чтения существующего (права/ENOSPC)
# — инкремент READ_ERRORS. ВАЖНО: du на нечитаемой папке может ещё и
# частичный размер напечатать (stat по родителю работает) — поэтому решение
# по КОДУ ВОЗВРАТА, не по пустоте вывода. Пишет результат в глобальную
# RESULT_DIR_BYTES: command substitution создал бы subshell, и ERRORS из
# него не вернулся бы.
dir_bytes() {
    RESULT_DIR_BYTES=0
    if [ ! -e "$1" ]; then
        return 0
    fi
    if out=$(du -bs "$1" 2>/dev/null); then
        # set -- $out — разбор "N	path" без пайпа (busybox sh без pipefail).
        set -- $out
        RESULT_DIR_BYTES="$1"
    else
        READ_ERRORS=$((READ_ERRORS + 1))
    fi
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

PORTAL="${HOST_ROOT}${PORTAL_HOST_PATH}"

# --- Неверный корень — ошибка, а не «свежие нули» (MON-12) -------------------
if [ ! -d "${PORTAL}" ]; then
    LAST_OK=$(prev_last_run)
    [ -n "$LAST_OK" ] || LAST_OK=0
    {
        echo "# HELP portal_storage_collector_error Storage-collector fatal error of the last run."
        echo "# TYPE portal_storage_collector_error gauge"
        printf 'portal_storage_collector_error{reason="root_missing"} 1\n'
        echo
        echo "# HELP portal_storage_collector_last_run_seconds Unix timestamp of the last SUCCESSFUL storage-collector run (freshness)."
        echo "# TYPE portal_storage_collector_last_run_seconds gauge"
        printf 'portal_storage_collector_last_run_seconds %s\n' "$LAST_OK"
    } > "${OUT}"
    mv "${OUT}" "${TEXTFILE_DIR}/storage.prom"
    echo "storage-collector: root_missing: ${PORTAL} не найден (проверить PORTAL_HOST_PATH и бинд-маунт /host)" >&2
    exit 1
fi

{
    echo "# HELP portal_storage_folder_bytes Apparent size of portal data folders on host (bytes)."
    echo "# TYPE portal_storage_folder_bytes gauge"

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
        dir_bytes "${PORTAL}/${sub}"
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$RESULT_DIR_BYTES"
    done

    # base_data/* — данные инфра-сервисов (PG data dir, Redis AOF/RDB)
    for sub in base_data/postgres base_data/redis; do
        label=$(esc "$sub")
        dir_bytes "${PORTAL}/${sub}"
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$RESULT_DIR_BYTES"
    done

    # system_data/* — runtime-настройки/секреты/certs/nginx-conf (обычно мало)
    for sub in system_data/settings system_data/secrets system_data/certs system_data/nginx; do
        label=$(esc "$sub")
        dir_bytes "${PORTAL}/${sub}"
        printf 'portal_storage_folder_bytes{folder="%s"} %s\n' "$label" "$RESULT_DIR_BYTES"
    done

    echo
    echo "# HELP portal_storage_docker_logs_bytes Size of Docker json-file logs per container on host (bytes)."
    echo "# TYPE portal_storage_docker_logs_bytes gauge"

    # /var/lib/docker/containers/<id>/{<id>-json.log, <id>-json.log.*}
    # Лейблы (MON-12): container — УНИКАЛЬНОЕ имя контейнера (daemon не даёт
    # дубликатов; включает compose-проект и индекс реплики), project/service —
    # compose-лейблы com.docker.compose.project / .service для агрегации.
    # Два проекта с одинаковым именем сервиса или две реплики одного сервиса
    # дают различные labelset'ы — дубли рядов ломали бы весь textfile-scrape.
    CONTAINERS="${HOST_ROOT}/var/lib/docker/containers"
    if [ -d "${CONTAINERS}" ]; then
        for cdir in "${CONTAINERS}"/*/; do
            [ -d "$cdir" ] || continue
            cfg="${cdir}config.v2.json"
            [ -f "$cfg" ] || continue
            if command -v jq >/dev/null 2>&1; then
                cname=$(jq -r '(.Name | ltrimstr("/")) // empty' "$cfg" 2>/dev/null)
                project=$(jq -r '.Config.Labels["com.docker.compose.project"] // ""' "$cfg" 2>/dev/null)
                service=$(jq -r '.Config.Labels["com.docker.compose.service"] // ""' "$cfg" 2>/dev/null)
            else
                cname=$(grep -oE '"Name"[[:space:]]*:[[:space:]]*"[^"]+"' "$cfg" \
                    | head -1 | sed -E 's#.*"([^"]+)"$#\1#' | sed 's#^/##')
                project=$(grep -oE '"com\.docker\.compose\.project"[[:space:]]*:[[:space:]]*"[^"]+"' "$cfg" \
                    | head -1 | sed -E 's#.*:"([^"]+)"$#\1#')
                service=$(grep -oE '"com\.docker\.compose\.service"[[:space:]]*:[[:space:]]*"[^"]+"' "$cfg" \
                    | head -1 | sed -E 's#.*:"([^"]+)"$#\1#')
            fi
            [ -n "$cname" ] || cname="unknown"
            label=$(esc "$cname")
            printf 'portal_storage_docker_logs_bytes{container="%s",project="%s",service="%s"} %s\n' \
                "$label" "$(esc "${project:-}")" "$(esc "${service:-}")" "$(glob_bytes "${cdir}*-json.log*")"
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
            dir_bytes "$data"
            printf 'portal_storage_docker_volume_bytes{volume="%s"} %s\n' "$label" "$RESULT_DIR_BYTES"
        done
    fi

    echo
    echo "# HELP portal_storage_collector_error Storage-collector fatal error of the last run."
    echo "# TYPE portal_storage_collector_error gauge"
    printf 'portal_storage_collector_error{reason="root_missing"} 0\n'
    echo "# HELP portal_storage_collector_read_errors Number of existing but unreadable paths in the last run."
    echo "# TYPE portal_storage_collector_read_errors gauge"
    printf 'portal_storage_collector_read_errors %s\n' "$READ_ERRORS"

    # Freshness-метрика пишется ПОСЛЕДНЕЙ — момент, когда все замеры выше
    # завершены (все метрики одного прогона консистентны по времени).
    # При частичных ошибках чтения (READ_ERRORS > 0) прогон НЕ считается
    # успешным: last_run сохраняет предыдущее значение, и
    # PortalStorageCollectorStale честно подсвечивает деградацию.
    echo
    echo "# HELP portal_storage_collector_last_run_seconds Unix timestamp of the last SUCCESSFUL storage-collector run (freshness)."
    echo "# TYPE portal_storage_collector_last_run_seconds gauge"
    if [ "$READ_ERRORS" -gt 0 ]; then
        LAST_OK=$(prev_last_run)
        [ -n "$LAST_OK" ] || LAST_OK=0
        printf 'portal_storage_collector_last_run_seconds %s\n' "$LAST_OK"
    else
        printf 'portal_storage_collector_last_run_seconds %s\n' "$(date +%s)"
    fi
} > "${OUT}"

# Атомарная замена — node-exporter не увидит недописанный файл.
# (Выполняется и при частичных ошибках: метрики read_errors/сохранённая
# свежесть должны попасть в экспозицию до того, как cron сообщит об отказе.)
mv "${OUT}" "${TEXTFILE_DIR}/storage.prom"

if [ "$READ_ERRORS" -gt 0 ]; then
    echo "storage-collector: ${READ_ERRORS} нечитаемых путей — см. portal_storage_collector_read_errors" >&2
    exit 1
fi
