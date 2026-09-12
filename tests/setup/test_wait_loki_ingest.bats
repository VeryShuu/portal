#!/usr/bin/env bats
# bats file_tokens=5.4k
#
# bats unit-тесты для wait_loki_ingest() из setup.sh — ожидание первых логов
# в Loki после старта monitoring-стека (п.10).
#
# Регрессия: smoke проверял ingestion одномоментно сразу после readiness —
# Alloy отвечает /ready мгновенно, но тащит только НОВЫЕ строки контейнеров,
# а worker пишет раз в ~60с (probe_integrations) → на тихой системе окно
# «5 минут» пустое → ложный LOKI_INGEST:fail и баннер «НЕ ПОЛНОСТЬЮ».
#
# docker мокается stub'ом в tmp-PATH (как в test_probe_ready.bats): stub
# логирует каждый вызов, а exit-код берёт из очереди (0 = «логи есть»,
# 1 = «пусто»). Пауза передаётся 0 — тесты не спят по 10с.

bats_require_minimum_version 1.5.0

SETUP_SH="${BATS_TEST_DIRNAME}/../../setup.sh"

setup() {
    TEST_CWD="$(mktemp -d)"
    cd "$TEST_CWD" || return 1
    STUB_DIR="${TEST_CWD}/stub"
    CODES_FILE="${TEST_CWD}/exit-codes"
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

# make_docker_stub — fake-docker в tmp-PATH: логирует вызовы, exit-код берёт
# из очереди CODES_FILE (после исчерпания — последний).
make_docker_stub() {
    cat > "${STUB_DIR}/docker" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "${CALLS_FILE}"
call_no=\$(wc -l < "${CALLS_FILE}")
total=\$(wc -l < "${CODES_FILE}")
(( call_no > total )) && call_no=\$total
code=\$(sed -n "\${call_no}p" "${CODES_FILE}")
[[ "\$code" == "0" ]] && exit 0
exit 1
STUB
    chmod +x "${STUB_DIR}/docker"
    export PATH="${STUB_DIR}:${PATH}"
}

calls() { wc -l < "${CALLS_FILE}"; }

# ─── happy path ───────────────────────────────────────────────────────────────

@test "wait_loki_ingest: логи есть с первой попытки — один вызов docker, без ретраев" {
    load_setup
    printf '0\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 wait_loki_ingest 4 0
    [[ "$(calls)" -eq 1 ]]
    # запрос идёт в Loki из сети portal_internal с окном «5 минут»
    grep -q -- "--network portal_internal" "${CALLS_FILE}"
    grep -q "count_over_time" "${CALLS_FILE}"
}

# ─── ожидание ─────────────────────────────────────────────────────────────────

@test "wait_loki_ingest: пусто на старте — дожидается появления логов" {
    load_setup
    printf '1\n1\n0\n' > "${CODES_FILE}"
    make_docker_stub
    run -0 wait_loki_ingest 4 0   # pause=0 — тест не спит по 10с
    [[ "$(calls)" -eq 3 ]]
    # 2 прогресс-строки между попытками (stderr попадает в output)
    [[ "${#lines[@]}" -eq 2 ]]
    [[ "${output}" == *"В Loki ещё нет свежих логов"* ]]
}

@test "wait_loki_ingest: логи так и не появились — ненулевой код после всех попыток" {
    load_setup
    printf '1\n' > "${CODES_FILE}"
    make_docker_stub
    run -1 wait_loki_ingest 3 0
    [[ "$(calls)" -eq 3 ]]
    [[ "${#lines[@]}" -eq 2 ]]   # попыток 3, прогресс-строк между ними — 2
}

@test "wait_loki_ingest: дефолты 12×10с (≈2 мин) при вызове без аргументов" {
    load_setup
    printf '1\n' > "${CODES_FILE}"
    make_docker_stub
    run -1 wait_loki_ingest
    [[ "$(calls)" -eq 12 ]]
}
