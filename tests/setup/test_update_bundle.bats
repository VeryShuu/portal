#!/usr/bin/env bats
# bats file_tokens=8.2k
#
# bats unit-тесты для авто-обновления deploy-bundle в setup.sh (ADR-046).
#
# Покрывают: bundle_url, download_bundle (успех/404/пустой/curl-отсутствует),
# apply_bundle (распаковка, .bak, .env не трогается), update_bundle_self (гейты).
#
# Setup.sh теперь source'ится безопасно — main() обёрнут в BASH_SOURCE-guard,
# поэтому импорт функций не запускает интерактивное меню.

# Используем `run -127` (флаг ожидаемого exit-кода) — требует bats ≥ 1.5.0.
# CI ставит bats-core из git (1.14.0), требование выполняется.
bats_require_minimum_version 1.5.0

SETUP_SH="${BATS_TEST_DIRNAME}/../../setup.sh"

# ─── setup/teardown: каждый тест в чистом tmp-CWD ─────────────────────────────
setup() {
    export TEST_CWD
    TEST_CWD="$(mktemp -d)"
    cd "$TEST_CWD" || return 1
}

teardown() {
    # shellcheck disable=SC2312
    [[ -n "${TEST_CWD:-}" ]] && rm -rf "$TEST_CWD"
}

# Загрузить функции setup.sh в текущий shell (без main).
load_setup() {
    # shellcheck source=/dev/null
    source "$SETUP_SH"
}

# ─── bundle_url ───────────────────────────────────────────────────────────────

@test "bundle_url формирует корректный URL для v1.1.0" {
    load_setup
    [[ "$(bundle_url v1.1.0)" == \
       "https://github.com/VeryShuu/portal/releases/download/v1.1.0/portal-deploy-bundle-v1.1.0.tar.gz" ]]
}

@test "bundle_url для rc-тега v1.2.3-rc1" {
    load_setup
    [[ "$(bundle_url v1.2.3-rc1)" == \
       "https://github.com/VeryShuu/portal/releases/download/v1.2.3-rc1/portal-deploy-bundle-v1.2.3-rc1.tar.gz" ]]
}

# ─── download_bundle ──────────────────────────────────────────────────────────
# Мокаем curl через stub в tmp-PATH (download_bundle вызывает curl напрямую).

# Создаёт fake-curl, который пишет заготовленный tarball в файл из -o.
# $1 — путь к «настоящему» tarball, который curl должен отдать.
# download_bundle вызывает: curl -fsSL --retry 3 -o "$tarball" "$url"
# Stub парсит -o <file> и копирует туда заготовку.
make_curl_stub_success() {
    local real_tarball="$1"
    mkdir -p stubbin
    cat > stubbin/curl <<EOF
#!/usr/bin/env bash
# Парсим -o <file>: последний аргумент перед URL.
local out=""
while [[ \$# -gt 0 ]]; do
    case "\$1" in
        -o) out="\$2"; shift 2 ;;
        *)  shift ;;
    esac
done
cp "$real_tarball" "\$out"
exit 0
EOF
    chmod +x stubbin/curl
    export PATH="$TEST_CWD/stubbin:$PATH"
}

# Fake-curl, имитирующий неудачу (HTTP 404 / сетевая ошибка → exit 22 для -f).
make_curl_stub_fail() {
    mkdir -p stubbin
    cat > stubbin/curl <<'EOF'
#!/usr/bin/env bash
echo "curl: (22) The requested URL returned error: 404" >&2
exit 22
EOF
    chmod +x stubbin/curl
    export PATH="$TEST_CWD/stubbin:$PATH"
}

@test "download_bundle возвращает путь и сохраняет tarball при успехе curl" {
    load_setup
    # Готовим минимальный валидный gzip-tarball (содержимое не важно для download).
    local real
    real="$TEST_CWD/fake-bundle.tar.gz"
    mkdir -p portal-deploy && touch portal-deploy/docker-compose.yml
    tar -czf "$real" portal-deploy && rm -rf portal-deploy
    make_curl_stub_success "$real"

    local out
    out=$(download_bundle v1.1.0 "$TEST_CWD/dl")
    [[ "$out" == "$TEST_CWD/dl/portal-deploy-bundle-v1.1.0.tar.gz" ]]
    [[ -s "$out" ]]
}

@test "download_bundle падает (exit ≠0) при ошибке curl (404)" {
    load_setup
    make_curl_stub_fail
    run download_bundle v1.9.9 "$TEST_CWD/dl"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"v1.9.9"* ]]   # сообщение упоминает тег
}

@test "download_bundle падает, когда curl отдал пустой файл" {
    load_setup
    # curl-«успех», но пишет пустой файл в -o <target>.
    mkdir -p stubbin
    cat > stubbin/curl <<'EOF'
#!/usr/bin/env bash
local out=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        *)  shift ;;
    esac
done
: > "$out"
exit 0
EOF
    chmod +x stubbin/curl
    export PATH="$TEST_CWD/stubbin:$PATH"

    run download_bundle v1.1.0 "$TEST_CWD/dl"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"пустой"* ]]
}

@test "download_bundle падает, если curl не установлен" {
    load_setup
    # Override встроенной command через функцию, эмулирующую отсутствие curl.
    # Прямой PATH-обрез не надёжен (curl может лежать в базовых путях).
    command() {
        if [[ "$1" == "-v" && "$2" == "curl" ]]; then
            return 1   # имитируем «curl не найден»
        fi
        builtin command "$@"   # иначе реальная command
    }
    run download_bundle v1.1.0 "$TEST_CWD/dl"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"curl не найден"* ]]
}

# ─── apply_bundle ─────────────────────────────────────────────────────────────
# Готовим tarball со структурой portal-deploy/<files> как делает CI (ci.yml::deploy-bundle).

# Собирает bundle-tarball с реалистичным именем portal-deploy-bundle-<tag>.tar.gz
# (как CI в ci.yml::deploy-bundle). Аргументы: tag, затем пары "путь=содержимое".
# Результат: $TEST_CWD/portal-deploy-bundle-<tag>.tar.gz (как в реальности).
make_bundle_tarball() {
    local tag="$1"; shift
    local bundle_root="$TEST_CWD/_bundle_src/portal-deploy"
    rm -rf "$TEST_CWD/_bundle_src"
    mkdir -p "$bundle_root"
    while [[ $# -gt 0 ]]; do
        local path="${1%%=*}" content="${1#*=}"
        mkdir -p "$bundle_root/$(dirname "$path")"
        printf '%s' "$content" > "$bundle_root/$path"
        shift
    done
    tar -czf "$TEST_CWD/portal-deploy-bundle-${tag}.tar.gz" -C "$TEST_CWD/_bundle_src" portal-deploy
    rm -rf "$TEST_CWD/_bundle_src"
}

@test "apply_bundle копирует docker-compose.yml и setup.sh поверх CWD" {
    load_setup
    make_bundle_tarball v1.1.0 \
        "docker-compose.yml=NEW_COMPOSE" \
        "setup.sh=NEW_SETUP"
    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"

    [[ "$(cat docker-compose.yml)" == "NEW_COMPOSE" ]]
    [[ "$(cat setup.sh)" == "NEW_SETUP" ]]
}

@test "apply_bundle создаёт .bak для изменённых файлов" {
    load_setup
    # Существующий локальный файл.
    printf 'OLD_COMPOSE' > docker-compose.yml
    make_bundle_tarball v1.1.0 "docker-compose.yml=NEW_COMPOSE"

    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"

    [[ "$(cat docker-compose.yml)" == "NEW_COMPOSE" ]]
    [[ -f docker-compose.yml.bak-pre-v1.1.0 ]]
    [[ "$(cat docker-compose.yml.bak-pre-v1.1.0)" == "OLD_COMPOSE" ]]
}

@test "apply_bundle НЕ создаёт .bak, если файл не изменился" {
    load_setup
    printf 'SAME' > docker-compose.yml
    make_bundle_tarball v1.1.0 "docker-compose.yml=SAME"

    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"

    [[ "$(cat docker-compose.yml)" == "SAME" ]]
    [[ ! -e docker-compose.yml.bak-pre-v1.1.0 ]]
}

@test "apply_bundle НЕ трогает существующий .env (не входит в bundle)" {
    load_setup
    printf 'SECRET=do-not-overwrite' > .env
    # Bundle БЕЗ .env (его там и нет по контракту — только .env.example).
    make_bundle_tarball v1.1.0 \
        "docker-compose.yml=x" \
        ".env.example=POSTGRES_DB=portal"
    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"

    # .env сохранён, .env.example обновлён.
    [[ "$(cat .env)" == "SECRET=do-not-overwrite" ]]
    [[ "$(cat .env.example)" == "POSTGRES_DB=portal" ]]
}

@test "apply_bundle копирует monitoring/ директорию целиком" {
    load_setup
    make_bundle_tarball v1.1.0 \
        "monitoring/prometheus.yml=SCRAPE_CONFIG" \
        "monitoring/alertmanager.yml=ALERT_CONFIG"
    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"

    [[ -f monitoring/prometheus.yml ]]
    [[ -f monitoring/alertmanager.yml ]]
    [[ "$(cat monitoring/prometheus.yml)" == "SCRAPE_CONFIG" ]]
}

@test "apply_bundle падает при битом архиве" {
    load_setup
    printf 'not a gzip' > bad.tar.gz
    run apply_bundle "$TEST_CWD/bad.tar.gz"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"распаковать"* ]]
}

@test "apply_bundle падает, если в архиве нет portal-deploy/" {
    load_setup
    # Архив с другой структурой.
    mkdir -p _wrong && touch _wrong/file && tar -czf wrong.tar.gz -C _wrong . && rm -rf _wrong
    run apply_bundle "$TEST_CWD/wrong.tar.gz"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"portal-deploy"* ]]
}

@test "apply_bundle не оставляет tmpdir после успешного выполнения" {
    load_setup
    make_bundle_tarball v1.1.0 "docker-compose.yml=x"
    local tmp_before
    tmp_before=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -type d 2>/dev/null | wc -l)
    apply_bundle "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz" >/dev/null
    local tmp_after
    tmp_after=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -type d 2>/dev/null | wc -l)
    [[ "$tmp_after" -le "$tmp_before" ]]
}

# ─── update_bundle_self ───────────────────────────────────────────────────────

@test "update_bundle_self отказывает при пустом теге" {
    load_setup
    run update_bundle_self ""
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"IMAGE_TAG"* ]]
}

@test "update_bundle_self отказывает при теге latest" {
    load_setup
    run update_bundle_self latest
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"latest"* ]]
}

@test "update_bundle_self: end-to-end (curl-mock → apply → файлы обновлены)" {
    load_setup
    # Bundle как реальный tarball, curl-stub его отдаёт.
    make_bundle_tarball v1.1.0 "docker-compose.yml=E2E_NEW_COMPOSE"
    make_curl_stub_success "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"
    printf 'OLD' > docker-compose.yml

    update_bundle_self v1.1.0

    [[ "$(cat docker-compose.yml)" == "E2E_NEW_COMPOSE" ]]
    [[ -f docker-compose.yml.bak-pre-v1.1.0 ]]
}

@test "update_bundle_self не оставляет tmpdir (cleanup на успехе)" {
    load_setup
    make_bundle_tarball v1.1.0 "docker-compose.yml=x"
    make_curl_stub_success "$TEST_CWD/portal-deploy-bundle-v1.1.0.tar.gz"
    local tmp_before
    tmp_before=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -type d 2>/dev/null | wc -l)
    update_bundle_self v1.1.0 >/dev/null
    local tmp_after
    tmp_after=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -type d 2>/dev/null | wc -l)
    [[ "$tmp_after" -le "$tmp_before" ]]
}

# ─── port_owned_by_self ───────────────────────────────────────────────────────
# Мокаем `docker compose ps` через функцию-обёртку (port_owned_by_self вызывает
# именно `docker compose ps ...`, не bare `docker`).

# Заменяем `docker` на stub, который для `compose ps` отдаёт фиктивные Publishers.
# $1 — строка Publishers (как из реального compose ps --format '{{.Publishers}}').
make_docker_stub() {
    local publishers="$1"
    mkdir -p stubbin
    cat > stubbin/docker <<EOF
#!/usr/bin/env bash
# Только подкоманда `compose ps` возвращает заданные Publishers; остальное — пусто.
if [[ "\$1" == "compose" && "\$2" == "ps" ]]; then
    printf '%s\n' "$publishers"
    exit 0
fi
exit 0
EOF
    chmod +x stubbin/docker
    export PATH="$TEST_CWD/stubbin:$PATH"
}

@test "port_owned_by_self: true, если порт публикуется контейнером проекта" {
    load_setup
    # Publishers nginx: [{0.0.0.0 80 80 tcp} {0.0.0.0 443 443 tcp}] (как в реальности)
    make_docker_stub '[{0.0.0.0 80 80 tcp} {0.0.0.0 443 443 tcp}]'
    run port_owned_by_self 80
    [[ "$status" -eq 0 ]]
    run port_owned_by_self 443
    [[ "$status" -eq 0 ]]
}

@test "port_owned_by_self: false для порта, который никто не публикует" {
    load_setup
    make_docker_stub '[{0.0.0.0 80 80 tcp}]'
    run port_owned_by_self 9999
    [[ "$status" -ne 0 ]]
}

@test "port_owned_by_self: false (не наш), если compose отдаёт чужие порты" {
    load_setup
    # Чужой процесс: порт 80 занят, но НЕ контейнером нашего проекта.
    make_docker_stub '[{0.0.0.0 8080 8080 tcp}]'
    run port_owned_by_self 80
    [[ "$status" -ne 0 ]]
}

@test "port_owned_by_self: false если docker/compose недоступен (тихий fail)" {
    load_setup
    # PATH без docker вообще → функция должна вернуть false (не падать).
    # exit 127 ожидаем (docker не найден) — `run -127` гасит bats-предупреждение BW01.
    run -127 env PATH="/usr/bin:/bin" port_owned_by_self 80
    [[ "$status" -ne 0 ]]
}

@test "port_owned_by_self: корректно парсит IPv6-формат Publishers" {
    load_setup
    # Реальный формат включает IPv6-записи: {:: 80 80 tcp}
    make_docker_stub '[{0.0.0.0 80 80 tcp} {:: 80 80 tcp} {0.0.0.0 443 443 tcp}]'
    run port_owned_by_self 80
    [[ "$status" -eq 0 ]]
}

# ─── set_env_var ──────────────────────────────────────────────────────────────
# Точечная перезапись одной строки в существующем .env (ADR-047 amendment).

@test "set_env_var: заменяет значение существующей строки" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\nSECRET_KEY=abc\n' > .env
    set_env_var IMAGE_TAG v1.2.3
    # Строка обновлена...
    [[ "$(load_env_var IMAGE_TAG)" == "v1.2.3" ]]
    # ...остальные строки не тронуты.
    [[ "$(load_env_var SECRET_KEY)" == "abc" ]]
}

@test "set_env_var: добавляет ключ, если его не было (append)" {
    load_setup
    printf 'SECRET_KEY=abc\n' > .env
    set_env_var IMAGE_TAG v1.2.3
    [[ "$(load_env_var IMAGE_TAG)" == "v1.2.3" ]]
    [[ "$(load_env_var SECRET_KEY)" == "abc" ]]
    # Новый ключ действительно в файле.
    grep -q '^IMAGE_TAG=v1.2.3$' .env
}

@test "set_env_var: создаёт бэкап .env перед правкой" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\n' > .env
    set_env_var IMAGE_TAG v1.2.3
    # Хотя бы один бэкап появился.
    ls .env.backup.* >/dev/null 2>&1
    # В старейшем бэкапе — прежнее значение.
    [[ "$(cat "$(ls .env.backup.* | head -1)")" == *'IMAGE_TAG=v1.0.0'* ]]
}

@test "set_env_var: падает, если .env отсутствует" {
    load_setup
    run set_env_var IMAGE_TAG v1.2.3
    [[ "$status" -ne 0 ]]
}

# ─── fetch_latest_release_tag ─────────────────────────────────────────────────
# Анонимный запрос к GitHub Releases API (репо публичный). curl мокается через stub.

# Stub curl для GitHub API: отдаёт JSON с заданным tag_name.
make_curl_stub_release() {
    local tag="$1"
    mkdir -p stubbin
    cat > stubbin/curl <<EOF
#!/usr/bin/env bash
# Игнорируем аргументы, отдаём фиксированный JSON.
cat <<JSON
{
  "tag_name": "${tag}",
  "name": "Release ${tag}",
  "html_url": "https://github.com/VeryShuu/portal/releases/tag/${tag}"
}
JSON
exit 0
EOF
    chmod +x stubbin/curl
    export PATH="$TEST_CWD/stubbin:$PATH"
}

@test "fetch_latest_release_tag: успех → печатает tag_name из JSON" {
    load_setup
    make_curl_stub_release "v1.2.3"
    [[ "$(fetch_latest_release_tag)" == "v1.2.3" ]]
}

@test "fetch_latest_release_tag: сетевой сбой → пустой вывод + return 1" {
    load_setup
    make_curl_stub_fail
    run fetch_latest_release_tag
    [[ "$status" -ne 0 ]]
    [[ -z "$output" ]]
}

@test "fetch_latest_release_tag: некорректный JSON (нет tag_name) → return 1" {
    load_setup
    mkdir -p stubbin
    cat > stubbin/curl <<'EOF'
#!/usr/bin/env bash
printf '{"name":"no tag here"}\n'
exit 0
EOF
    chmod +x stubbin/curl
    export PATH="$TEST_CWD/stubbin:$PATH"
    run fetch_latest_release_tag
    [[ "$status" -ne 0 ]]
}

# ─── version_gt ───────────────────────────────────────────────────────────────
# Сравнение semver через sort -V (корректно для 1.10 > 1.9).

@test "version_gt: v1.2.3 строго новее v1.2.2" {
    load_setup
    run version_gt v1.2.3 v1.2.2
    [[ "$status" -eq 0 ]]
}

@test "version_gt: v1.10.0 новее v1.9.0 (лексикографическая ловушка)" {
    load_setup
    run version_gt v1.10.0 v1.9.0
    [[ "$status" -eq 0 ]]
    # Обратное направление — false.
    run version_gt v1.9.0 v1.10.0
    [[ "$status" -ne 0 ]]
}

@test "version_gt: равные версии → false (строгое сравнение)" {
    load_setup
    run version_gt v1.2.3 v1.2.3
    [[ "$status" -ne 0 ]]
}

@test "version_gt: работает без ведущего v (1.2.3 vs 1.2)" {
    load_setup
    run version_gt 1.2.3 1.2
    [[ "$status" -eq 0 ]]
}

# ─── check_and_offer_tag_bump ─────────────────────────────────────────────────
# Оркестратор: current_profile + IMAGE_TAG + latest release + read (y/N).
# Мокаем current_profile (через переопределение функции) и read (через подкормку stdin).

@test "check_and_offer_tag_bump: при согласии 'y' — IMAGE_TAG обновлён в .env" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\n' > .env
    make_curl_stub_release "v1.2.3"
    # prod-контур: переопределяем current_profile в текущем shell.
    current_profile() { printf 'prod'; }
    # Ответ 'y' на prompt. Прямой вызов в текущем shell (как в тесте отказа 'N'),
    # чтобы set_env_var правил тот же .env, который проверим ниже.
    printf 'y\n' | check_and_offer_tag_bump >/dev/null 2>&1 || true
    [[ "$(load_env_var IMAGE_TAG)" == "v1.2.3" ]]
}

@test "check_and_offer_tag_bump: при отказе 'N' — IMAGE_TAG НЕ меняется" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\n' > .env
    make_curl_stub_release "v1.2.3"
    current_profile() { printf 'prod'; }
    # Ответ 'N' (отказ).
    printf 'N\n' | check_and_offer_tag_bump >/dev/null 2>&1 || true
    [[ "$(load_env_var IMAGE_TAG)" == "v1.0.0" ]]
}

@test "check_and_offer_tag_bump: dev-контур — no-op (тег не проверяется)" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\n' > .env
    make_curl_stub_release "v1.2.3"
    # dev-контур — функция должна вернуть 0, не дёргая GitHub.
    current_profile() { printf 'dev'; }
    run check_and_offer_tag_bump
    [[ "$status" -eq 0 ]]
    [[ "$(load_env_var IMAGE_TAG)" == "v1.0.0" ]]
}

@test "check_and_offer_tag_bump: текущий тег = latest — пропущен" {
    load_setup
    printf 'IMAGE_TAG=latest\n' > .env
    make_curl_stub_release "v1.2.3"
    current_profile() { printf 'prod'; }
    run check_and_offer_tag_bump
    [[ "$status" -eq 0 ]]
    # latest не должен был замениться.
    [[ "$(load_env_var IMAGE_TAG)" == "latest" ]]
}

@test "check_and_offer_tag_bump: текущий новее release — не понижается" {
    load_setup
    printf 'IMAGE_TAG=v2.0.0\n' > .env
    make_curl_stub_release "v1.2.3"
    current_profile() { printf 'prod'; }
    run check_and_offer_tag_bump
    [[ "$status" -eq 0 ]]
    [[ "$(load_env_var IMAGE_TAG)" == "v2.0.0" ]]
}

@test "check_and_offer_tag_bump: GitHub недоступен — тихий пропуск, тег не тронут" {
    load_setup
    printf 'IMAGE_TAG=v1.0.0\n' > .env
    make_curl_stub_fail
    current_profile() { printf 'prod'; }
    run check_and_offer_tag_bump
    [[ "$status" -eq 0 ]]
    [[ "$(load_env_var IMAGE_TAG)" == "v1.0.0" ]]
}

