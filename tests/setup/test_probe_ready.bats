#!/usr/bin/env bats
# bats file_tokens=5.4k
#
# bats unit-тесты для probe_ready() из setup.sh — опрос /ready с ретраями.
# Регрессия: одиночный curl с --max-time 5 на холодном старте ложно ругался
# «нет ответа» при рабочем стеке — /ready синхронно опрашивает NC/Keycloak/
# SMTP/Collabora и отвечает дольше 5с (curl рвал соединение → nginx 499).
#
# docker мокается stub'ом в tmp-PATH (как curl в test_update_bundle.bats):
# stub логирует каждую команду, а в stdout отдаёт следующий HTTP-код из
# заранее заготовленной очереди (после исчерпания — последний).

bats_require_minimum_version 1.5.0

SETUP_SH="${BATS_TEST_DIRNAME}/../../setup.sh"

setup() {
    TEST_CWD="$(mktemp -d)"
    cd "$TEST_CWD" || return 1
    STUB_DIR="${TEST_CWD}/stub"
    CODES_FILE="${TEST_CWD}/http-codes"
    CALLS_FILE="${TEST_CWD}/docker-calls"
    mkdir -p "$STUB_DIR"
    : > "$CALLS_FILE"
}

teardown() {
    # shellcheck disable=SC2312
    [[ -n "${TEST_CWD:-}" ]] && rm -rf "$TEST_CWD"
}

load_setup() {
    # shellcheck source=/dev/null
    source "$SETUP_SH"
}

# make_docker_stub — fake-docker в tmp-PATH: логирует вызовы, коды берёт из очереди.
make_docker_stub() {
    cat > "${STUB_DIR}/docker" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "${CALLS_FILE}"
call_no=\$(wc -l < "${CALLS_FILE}")
total=\$(wc -l < "${CODES_FILE}")
(( call_no > total )) && call_no=\$total
sed -n "\${call_no}p" "${CODES_FILE}"
STUB
    chmod +x "${STUB_DIR}/docker"
    export PATH="${STUB_DIR}:${PATH}"
}

calls() { wc -l < "${CALLS_FILE}"; }

# ─── happy path ───────────────────────────────────────────────────────────────

@test "probe_ready: 200 с первой попытки — один вызов docker, без ретраев" {
    load_setup
    printf '200\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 probe_ready portal-nginx-1
    [[ "$(calls)" -eq 1 ]]
    [[ "${output}" == "200" ]]
    # стучимся именно внутрь nginx-контейнера на :8080, а max-time покрывает
    # сумму таймаутов проб /ready (NC 3с + Keycloak/SMTP/Collabora по 5с)
    grep -q -- "--max-time 20" "${CALLS_FILE}"
    grep -q "http://localhost:8080/ready" "${CALLS_FILE}"
}

# ─── ретраи ───────────────────────────────────────────────────────────────────

@test "probe_ready: таймаут (000) на холодном старте — дожидается 200" {
    load_setup
    printf '000\n000\n200\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 probe_ready portal-nginx-1 6 20 0   # pause=0 — тест не спит по 5с
    [[ "$(calls)" -eq 3 ]]
    [[ "${lines[-1]}" == "200" ]]
    # между попытками были прогресс-строки (stderr попадает в output вместе со stdout)
    [[ "${#lines[@]}" -eq 3 ]]
}

@test "probe_ready: 503 тоже ретраится — подсистема может догружаться" {
    load_setup
    printf '503\n200\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 probe_ready portal-nginx-1 6 20 0
    [[ "$(calls)" -eq 2 ]]
    [[ "${lines[-1]}" == "200" ]]
}

@test "probe_ready: все попытки исчерпаны — возвращается код последней (000)" {
    load_setup
    printf '000\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 probe_ready portal-nginx-1 4 20 0
    [[ "$(calls)" -eq 4 ]]
    [[ "${lines[-1]}" == "000" ]]
    # 3 прогресс-строки между 4 попытками + итоговая строка с кодом
    [[ "${#lines[@]}" -eq 4 ]]
}
