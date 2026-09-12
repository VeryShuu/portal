#!/usr/bin/env bats
# bats file_tokens=4.2k
#
# bats unit-тесты для monitoring/node-exporter-textfile/collect.sh (MON-12).
# Скрипт параметризуется env (HOST_ROOT/PORTAL_HOST_PATH/TEXTFILE_DIR),
# поэтому гоняется на tmp-фикстурах без Docker и без реального /var/lib/docker.
#
# Регрессии MON-12:
#   - неверный корень → portal_storage_collector_error{reason="root_missing"} 1
#     и СОХРАНЁННАЯ прошлая свежесть, а не «свежие нули»;
#   - два compose-проекта с одинаковым именем сервиса / две реплики одного
#     сервиса → различные labelset'ы (раньше лейбл был только compose-service,
#     дубли рядов ломали весь textfile-scrape);
#   - нечитаемая существующая папка → read_errors > 0 и last_run не
#     обновляется; пустая папка — легитимный 0.

# `run -0` требует bats ≥ 1.5.0 (CI ставит 1.14.0).
bats_require_minimum_version 1.5.0

COLLECT="${BATS_TEST_DIRNAME}/../../monitoring/node-exporter-textfile/collect.sh"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOST_ROOT="${TEST_DIR}/host"
    export TEXTFILE_DIR="${TEST_DIR}/textfile"
    export PORTAL_HOST_PATH="/home/snow/portal"
    PORTAL="${HOST_ROOT}${PORTAL_HOST_PATH}"
    mkdir -p "${PORTAL}/upload_data/photos/originals" \
             "${PORTAL}/base_data/postgres" \
             "${HOST_ROOT}/var/lib/docker/containers" \
             "${HOST_ROOT}/var/lib/docker/volumes" \
             "${TEXTFILE_DIR}"
    # Детерминированный «размер»: файл в 100 байт в каждой замеряемой папке.
    dd if=/dev/zero of="${PORTAL}/upload_data/photos/originals/f.bin" bs=100 count=1 2>/dev/null
}

teardown() {
    chmod -R u+rwx "${TEST_DIR}" 2>/dev/null || true
    rm -rf "${TEST_DIR}"
}

_add_container() {
    # $1 — уникальный подкаталог контейнера; $2 — Name; $3/$4 — project/service
    # (пустая строка = лейбла нет); $5 — размер json-лога.
    local dir="${HOST_ROOT}/var/lib/docker/containers/$1"
    mkdir -p "$dir"
    printf '{"Name":"/%s","Config":{"Labels":{"com.docker.compose.project":"%s","com.docker.compose.service":"%s"}}}' \
        "$2" "$3" "$4" > "${dir}/config.v2.json"
    head -c "$5" /dev/zero > "${dir}/$1-json.log"
}

_last_run() {
    sed -n 's/^portal_storage_collector_last_run_seconds //p' "${TEXTFILE_DIR}/storage.prom"
}

@test "happy path: folders, container labels (container/project/service), volumes, fresh last_run" {
    dd if=/dev/zero of="${PORTAL}/base_data/postgres/pg.bin" bs=1000 count=1 2>/dev/null
    _add_container "abc123" "portal-backend-1" "portal" "backend" 4096
    mkdir -p "${HOST_ROOT}/var/lib/docker/volumes/portal_loki-data/_data"

    run -0 sh "$COLLECT"
    # du -bs включает apparent-size самой директории (зависит от ФС: ext4/overlayfs),
    # поэтому ожидаемое значение считаем тем же du, а не литералом.
    photos=$(du -bs "${PORTAL}/upload_data/photos/originals" | awk '{print $1}')
    pgdata=$(du -bs "${PORTAL}/base_data/postgres" | awk '{print $1}')
    grep -q 'portal_storage_folder_bytes{folder="upload_data/photos/originals"} '"${photos}" "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_folder_bytes{folder="base_data/postgres"} '"${pgdata}" "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_docker_logs_bytes{container="portal-backend-1",project="portal",service="backend"} 4096' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_docker_volume_bytes{volume="portal_loki-data"}' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_collector_error{reason="root_missing"} 0' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_collector_read_errors 0' "${TEXTFILE_DIR}/storage.prom"
    now=$(date +%s)
    last=$(_last_run)
    [ "${last}" -gt $((now - 60)) ]
}

@test "empty allowed folder is a legitimate zero, not a read error" {
    # photos/thumbs отсутствует (модуль собирается без превью) → 0, ошибки нет.
    run -0 sh "$COLLECT"
    grep -q 'portal_storage_folder_bytes{folder="upload_data/photos/thumbs"} 0' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_collector_read_errors 0' "${TEXTFILE_DIR}/storage.prom"
}

@test "wrong root publishes root_missing error and preserves previous freshness" {
    sh "$COLLECT" >/dev/null 2>&1   # первый успешный прогон фиксирует last_run
    previous=$(_last_run)
    sleep 1
    export PORTAL_HOST_PATH="/home/snow/portal-WRONG"

    run -1 sh "$COLLECT"            # root missing → exit 1, но метрики публикуются
    grep -q 'portal_storage_collector_error{reason="root_missing"} 1' "${TEXTFILE_DIR}/storage.prom"
    [ "$(_last_run)" = "${previous}" ]   # свежесть НЕ подменяется текущим моментом
}

@test "two compose projects with the same service name yield distinct labelsets" {
    _add_container "aaa111" "portal-backend-1" "portal" "backend" 100
    _add_container "bbb222" "staging-backend-1" "staging" "backend" 200

    run -0 sh "$COLLECT"
    grep -q 'container="portal-backend-1",project="portal",service="backend"} 100' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'container="staging-backend-1",project="staging",service="backend"} 200' "${TEXTFILE_DIR}/storage.prom"
    # Все ряды логов уникальны как полные строки (нет дублирующихся labelset'ов).
    ! sort "${TEXTFILE_DIR}/storage.prom" | grep '^portal_storage_docker_logs_bytes' | uniq -d | grep -q .
}

@test "two replicas of one service yield distinct labelsets" {
    _add_container "aaa111" "portal-backend-1" "portal" "backend" 100
    _add_container "ccc333" "portal-backend-2" "portal" "backend" 300

    run -0 sh "$COLLECT"
    grep -q 'container="portal-backend-1",project="portal",service="backend"} 100' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'container="portal-backend-2",project="portal",service="backend"} 300' "${TEXTFILE_DIR}/storage.prom"
}

@test "unreadable existing folder counts a read error and does not refresh last_run" {
    if [ "$(id -u)" = "0" ]; then
        skip "root читает любые папки — сценарий неприменим"
    fi
    sh "$COLLECT" >/dev/null 2>&1
    previous=$(_last_run)
    sleep 1
    mkdir -p "${PORTAL}/upload_data/kb"
    chmod 000 "${PORTAL}/upload_data/kb"

    run -1 sh "$COLLECT"            # частичный отказ → exit 1, метрики публикуются
    grep -q 'portal_storage_collector_read_errors 1' "${TEXTFILE_DIR}/storage.prom"
    grep -q 'portal_storage_folder_bytes{folder="upload_data/kb"} 0' "${TEXTFILE_DIR}/storage.prom"
    [ "$(_last_run)" = "${previous}" ]
}

@test "non-compose container falls back to Name with empty project/service" {
    _add_container "ddd444" "standalone-nginx" "" "" 512

    run -0 sh "$COLLECT"
    grep -q 'container="standalone-nginx",project="",service=""} 512' "${TEXTFILE_DIR}/storage.prom"
}
