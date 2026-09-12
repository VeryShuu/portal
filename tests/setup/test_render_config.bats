#!/usr/bin/env bats
# bats file_tokens=3.9k
#
# bats unit-тесты для nginx/render-config.sh — генерация allowlist.conf
# из allowed_cidr (system.json). Скрипт параметризуется env (SETTINGS_JSON/
# OUT_DIR/CERTS_DIR/TEMPLATES_DIR/RELOAD_TRIGGER), поэтому гоняется в tmp.
#
# Регрессия: лупбэк, прописанный в allowed_cidr как 127.0.0.1/32, не должен
# дублироваться авто-добавляемым 127.0.0.1 → nginx "duplicate network" warning.

# `run -0` требует bats ≥ 1.5.0 (CI ставит 1.14.0).
bats_require_minimum_version 1.5.0

RENDER="${BATS_TEST_DIRNAME}/../../nginx/render-config.sh"
RENDER_TEMPLATES="${BATS_TEST_DIRNAME}/../../nginx/templates"

setup() {
    command -v jq >/dev/null 2>&1 || skip "jq не установлен"
    TEST_CWD="$(mktemp -d)"
    cd "$TEST_CWD" || return 1
    export SETTINGS_JSON="${TEST_CWD}/system.json"
    export OUT_DIR="${TEST_CWD}/out"
    export CERTS_DIR="${TEST_CWD}/certs"        # пустой → http-only режим
    export RELOAD_TRIGGER="${TEST_CWD}/reload-trigger"
    export TEMPLATES_DIR="${RENDER_TEMPLATES}"
    mkdir -p "${OUT_DIR}" "${CERTS_DIR}"
    # envsubst нужен рендеру ssl/learn_server.conf; на минималистичных образах
    # может отсутствовать — подкладываем мини-envsubst (POSIX awk), совместимый
    # с единственной формой из render-config.sh: envsubst '${V1} ${V2}' < file.
    # Passthrough-заглушки недостаточно: CSP/server_name тесты обязаны видеть
    # подставленный рендер, иначе на CI они бессмысленны.
    if ! command -v envsubst >/dev/null 2>&1; then
        mkdir -p "${TEST_CWD}/bin"
        cat > "${TEST_CWD}/bin/envsubst" <<'STUB'
#!/bin/sh
# Минимальный envsubst: только форма с явным списком переменных ('${V1} ${V2}').
# Без аргументов — passthrough (как cat), чтобы не эмулировать full-режим.
exec awk -v vlist="$1" '
function replace_all(s, pat, val,   out, i, j, plen) {
    plen = length(pat); out = ""; i = 1
    while ((j = index(substr(s, i), pat)) > 0) {
        out = out substr(s, i, j - 1) val
        i = i + j - 1 + plen
    }
    return out substr(s, i)
}
BEGIN { k = 0
        if (vlist != "") { n = split(vlist, a, " ")
            for (i = 1; i <= n; i++) {
                nm = a[i]; if (nm == "") continue
                gsub(/^\$\{/, "", nm); gsub(/\}$/, "", nm)
                names[++k] = nm
            } } }
{   line = $0
    for (i = 1; i <= k; i++)
        line = replace_all(line, "${" names[i] "}", ENVIRON[names[i]])
    print line
}'
STUB
        chmod +x "${TEST_CWD}/bin/envsubst"
        export PATH="${TEST_CWD}/bin:${PATH}"
    fi
}

teardown() {
    # shellcheck disable=SC2312
    [[ -n "${TEST_CWD:-}" ]] && rm -rf "$TEST_CWD"
}

# make_settings <allowed_cidr> — пишет system.json с одним полем.
make_settings() {
    jq -n --arg cidr "$1" '{allowed_cidr: $cidr}' > "${SETTINGS_JSON}"
}

# loopback_entries — сколько строк-разрешений для лупбэка в allowlist.conf.
loopback_entries() {
    grep -cE '^ +127\.0\.0\.1(/32)? 1;$' "${OUT_DIR}/allowlist.conf"
}

@test "allowed_cidr с 127.0.0.1/32 — лупбэк не дублируется (регрессия)" {
    make_settings "10.0.0.0/8,172.16.0.0/12,127.0.0.1/32"
    run -0 "${RENDER}"
    [[ "$(loopback_entries)" -eq 1 ]]
    # пользовательская запись /32 сохранена как есть, без переписывания
    grep -q '^    127\.0\.0\.1/32 1;$' "${OUT_DIR}/allowlist.conf"
}

@test "allowed_cidr с 127.0.0.1 (без /32) — автодобавления нет" {
    make_settings "10.0.0.0/8,127.0.0.1"
    run -0 "${RENDER}"
    [[ "$(loopback_entries)" -eq 1 ]]
}

@test "лупбэка нет в allowed_cidr — добавляется автоматически" {
    make_settings "10.0.0.0/8"
    run -0 "${RENDER}"
    [[ "$(loopback_entries)" -eq 1 ]]
    grep -q '^    127\.0\.0\.1 1;$' "${OUT_DIR}/allowlist.conf"
}

@test "render завершается полностью: limits.conf и ssl_server.conf на месте" {
    make_settings "10.0.0.0/8"
    run -0 "${RENDER}"
    [[ -s "${OUT_DIR}/ssl_server.conf" ]]
    [[ -s "${OUT_DIR}/limits.conf" ]]
}

# ── CSP frame-src: доверенные видеохостинги (материалы обучения + rich-контент) ──

@test "CSP портала разрешает frame-src только доверенных видеохостингов" {
    make_settings "10.0.0.0/8"
    run -0 "${RENDER}"
    grep -q "frame-src 'self' https://video.mage.ru https://www.youtube-nocookie.com" \
        "${OUT_DIR}/ssl_server.conf"
    grep -q "https://rutube.ru https://vk.com https://vkvideo.ru https://player.vimeo.com;" \
        "${OUT_DIR}/ssl_server.conf"
    # открытый wildcard не возвращается даже с расширением списка
    ! grep -q "frame-src 'self' https:;" "${OUT_DIR}/ssl_server.conf"
}

@test "CSP learn-контура получает frame-src доверенных видеохостингов (ADR-051)" {
    jq -n '{allowed_cidr: "10.0.0.0/8", learning_base_url: "https://learn.mage.ru"}' > "${SETTINGS_JSON}"
    printf 'crt' > "${CERTS_DIR}/portal.crt"
    printf 'key' > "${CERTS_DIR}/portal.key"
    run -0 "${RENDER}"
    grep -q "server_name learn.mage.ru" "${OUT_DIR}/learn_server.conf"
    grep -q "frame-src 'self' https://video.mage.ru https://www.youtube-nocookie.com" \
        "${OUT_DIR}/learn_server.conf"
    # внешний контент learn-контура — только эти iframe: media-src остаётся закрытым
    ! grep -q "media-src" "${OUT_DIR}/learn_server.conf"
}

@test "learning_base_url с http:// — learn-контур fail-closed disabled (PA-025)" {
    jq -n '{allowed_cidr: "10.0.0.0/8", learning_base_url: "http://learn.mage.ru"}' > "${SETTINGS_JSON}"
    printf 'crt' > "${CERTS_DIR}/portal.crt"
    printf 'key' > "${CERTS_DIR}/portal.key"
    run -0 "${RENDER}"
    ! grep -q "server {" "${OUT_DIR}/learn_server.conf"
    grep -q "ADR-051" "${OUT_DIR}/learn_server.conf"
}

@test "learn-allowlist: learner-пути проксируются, остальной /learning/ — 404 (PA-003)" {
    jq -n '{allowed_cidr: "10.0.0.0/8", learning_base_url: "https://learn.mage.ru"}' > "${SETTINGS_JSON}"
    printf 'crt' > "${CERTS_DIR}/portal.crt"
    printf 'key' > "${CERTS_DIR}/portal.key"
    run -0 "${RENDER}"
    local CONF="${OUT_DIR}/learn_server.conf"
    # learner-подмножество имеет собственные proxy-локации
    grep -q "location = /api/v1/learning/meta" "${CONF}"
    grep -q "location /api/v1/learning/me/" "${CONF}"
    # catchall-блок /api/v1/learning/ отдаёт 404 и НЕ содержит proxy_pass —
    # admin/methodist-роуты не доходят до backend
    grep -q "location /api/v1/learning/ {" "${CONF}"
    run awk '/location \/api\/v1\/learning\/ \{/{f=1} f{print} f&&/^\    \}/{exit}' "${CONF}"
    [[ "$output" != *"proxy_pass"* ]]
}

# ── video_iframe_origins: runtime-настройка (Admin UI → System) ──────────────

@test "frame-src читается из video_iframe_origins (custom список)" {
    jq -n '{allowed_cidr: "10.0.0.0/8", video_iframe_origins: ["https://video.mage.ru", "https://media.corp.local:8443"]}' > "${SETTINGS_JSON}"
    run -0 "${RENDER}"
    grep -q "frame-src 'self' https://video.mage.ru https://media.corp.local:8443;" \
        "${OUT_DIR}/ssl_server.conf"
    # дефолтные origins больше не разрешены — настройка единственный источник
    ! grep -q "rutube.ru" "${OUT_DIR}/ssl_server.conf"
}

@test "video_iframe_origins отсутствует в system.json — fallback на дефолт" {
    make_settings "10.0.0.0/8"
    run -0 "${RENDER}"
    grep -q "https://video.mage.ru https://www.youtube-nocookie.com" \
        "${OUT_DIR}/ssl_server.conf"
}

@test "пустой video_iframe_origins — внешние iframe запрещены" {
    jq -n '{allowed_cidr: "10.0.0.0/8", video_iframe_origins: []}' > "${SETTINGS_JSON}"
    run -0 "${RENDER}"
    grep -q "frame-src 'self';" "${OUT_DIR}/ssl_server.conf"
    ! grep -q "rutube" "${OUT_DIR}/ssl_server.conf"
}
