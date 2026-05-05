#!/usr/bin/env bash
set -euo pipefail

# ─── Цвета ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
err()  { echo -e "  ${RED}✗${RESET}  $*"; exit 1; }
sep()  { echo -e "  ${DIM}────────────────────────────────────────────${RESET}"; }
h2()   { echo; echo -e "  ${BOLD}$*${RESET}"; sep; }

# ─── Файл с запомненным режимом ────────────────────────────────────────────────
MODE_FILE=".portal-mode"

current_mode_label() {
    if [[ -f "$MODE_FILE" ]]; then
        case "$(cat "$MODE_FILE")" in
            prod)    echo -e "${GREEN}Production${RESET}" ;;
            staging) echo -e "${YELLOW}Разработка / Стейджинг${RESET}" ;;
            *)       echo "не задан" ;;
        esac
    else
        echo -e "${DIM}не задан${RESET}"
    fi
}

# ─── Главный экран ─────────────────────────────────────────────────────────────
show_menu() {
    clear
    echo
    echo -e "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}║       Portal — управление развёртыванием     ║${RESET}"
    echo -e "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}"
    echo
    echo -e "  ${BOLD}1.${RESET}  ${GREEN}Production${RESET}"
    echo -e "  ${DIM}     Сборка образов и запуск. Nginx слушает порты из .env (80/443 по умолчанию).${RESET}"
    echo
    echo -e "  ${BOLD}2.${RESET}  ${YELLOW}Разработка / Стейджинг${RESET}"
    echo -e "  ${DIM}     Staging override: PostgreSQL/Redis доступны снаружи (5432/6379),${RESET}"
    echo -e "  ${DIM}     backend открыт на :8000, nginx на 8080/8443, логи уровня DEBUG.${RESET}"
    echo
    echo -e "  ${BOLD}3.${RESET}  Полная пересборка ${DIM}(--no-cache)${RESET} и запуск текущего режима"
    echo -e "  ${DIM}     Нужна когда изменились Dockerfile или зависимости.${RESET}"
    echo -e "  ${DIM}     Текущий режим: $(current_mode_label).${RESET}"
    echo
    sep
    echo
    echo -e "  ${BOLD}4.${RESET}  Настроить / пересоздать .env"
    echo -e "  ${DIM}     Изменить пароли, порты, учётную запись администратора.${RESET}"
    echo
    echo -e "  ${BOLD}0.${RESET}  Выход"
    echo
    read -r -p "  Выберите [0-4]: " MENU_CHOICE
    echo
}

# ─── Вспомогательные функции ввода ─────────────────────────────────────────────
ask() {
    local prompt="$1" default="${2:-}" var
    if [[ -n "$default" ]]; then
        read -r -p "    ${prompt} [${default}]: " var
        echo "${var:-$default}"
    else
        read -r -p "    ${prompt}: " var
        echo "$var"
    fi
}

ask_secret() {
    local prompt="$1" var confirm
    while true; do
        read -r -s -p "    ${prompt}: " var
        echo >&2
        if [[ -z "$var" ]]; then
            warn "Значение не может быть пустым."
            continue
        fi
        if [[ "$var" == *"'"* ]]; then
            warn "Пароль не должен содержать символ ' (одинарная кавычка) — используйте другой символ."
            continue
        fi
        read -r -s -p "    Повторите для подтверждения: " confirm
        echo >&2
        if [[ "$var" == "$confirm" ]]; then
            break
        fi
        warn "Значения не совпадают, попробуйте снова."
    done
    printf '%s' "$var"
}

gen_secret() {
    if command -v openssl &>/dev/null; then
        openssl rand -hex 32
    else
        python3 -c "import secrets; print(secrets.token_hex(32))"
    fi
}

gen_or_ask() {
    local prompt="$1" generated var
    generated=$(gen_secret)
    echo -e "  ${DIM}Нажмите Enter для автогенерации безопасного пароля (рекомендуется).${RESET}" >&2
    read -r -s -p "    ${prompt} (Enter = автогенерация): " var
    echo >&2
    if [[ -z "$var" ]]; then
        ok "Пароль сгенерирован автоматически." >&2
        printf '%s' "$generated"
    else
        printf '%s' "$var"
    fi
}

# ─── Настройка .env ────────────────────────────────────────────────────────────
setup_env() {
    echo
    echo -e "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}║            Настройка файла .env              ║${RESET}"
    echo -e "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}"

    if [[ -f .env ]]; then
        echo
        warn "Файл .env уже существует."
        read -r -p "  Перезаписать? Старый файл будет сохранён как .env.backup (y/N): " ow
        if [[ "${ow,,}" != "y" ]]; then
            ok "Используется существующий .env."
            return 0
        fi
        cp .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
        ok "Резервная копия сохранена."
    fi

    # ── PostgreSQL ──────────────────────────────────────────────────────────────
    h2 "PostgreSQL — база данных"
    echo -e "  ${DIM}Имя базы и пользователя обычно оставляют по умолчанию (portal/portal).${RESET}"
    echo -e "  ${DIM}Пароль защищает порт БД, который не выставлен наружу в режиме Production.${RESET}"
    echo
    POSTGRES_DB=$(ask   "Имя базы данных       POSTGRES_DB"   "portal")
    POSTGRES_USER=$(ask "Пользователь БД       POSTGRES_USER" "portal")
    echo
    echo -e "  ${DIM}Пароль используется только внутри Docker-сети. Запоминать не нужно.${RESET}"
    POSTGRES_PASSWORD=$(gen_or_ask "Пароль БД             POSTGRES_PASSWORD")

    # ── Redis ───────────────────────────────────────────────────────────────────
    h2 "Redis — кэш и очереди"
    echo -e "  ${DIM}Redis хранит сессии пользователей, очереди задач и кэш API.${RESET}"
    echo -e "  ${DIM}Пароль используется только внутри Docker-сети. Запоминать не нужно.${RESET}"
    echo
    REDIS_PASSWORD=$(gen_or_ask "Пароль Redis          REDIS_PASSWORD")

    # ── SECRET_KEY ──────────────────────────────────────────────────────────────
    h2 "SECRET_KEY — ключ подписи сессий"
    echo -e "  ${DIM}Используется для криптографической подписи сессионных токенов.${RESET}"
    echo -e "  ${DIM}Если этот ключ утечёт — все активные сессии станут невалидны.${RESET}"
    echo -e "  ${DIM}Минимум 32 символа. Нажмите Enter чтобы сгенерировать автоматически.${RESET}"
    echo
    read -r -s -p "    SECRET_KEY (Enter = автогенерация): " SECRET_KEY
    echo
    if [[ -z "$SECRET_KEY" ]]; then
        SECRET_KEY=$(gen_secret)
        ok "SECRET_KEY сгенерирован автоматически."
    fi

    # ── LOCAL_AUTH ──────────────────────────────────────────────────────────────
    h2 "Локальная аутентификация"
    echo -e "  ${DIM}Вход по email и паролю — без Keycloak. Необходим для первого запуска${RESET}"
    echo -e "  ${DIM}и аварийного доступа если Keycloak временно недоступен.${RESET}"
    echo -e "  ${DIM}После настройки Keycloak через Admin UI можно отключить.${RESET}"
    echo
    read -r -p "  Включить локальную аутентификацию? LOCAL_AUTH_ENABLED (Y/n): " la
    [[ "${la,,}" == "n" ]] && LOCAL_AUTH_ENABLED=false || LOCAL_AUTH_ENABLED=true

    # ── Admin ───────────────────────────────────────────────────────────────────
    h2 "Учётная запись администратора"
    echo -e "  ${DIM}Создаётся автоматически при первом старте если в базе нет ни одного admin.${RESET}"
    echo -e "  ${DIM}Используется для входа до настройки Keycloak. Смените пароль сразу!${RESET}"
    echo
    ADMIN_EMAIL=$(ask "Email администратора  ADMIN_EMAIL" "admin@company.local")
    echo
    echo -e "  ${DIM}Пароль должен быть надёжным — это ваша главная точка доступа до SSO.${RESET}"
    ADMIN_PASSWORD=$(ask_secret "Пароль               ADMIN_PASSWORD")

    # ── Порты Nginx ─────────────────────────────────────────────────────────────
    h2 "Порты Nginx"
    echo -e "  ${DIM}На каких портах хоста будет доступен портал.${RESET}"
    echo -e "  ${DIM}Если 80/443 уже заняты другим сервисом — укажите другие (например 8080/8443).${RESET}"
    echo
    HTTP_PORT=$(ask  "HTTP порт             HTTP_PORT"  "80")
    HTTPS_PORT=$(ask "HTTPS порт            HTTPS_PORT" "443")

    # ── Запись .env ─────────────────────────────────────────────────────────────
    echo
    cat > .env << EOF
# ============================================================
# Portal — переменные окружения
# Создано setup.sh $(date '+%Y-%m-%d %H:%M:%S')
#
# Все остальные настройки (Keycloak, SMTP, TLS, Nginx, лимиты)
# задаются через Admin UI → Администрирование после запуска.
# ============================================================

# === PostgreSQL ===
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD='${POSTGRES_PASSWORD}'

# === Redis ===
REDIS_PASSWORD='${REDIS_PASSWORD}'

# === Backend ===
SECRET_KEY='${SECRET_KEY}'
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# === Nginx ports ===
HTTP_PORT=${HTTP_PORT}
HTTPS_PORT=${HTTPS_PORT}

# === Локальная аутентификация / Bootstrap ===
LOCAL_AUTH_ENABLED=${LOCAL_AUTH_ENABLED}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD='${ADMIN_PASSWORD}'
ADMIN_PASSWORD_RESET_ON_START=false

# === Отладка (только для разработки) ===
DB_ECHO=false
EOF

    chmod 600 .env
    ok "Файл .env создан."

}

# ─── Создание директорий ────────────────────────────────────────────────────────
create_dirs() {
    local dirs=(
        base_data/postgres
        base_data/redis
        upload_data/avatars
        upload_data/news_media
        upload_data/branding
        upload_data/link_icons
        upload_data/kb
        upload_data/photos/originals
        upload_data/photos/thumbs
        upload_data/photos/zips
        system_data/settings
        system_data/secrets
        system_data/nginx_conf
        system_data/nginx_reload
        system_data/certs
    )
    for d in "${dirs[@]}"; do
        mkdir -p "$d"
    done

    ok "Рабочие директории созданы."
}

# ─── Проверка существующих данных ──────────────────────────────────────────────
check_existing_data() {
    local found=()

    if [[ -d base_data/postgres ]] && [[ -n "$(ls -A base_data/postgres 2>/dev/null)" ]]; then
        found+=("  ${YELLOW}⚠${RESET}  base_data/postgres/      — база данных PostgreSQL")
    fi
    if [[ -d base_data/redis ]] && [[ -n "$(ls -A base_data/redis 2>/dev/null)" ]]; then
        found+=("  ${YELLOW}⚠${RESET}  base_data/redis/          — данные Redis")
    fi
    if [[ -f system_data/settings/system.json ]]; then
        found+=("  ${YELLOW}⚠${RESET}  system_data/settings/     — системные настройки")
    fi
    if [[ -f system_data/secrets/keycloak-settings.json ]]; then
        found+=("  ${YELLOW}⚠${RESET}  system_data/secrets/      — настройки Keycloak")
    fi
    if [[ -f system_data/certs/server.crt ]]; then
        found+=("  ${YELLOW}⚠${RESET}  system_data/certs/        — TLS-сертификат")
    fi
    if [[ -d upload_data ]] && [[ -n "$(find upload_data \( -name '*.jpg' -o -name '*.png' -o -name '*.md' \) -print -quit 2>/dev/null)" ]]; then
        found+=("  ${YELLOW}⚠${RESET}  upload_data/              — загруженные файлы пользователей")
    fi

    if [[ ${#found[@]} -gt 0 ]]; then
        echo
        echo -e "  ${BOLD}Обнаружены существующие данные:${RESET}"
        echo
        for item in "${found[@]}"; do
            echo -e "$item"
        done
        echo
        echo -e "  ${DIM}Пересборка контейнеров НЕ затрагивает эти данные.${RESET}"
        echo -e "  ${DIM}Чтобы начать с чистого листа — удалите папки вручную.${RESET}"
        echo
        read -r -p "  Продолжить? (Y/n): " cont
        if [[ "${cont,,}" == "n" ]]; then
            echo "  Отмена."
            exit 0
        fi
    fi
}

# ─── Генерация файлов для режима разработки ────────────────────────────────────
generate_dev_files() {
    if [[ -f docker-compose.dev.yml ]]; then
        warn "docker-compose.dev.yml уже существует — файл не будет перезаписан."
        warn "Удалите его вручную, если хотите сбросить к шаблону по умолчанию."
    else
    cat > docker-compose.dev.yml << 'DEVEOF'
# Dev override для docker-compose.yml.
# Использование:
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
#
# Что меняет:
# - публикует порты PostgreSQL (5432) и Redis (6379) наружу для подключения IDE / pgAdmin / DBeaver;
# - монтирует исходники backend в контейнер для hot-reload через uvicorn --reload;
# - снижает количество воркеров до 1 (нужен --reload);
# - frontend запускается в dev-режиме через `npm run dev` на порту 5173 (отдельный сервис).

services:
  postgres:
    ports:
      - "5432:5432"

  redis:
    ports:
      - "6379:6379"

  backend:
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    volumes:
      - ./backend/app:/app/app
      - ./backend/migrations:/app/migrations
      - ./backend/scripts:/app/scripts
      - ./backend/tests:/app/tests
      - ./upload_data/avatars:/data/avatars
      - ./upload_data/news_media:/data/news_media
      - ./upload_data/branding:/data/branding
      - ./upload_data/link_icons:/data/link_icons
      - ./upload_data/kb:/data/kb
      - ./upload_data/photos/originals:/data/photos/originals
      - ./upload_data/photos/thumbs:/data/photos/thumbs
      - ./upload_data/photos/zips:/data/photos/zips
      - ./system_data/settings:/data/settings
      - ./system_data/secrets:/data/secrets
      - ./system_data/nginx_conf:/data/nginx-conf
      - ./system_data/nginx_reload:/data/nginx
      - ./system_data/certs:/data/certs
    environment:
      ENVIRONMENT: development
      DB_ECHO: "false"

  worker:
    volumes:
      - ./backend/app:/app/app
      - ./upload_data/avatars:/data/avatars
      - ./upload_data/news_media:/data/news_media
      - ./upload_data/branding:/data/branding
      - ./upload_data/link_icons:/data/link_icons
      - ./upload_data/kb:/data/kb
      - ./upload_data/photos/originals:/data/photos/originals
      - ./upload_data/photos/thumbs:/data/photos/thumbs
      - ./upload_data/photos/zips:/data/photos/zips
      - ./system_data/settings:/data/settings
      - ./system_data/secrets:/data/secrets
DEVEOF
    fi

    cat > docker-compose.staging.yml << 'STAGEOF'
# Staging override для docker-compose.yml
#
# Использование:
#   docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
#
# Назначение:
# - тестовый стенд, максимально приближённый к production;
# - публикует Postgres/Redis наружу для дампов и интеграционных прогонов;
# - снижает потребление памяти Redis (staging-нагрузка < prod);
# - подключает sentry environment=staging;
# - публикует backend на 8000 для прямых curl/k6/zap прогонов мимо nginx;
# - включает verbose-логирование backend и worker;
# - использует отдельные тома `staging_*` чтобы не пересекаться с prod-данными
#   на одном и том же хосте (если staging и prod крутятся рядом).

services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-portal_staging}

  redis:
    ports:
      - "127.0.0.1:6379:6379"
    command: redis-server --aclfile /etc/redis/redis.acl --maxmemory 128mb --maxmemory-policy allkeys-lru

  backend:
    ports:
      - "8000:8000"
    environment:
      ENVIRONMENT: staging
      LOG_LEVEL: DEBUG
      LOG_FORCE_JSON: "true"
      SENTRY_ENVIRONMENT: staging

  worker:
    environment:
      ENVIRONMENT: staging
      LOG_LEVEL: DEBUG
      LOG_FORCE_JSON: "true"
      SENTRY_ENVIRONMENT: staging

  nginx:
    ports:
      - "${HTTP_PORT:-8080}:80"
      - "${HTTPS_PORT:-8443}:443"
STAGEOF

    ok "Файлы docker-compose.dev.yml и docker-compose.staging.yml сгенерированы."
}

# ─── Настройка sysctl для Redis ────────────────────────────────────────────────
apply_sysctl() {
    if [[ "$(sysctl -n vm.overcommit_memory 2>/dev/null)" == "1" ]]; then
        return 0
    fi

    if [[ "$(id -u)" != "0" ]]; then
        echo ""
        echo "  ⚠️  ВНИМАНИЕ: vm.overcommit_memory ≠ 1"
        echo "  Скрипт запущен не от root — параметр ядра не применён."
        echo "  Redis будет писать 'WARNING: overcommit_memory is set to 0' и"
        echo "  может некорректно работать под нагрузкой (OOM-killer на fork)."
        echo ""
        echo "  Для исправления выполните от root (или через sudo):"
        echo "    sudo sysctl -w vm.overcommit_memory=1"
        echo "    echo 'vm.overcommit_memory=1' | sudo tee /etc/sysctl.d/90-portal-redis.conf"
        echo "    sudo sysctl --system"
        echo ""
        warn "vm.overcommit_memory не применён — производительность Redis в production может пострадать."
        return 1
    fi

    if sysctl -w vm.overcommit_memory=1 &>/dev/null; then
        echo "vm.overcommit_memory=1" > /etc/sysctl.d/90-portal-redis.conf
        sysctl --system &>/dev/null || true
        ok "vm.overcommit_memory=1 применён и сохранён в /etc/sysctl.d/90-portal-redis.conf"
    else
        warn "Не удалось применить vm.overcommit_memory=1. Redis может выводить предупреждение в логах."
    fi
}

# ─── Docker Compose команды ────────────────────────────────────────────────────
run_compose() {
    local mode="$1" no_cache="${2:-}"

    if [[ "$mode" == "staging" ]]; then
        if [[ -n "$no_cache" ]]; then
            docker compose -f docker-compose.yml -f docker-compose.staging.yml build --no-cache
            docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
        else
            docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
        fi
    else
        if [[ -n "$no_cache" ]]; then
            docker compose build --no-cache
            docker compose up -d
        else
            docker compose up -d --build
        fi
    fi
}

# ─── Проверка работоспособности после запуска ──────────────────────────────────
check_services() {
    local mode="$1"

    # Имена контейнеров и читаемые метки
    local -a names=(
        "portal-postgres"
        "portal-redis"
        "portal-migrations"
        "portal-backend"
        "portal-worker"
        "portal-frontend"
        "portal-nginx"
    )
    local -a labels=(
        "postgres"
        "redis"
        "migrations"
        "backend"
        "worker"
        "frontend"
        "nginx"
    )

    local timeout=180  # 3 минуты
    local elapsed=0

    # ── Ожидание ────────────────────────────────────────────────────────────────
    echo
    printf "  Ожидаю готовности контейнеров"

    while [[ $elapsed -lt $timeout ]]; do
        local all_ready=true
        for name in "${names[@]}"; do
            local st h
            st=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
            h=$(docker inspect \
                --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-check{{end}}' \
                "$name" 2>/dev/null || echo "missing")

            # migrations завершается (exited) — это нормально
            if [[ "$name" == "portal-migrations" ]]; then
                [[ "$st" != "exited" && "$st" != "running" ]] && all_ready=false && break
                continue
            fi

            # остальные должны быть running и healthcheck не должен быть "starting"
            if [[ "$st" != "running" ]] || [[ "$h" == "starting" ]]; then
                all_ready=false
                break
            fi
        done

        if [[ "$all_ready" == "true" ]]; then break; fi
        sleep 5
        elapsed=$((elapsed + 5))
        printf "."
    done

    echo
    echo

    # ── Таблица статусов ────────────────────────────────────────────────────────
    echo -e "  ${BOLD}Статус сервисов:${RESET}"
    echo
    printf "  %-5s  %-14s  %-12s  %s\n" "" "Сервис" "Статус" "Healthcheck"
    sep

    local -a failed=()

    for i in "${!names[@]}"; do
        local name="${names[$i]}"
        local label="${labels[$i]}"
        local st h icon color

        st=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
        h=$(docker inspect \
            --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}—{{end}}' \
            "$name" 2>/dev/null || echo "missing")

        # Оцениваем статус
        local is_ok=false
        if [[ "$name" == "portal-migrations" ]]; then
            # migrations: ожидаем exited с кодом 0
            local exit_code
            exit_code=$(docker inspect --format='{{.State.ExitCode}}' "$name" 2>/dev/null || echo "1")
            [[ "$st" == "exited" && "$exit_code" == "0" ]] && is_ok=true
        elif [[ "$st" == "running" ]] && [[ "$h" != "unhealthy" ]]; then
            is_ok=true
        fi

        if $is_ok; then
            color="$GREEN"; icon="✓"
        else
            color="$RED"; icon="✗"
            failed+=("$name")
        fi

        printf "  ${color}%s${RESET}  %-14s  %-12s  %s\n" \
            "$icon" "$label" "$st" "$(echo -e "${DIM}${h}${RESET}")"
    done

    # ── Проверка HTTP /health ────────────────────────────────────────────────────
    sep

    local port
    port="$(grep '^HTTP_PORT=' .env 2>/dev/null | cut -d= -f2 || echo '80')"

    local http_code
    http_code=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" \
        "http://localhost:${port}/health" 2>/dev/null || true)
    http_code="${http_code:-000}"

    if [[ "$http_code" == "200" ]]; then
        printf "  ${GREEN}%s${RESET}  %-14s  %-12s  %s\n" \
            "✓" "/health" "HTTP ${http_code}" ""
    elif [[ "$http_code" == "000" ]]; then
        printf "  ${YELLOW}%s${RESET}  %-14s  %-12s  %s\n" \
            "⚠" "/health" "нет ответа" ""
    else
        printf "  ${RED}%s${RESET}  %-14s  %-12s  %s\n" \
            "✗" "/health" "HTTP ${http_code}" ""
        failed+=("portal-nginx")
    fi

    echo

    # ── Логи упавших контейнеров ─────────────────────────────────────────────────
    if [[ ${#failed[@]} -gt 0 ]]; then
        echo
        warn "Следующие сервисы не запустились:"
        echo
        for name in "${failed[@]}"; do
            echo -e "  ${RED}${BOLD}── Логи: ${name} ──${RESET}"
            docker logs --tail=40 "$name" 2>&1 | sed 's/^/  │ /'
            echo
        done
        sep
        echo
        echo -e "  ${BOLD}Возможные причины:${RESET}"
        echo -e "  ${DIM}• Неверный пароль в .env — пересоздайте через пункт 4${RESET}"
        echo -e "  ${DIM}• Порт 80/443 занят другим процессом — проверьте: ss -tlnp${RESET}"
        echo -e "  ${DIM}• Нехватка памяти — рекомендуется минимум 4 GB RAM${RESET}"
        echo -e "  ${DIM}• Полные логи: docker compose logs <сервис>${RESET}"
        echo -e "  ${DIM}• Статус всех контейнеров: docker compose ps${RESET}"
        echo
    fi
}

# ─── Итоговое сообщение ─────────────────────────────────────────────────────────
show_done() {
    local mode="$1"
    local http_port
    http_port=$(grep "^HTTP_PORT=" .env 2>/dev/null | cut -d= -f2 || echo "80")
    local admin_email
    admin_email=$(grep "^ADMIN_EMAIL=" .env 2>/dev/null | cut -d= -f2 || echo "см. .env")

    echo -e "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}║                   Готово!                    ║${RESET}"
    echo -e "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}"
    echo
    echo -e "  Режим:      $(current_mode_label)"
    echo -e "  Портал:     ${BOLD}http://<server>:${http_port}/${RESET}"
    echo -e "  API docs:   http://<server>:${http_port}/api/docs"
    echo
    echo -e "  Первый вход: ${BOLD}${admin_email}${RESET}"
    echo -e "  ${YELLOW}Смените пароль через профиль сразу после входа!${RESET}"
    echo
    echo -e "  ${DIM}Перезапуск без пересборки: docker compose restart${RESET}"
    echo -e "  ${DIM}Остановка:                 docker compose down${RESET}"
    echo -e "  ${DIM}Логи в реальном времени:   docker compose logs -f${RESET}"
    echo
}

# ─── Точка входа ───────────────────────────────────────────────────────────────
main() {
    # Первый запуск — нет .env
    if [[ ! -f .env ]]; then
        clear
        echo
        echo -e "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}"
        echo -e "  ${BOLD}║         Portal — первоначальная настройка    ║${RESET}"
        echo -e "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}"
        echo
        echo -e "  ${YELLOW}Файл .env не найден. Создадим его сейчас.${RESET}"
        setup_env
        create_dirs
        echo
        echo -e "  Теперь выберите режим запуска:"
    fi

    show_menu

    case "$MENU_CHOICE" in
        1)
            check_existing_data
            create_dirs
            apply_sysctl
            echo "prod" > "$MODE_FILE"
            echo -e "  Запускаю ${GREEN}Production${RESET}..."
            echo
            run_compose prod
            check_services prod
            show_done prod
            ;;
        2)
            check_existing_data
            create_dirs
            apply_sysctl
            generate_dev_files
            echo "staging" > "$MODE_FILE"
            echo -e "  Запускаю ${YELLOW}Разработка / Стейджинг${RESET}..."
            echo
            run_compose staging
            check_services staging
            show_done staging
            ;;
        3)
            local saved_mode="prod"
            if [[ -f "$MODE_FILE" ]]; then
                saved_mode=$(cat "$MODE_FILE")
            fi
            if [[ -z "$saved_mode" ]] || [[ "$saved_mode" != "staging" ]]; then
                saved_mode="prod"
            fi
            check_existing_data
            apply_sysctl
            if [[ "$saved_mode" == "staging" ]]; then generate_dev_files; fi
            echo -e "  Полная пересборка (--no-cache), режим: $(current_mode_label)"
            echo
            echo -e "  ${DIM}Останавливаю контейнеры...${RESET}"
            docker compose down --remove-orphans
            run_compose "$saved_mode" no-cache
            check_services "$saved_mode"
            show_done "$saved_mode"
            ;;
        4)
            setup_env
            echo
            echo -e "  ${DIM}Вернитесь в меню чтобы запустить контейнеры с новыми настройками.${RESET}"
            echo
            ;;
        0)
            echo -e "  Выход."
            echo
            exit 0
            ;;
        *)
            warn "Неверный выбор: '$MENU_CHOICE'"
            exit 1
            ;;
    esac
}

main "$@"
