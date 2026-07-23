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
            dev)     echo -e "${CYAN}Разработка${RESET}" ;;
            staging) echo -e "${YELLOW}Стейджинг${RESET}" ;;
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
    echo -e "  ${DIM}     Сборка production-образов и запуск. Nginx слушает порты из .env (80/443).${RESET}"
    echo
    echo -e "  ${BOLD}2.${RESET}  ${CYAN}Разработка${RESET}"
    echo -e "  ${DIM}     Сборка dev-образа (target=test): pytest, ruff, mypy, тесты внутри.${RESET}"
    echo -e "  ${DIM}     Bind-mount исходников и tests/ для hot-reload (uvicorn --reload, 1 worker).${RESET}"
    echo -e "  ${DIM}     PostgreSQL/Redis на 5432/6379, backend на :8000, ENVIRONMENT=development.${RESET}"
    echo
    echo -e "  ${BOLD}3.${RESET}  ${YELLOW}Стейджинг${RESET}"
    echo -e "  ${DIM}     Production-образ + открытые порты для QA/k6/zap, nginx на 8080/8443,${RESET}"
    echo -e "  ${DIM}     ENVIRONMENT=staging, уровень логов задаётся через Admin UI. Прод-near тестирование.${RESET}"
    echo
    echo -e "  ${BOLD}4.${RESET}  Полная пересборка ${DIM}(--no-cache)${RESET} и запуск текущего режима"
    echo -e "  ${DIM}     Нужна когда изменились Dockerfile или зависимости.${RESET}"
    echo -e "  ${DIM}     Текущий режим: $(current_mode_label).${RESET}"
    echo
    sep
    echo
    echo -e "  ${BOLD}5.${RESET}  Настроить / пересоздать .env"
    echo -e "  ${DIM}     Изменить пароли, порты, учётную запись администратора.${RESET}"
    echo
    echo -e "  ${BOLD}6.${RESET}  ${GREEN}Обновить Production${RESET}"
    echo -e "  ${DIM}     git pull → pg_dump (опц.) → docker compose pull → up -d.${RESET}"
    echo -e "  ${DIM}     Миграции применяются автоматически. Текущий режим: $(current_mode_label).${RESET}"
    echo
    echo -e "  ${BOLD}7.${RESET}  Перезапустить стек ${DIM}(без пересборки)${RESET}"
    echo -e "  ${DIM}     docker compose restart. Текущий режим: $(current_mode_label).${RESET}"
    echo
    echo -e "  ${BOLD}8.${RESET}  Остановить стек"
    echo -e "  ${DIM}     docker compose down. Данные сохраняются.${RESET}"
    echo
    echo -e "  ${BOLD}9.${RESET}  Статус + последние логи"
    echo -e "  ${DIM}     docker compose ps + logs --tail=30 backend.${RESET}"
    echo
    echo -e "  ${BOLD}10.${RESET} Запустить мониторинг ${DIM}(Grafana + Loki + Prometheus)${RESET}"
    echo -e "  ${DIM}     Observability-overlay: метрики, централизованные логи, alerting.${RESET}"
    echo -e "  ${DIM}     Grafana http://<server>:3001 (admin / admin, сменить при первом входе).${RESET}"
    echo
    echo -e "  ${BOLD}0.${RESET}  Выход"
    echo
    read -r -p "  Выберите [0-10]: " MENU_CHOICE
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
        if [[ "$var" == *'\'* ]]; then
            warn "Пароль не должен содержать символ \\ (backslash) — он ломает парсинг .env."
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
    local result
    if command -v openssl &>/dev/null; then
        result=$(openssl rand -hex 32 2>/dev/null)
        if [[ ${#result} -ne 64 || ! "$result" =~ ^[0-9a-f]{64}$ ]]; then
            warn "openssl rand failed or returned unexpected output, falling back to python3"
            result=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        fi
    else
        result=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi
    if [[ ${#result} -ne 64 ]]; then
        err "gen_secret: unable to generate a 64-hex-char secret (entropy source failure)"
        exit 1
    fi
    printf '%s' "$result"
}

encode_url() {
    python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1"
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

    SCREENSHOT_SERVICE_SECRET=$(gen_secret)
    ok "SCREENSHOT_SERVICE_SECRET сгенерирован автоматически."

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

    # ── Observability (опционально) ────────────────────────────────────────────
    h2 "Observability (Grafana + алерты)"
    echo -e "  ${DIM}Параметры для observability-overlay (monitoring/docker-compose.monitoring.yml).${RESET}"
    echo -e "  ${DIM}Overlay НЕ подключается к прод-стеку автоматически — его поднимают явно.${RESET}"
    echo -e "  ${DIM}Grafana: admin/admin при первом входе (принудительная смена), затем — SMTP для алертов.${RESET}"
    echo
    echo -e "  ${DIM}SMTP-relay для доставки алертов админам. Пусто = алерты только в UI.${RESET}"
    ALERT_SMTP_HOST=$(ask "SMTP host             ALERT_SMTP_HOST"  "")
    if [[ -n "$ALERT_SMTP_HOST" ]]; then
        ALERT_SMTP_PORT=$(ask "SMTP port             ALERT_SMTP_PORT"  "25")
        ALERT_SMTP_FROM=$(ask "SMTP From             ALERT_SMTP_FROM"  "portal-alerts@${ALERT_SMTP_HOST}")
        ALERT_ADMINS_EMAIL=$(ask "Email админов         ALERT_ADMINS_EMAIL"  "")
        ALERT_SMTP_USER=$(ask "SMTP user (опц.)      ALERT_SMTP_USER"  "")
        [[ -n "$ALERT_SMTP_USER" ]] && ALERT_SMTP_PASSWORD=$(ask_secret "SMTP password         ALERT_SMTP_PASSWORD") || ALERT_SMTP_PASSWORD=""
    else
        ALERT_SMTP_PORT="" ALERT_SMTP_FROM="" ALERT_ADMINS_EMAIL="" ALERT_SMTP_USER="" ALERT_SMTP_PASSWORD=""
    fi

    # ── Запись .env ─────────────────────────────────────────────────────────────
    local POSTGRES_PASSWORD_ENC REDIS_PASSWORD_ENC
    POSTGRES_PASSWORD_ENC=$(encode_url "$POSTGRES_PASSWORD")
    REDIS_PASSWORD_ENC=$(encode_url "$REDIS_PASSWORD")
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
# ENVIRONMENT is overridden to "staging" by docker-compose.staging.yml when running in staging mode.
# Do not change this value here — use the staging compose override instead.
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD_ENC}@postgres:5432/${POSTGRES_DB}
REDIS_URL=redis://:${REDIS_PASSWORD_ENC}@redis:6379/0

# === Nginx ports ===
HTTP_PORT=${HTTP_PORT}
HTTPS_PORT=${HTTPS_PORT}

# === Локальная аутентификация / Bootstrap ===
LOCAL_AUTH_ENABLED=${LOCAL_AUTH_ENABLED}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD='${ADMIN_PASSWORD}'
ADMIN_PASSWORD_RESET_ON_START=false

# === Screenshot service ===
# SCREENSHOT_SERVICE_URL зашит в docker-compose.yml (внутреннее имя контейнера).
SCREENSHOT_SERVICE_SECRET='${SCREENSHOT_SERVICE_SECRET}'
# (опционально) Allowlist origin'ов для endpoint /screenshot (защита от SSRF).
# SCREENSHOT_ALLOWED_ORIGINS=https://portal.company.local

# === Observability (overlay monitoring/docker-compose.monitoring.yml) ===
# Используется только при явном поднятии overlay (не в базовом прод-деплое).
GRAFANA_ADMIN_USER=admin
PORTAL_METRICS_TOKEN=
# SMTP для доставки алертов админам (Alertmanager → email). Пусто = алерты только в UI.
ALERT_SMTP_HOST=${ALERT_SMTP_HOST}
ALERT_SMTP_PORT=${ALERT_SMTP_PORT}
ALERT_SMTP_FROM=${ALERT_SMTP_FROM}
ALERT_ADMINS_EMAIL=${ALERT_ADMINS_EMAIL}
ALERT_SMTP_USER=${ALERT_SMTP_USER}
ALERT_SMTP_PASSWORD='${ALERT_SMTP_PASSWORD}'
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
        upload_data/file_icons
        upload_data/kb
        upload_data/helpdesk
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
# Шаблоны перегенерируются всегда — это служебные файлы, генерируемые setup.sh.
# Если нужны локальные правки — редактируйте оригинальный шаблон ниже, а не файл на диске.
generate_dev_files() {
    cat > docker-compose.dev.yml << 'DEVEOF'
# Dev override для docker-compose.yml — генерируется setup.sh, НЕ редактировать вручную.
#
# Использование (управляется через setup.sh, пункт меню "Разработка"):
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
#
# Что меняет относительно production-стека:
# - все backend-сервисы пересобираются из стадии `test` Dockerfile (target: test):
#   там установлены pytest/ruff/mypy и лежит каталог tests/;
# - используется отдельный image-тег `portal-backend:dev`, чтобы не пересекаться с :latest;
# - порты PostgreSQL (5432) и Redis (6379) опубликованы для IDE / pgAdmin / DBeaver / pytest с хоста;
# - backend опубликован на :8000 для прямых curl/Insomnia запросов мимо nginx;
# - исходники backend и tests/ примонтированы внутрь контейнера для hot-reload;
# - uvicorn запускается с --reload и одним воркером;
# - ENVIRONMENT=development (уровень и формат логирования управляются через Admin UI
#   → Мониторинг → Логирование, а не через env);
# - frontend пересобирается из стадии `dev` Dockerfile: Vite dev server с HMR на :5173,
#   /api проксируется напрямую на backend:8000 (env VITE_API_TARGET).
#
# URL для разработки:
#   http://localhost:5173/         — Vue UI с hot-reload (рекомендуется)
#   http://localhost:8000/api/...  — backend напрямую, минуя nginx и Vite
#   http://localhost:8080/         — nginx (production-сборка фронта в dev не пересобирается;
#                                    для проверки прод-бандла используйте режим Стейджинг)
#
# Запуск тестов в dev-стеке:
#   docker compose exec backend /app/scripts/run_pytest_unit.sh          — unit + security
#   docker compose exec backend /app/scripts/run_pytest_integration.sh   — все тесты (unit + security + integration)
#   docker compose exec frontend npm run test:unit
#   docker compose exec frontend npm run lint:check

services:
  nginx-config:
    volumes:
      - ./nginx/render-config.sh:/usr/local/bin/render-config.sh:ro
    environment:
      FRONTEND_HOST: frontend:5173

  postgres:
    ports:
      - "5432:5432"

  redis:
    ports:
      - "6379:6379"

  migrations:
    build:
      target: test
    image: portal-backend:dev

  backend:
    build:
      target: test
    image: portal-backend:dev
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app
      - ./backend/migrations:/app/migrations
      - ./backend/scripts:/app/scripts
      - ./backend/tests:/app/tests
      - ./backend/pyproject.toml:/app/pyproject.toml:ro
      - ./backend/alembic.ini:/app/alembic.ini:ro
      - ./upload_data/avatars:/data/avatars
      - ./upload_data/news_media:/data/news_media
      - ./upload_data/branding:/data/branding
      - ./upload_data/link_icons:/data/link_icons
      - ./upload_data/file_icons:/data/file-icons
      - ./upload_data/kb:/data/kb
      - ./upload_data/feedback:/data/feedback
      - ./upload_data/helpdesk:/data/helpdesk
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
      PYTHONDONTWRITEBYTECODE: "1"

  worker:
    build:
      target: test
    image: portal-backend:dev
    volumes:
      - ./backend/app:/app/app
      - ./backend/scripts:/app/scripts
      - ./upload_data/avatars:/data/avatars
      - ./upload_data/news_media:/data/news_media
      - ./upload_data/branding:/data/branding
      - ./upload_data/link_icons:/data/link_icons
      - ./upload_data/file_icons:/data/file-icons
      - ./upload_data/kb:/data/kb
      - ./upload_data/feedback:/data/feedback
      - ./upload_data/helpdesk:/data/helpdesk
      - ./upload_data/photos/originals:/data/photos/originals
      - ./upload_data/photos/thumbs:/data/photos/thumbs
      - ./upload_data/photos/zips:/data/photos/zips
      - ./system_data/settings:/data/settings
      - ./system_data/secrets:/data/secrets
    environment:
      ENVIRONMENT: development

  frontend:
    build:
      context: .
      dockerfile: ./frontend/Dockerfile
      target: dev
    image: portal-frontend:dev
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      # Анонимный том на /app/node_modules — чтобы host-овский node_modules
      # не затирал debian-slim-сборку из образа.
      - /app/node_modules
      - ./openapi.json:/openapi.json:ro
    environment:
      VITE_API_TARGET: http://backend:8000
      # Включаем polling для надёжного HMR в Docker (особенно на Windows/WSL/macOS).
      CHOKIDAR_USEPOLLING: "true"
      WATCHPACK_POLLING: "true"
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 768m
    healthcheck:
      # /@vite/client — это Vite-эндпоинт (HTTP 200 пока dev-сервер жив),
      # надёжнее чем греп index.html: index.html рендерится даже при сломанном бандле.
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:5173/@vite/client 2>/dev/null | head -c1 | grep -q . || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s
DEVEOF

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
# - публикует backend на 8000 для прямых curl/k6/zap прогонов мимо nginx;
# - уровень и формат логирования управляются через Admin UI → Мониторинг → Логирование
#   (для staging обычно ставят DEBUG + JSON всегда);
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
    environment:
      REDIS_MAXMEMORY: 128mb

  backend:
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      ENVIRONMENT: staging

  worker:
    environment:
      ENVIRONMENT: staging

  nginx:
    ports:
      - "${HTTP_PORT:-8080}:80"
      - "${HTTPS_PORT:-8443}:443"
STAGEOF

    cat > docker-compose.test.yml << 'TESTEOF'
# Test stack для backend integration-тестов — генерируется setup.sh, НЕ редактировать вручную.
#
# Назначение:
# - изолированный PostgreSQL/Redis на отдельных портах (5433/6380), чтобы не
#   конфликтовать с dev/staging/prod-стеком на той же машине;
# - tmpfs + отключённый fsync — максимум скорости, данные не сохраняются;
# - init.sql монтируется для расширений и FTS-конфигурации russian_hunspell.
#
# Использование (см. scripts/test-integration.sh):
#   docker compose -f docker-compose.test.yml up -d --wait
#   export INTEGRATION_DB=true
#   export DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test
#   export REDIS_URL=redis://localhost:6380/0
#   (cd backend && python3 -m alembic upgrade head && python3 -m pytest -m integration)
#   docker compose -f docker-compose.test.yml down -v

services:
  postgres-test:
    build:
      context: ./postgres
      dockerfile: Dockerfile
    image: portal-postgres:16
    restart: "no"
    environment:
      POSTGRES_DB: test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    command:
      - postgres
      - -c
      - fsync=off
      - -c
      - synchronous_commit=off
      - -c
      - full_page_writes=off
    tmpfs:
      - /var/lib/postgresql/data
    volumes:
      - ./backend/migrations/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d test"]
      interval: 2s
      timeout: 3s
      retries: 30
      start_period: 5s

  redis-test:
    image: redis:7-alpine
    restart: "no"
    command: ["redis-server", "--appendonly", "no", "--save", ""]
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping"]
      interval: 2s
      timeout: 3s
      retries: 30
TESTEOF

    ok "Файлы docker-compose.dev.yml, docker-compose.staging.yml и docker-compose.test.yml сгенерированы (перезаписаны)."
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
        # Не делаем return 1: при set -euo pipefail это роняло бы весь скрипт.
        # Предупреждение уже выведено; Redis продолжит работу (с варнингом в логах).
        return 0
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
    local -a files=(-f docker-compose.yml)

    case "$mode" in
        dev)     files+=(-f docker-compose.dev.yml) ;;
        staging) files+=(-f docker-compose.staging.yml) ;;
        prod)    : ;;
        *)       err "run_compose: неизвестный режим '$mode'" ;;
    esac

    if [[ -n "$no_cache" ]]; then
        docker compose "${files[@]}" build --no-cache
        docker compose "${files[@]}" up -d
    else
        docker compose "${files[@]}" up -d --build
    fi
}

# ─── Проверка работоспособности после запуска ──────────────────────────────────
check_services() {
    local mode="$1"

    # Имена контейнеров и сервисов читаются динамически из docker compose ps
    # (не хардкодим, чтобы не ломаться при переименовании container_name в compose-файле)
    local -a names=()
    local -a services=()
    while IFS=$'\t' read -r cname sname; do
        [[ -n "$cname" ]] || continue
        names+=("$cname")
        services+=("$sname")
    done < <(docker compose ps --format '{{.Name}}\t{{.Service}}' 2>/dev/null)

    if [[ ${#names[@]} -eq 0 ]]; then
        warn "docker compose ps не вернул контейнеров — возможно, стек не запущен"
        return 1
    fi

    local timeout=180  # 3 минуты
    local elapsed=0

    # ── Ожидание ────────────────────────────────────────────────────────────────
    echo
    printf "  Ожидаю готовности контейнеров"

    while [[ $elapsed -lt $timeout ]]; do
        local all_ready=true
        local waiting_for=""
        for i in "${!names[@]}"; do
            local name="${names[$i]}"
            local svc="${services[$i]}"
            local label="$svc"
            local st h
            st=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
            h=$(docker inspect \
                --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-check{{end}}' \
                "$name" 2>/dev/null || echo "missing")

            # migrations завершается (exited) — это нормально
            if [[ "$svc" == "migrations" ]]; then
                if [[ "$st" != "exited" && "$st" != "running" ]]; then
                    all_ready=false
                    waiting_for="$label (status: $st)"
                    break
                fi
                continue
            fi

            # остальные должны быть running и healthcheck не должен быть "starting"
            if [[ "$st" != "running" ]] || [[ "$h" == "starting" ]]; then
                all_ready=false
                waiting_for="$label (status: $st, health: $h)"
                break
            fi
        done

        if [[ "$all_ready" == "true" ]]; then break; fi
        sleep 5
        elapsed=$((elapsed + 5))
        printf "\r  Ожидаю готовности контейнеров: %-40s [%ds]" "${waiting_for}" "$elapsed"
    done
    printf "\r%-70s\r" ""

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
        local svc="${services[$i]}"
        local label="$svc"
        local st h icon color

        st=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
        h=$(docker inspect \
            --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}—{{end}}' \
            "$name" 2>/dev/null || echo "missing")

        # Оцениваем статус
        local is_ok=false
        if [[ "$svc" == "migrations" ]]; then
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

    # ── Проверка HTTP /ready (DB + Redis + NC + audit-партиции) ───────────────
    # /health — это liveness (тупо {"status":"ok"}), он ничего не проверяет.
    # Реальная готовность — /ready. См. backend/app/api/health.py + AGENTS.md:
    #   «Не использовать Docker healthcheck на /health (использовать /ready)».
    sep

    local http_port https_port nginx_container
    http_port="$(grep '^HTTP_PORT='  .env 2>/dev/null | cut -d= -f2 || echo '80')"
    https_port="$(grep '^HTTPS_PORT=' .env 2>/dev/null | cut -d= -f2 || echo '443')"
    nginx_container=$(docker compose ps --format '{{.Name}}\t{{.Service}}' 2>/dev/null \
        | awk -F'\t' '$2=="nginx"{print $1; exit}')

    # ВАЖНО: стучимся ВНУТРИ nginx-контейнера на http://localhost:80/ready,
    # а не с хоста через https://localhost:${https_port}/ready.
    # Причины:
    #   1. Снаружи self-signed/корпоративный CA может быть не в curl trust store
    #      → ssl-ошибка → http_code 000 (ложная тревога).
    #   2. На хосте может стоять HTTPS_PROXY env — рвёт localhost.
    #   3. Внутри контейнера nginx слушает :80 и проксирует /ready на backend.
    #      Plain HTTP, никаких TLS/SNI — детерминированно.
    # docker compose exec сам подставляет нужный compose-файл (с оверраем для dev).
    local http_code body
    if [[ -n "$nginx_container" ]]; then
        # curl -s --max-time 5 -o /dev/null -w "%{http_code}" — пишем код в stdout,
        # тело (если 503) — в файл, чтобы вывести его позже.
        http_code=$(docker exec "$nginx_container" \
            curl -s --max-time 5 -o /tmp/portal-ready-body -w "%{http_code}" \
            "http://localhost:80/ready" 2>/dev/null || true)
    else
        # nginx контейнер не найден — упадём ниже по логике failed.
        http_code="000"
    fi
    http_code="${http_code:-000}"

    if [[ "$http_code" == "200" ]]; then
        printf "  ${GREEN}%s${RESET}  %-14s  %-12s  %s\n" \
            "✓" "/ready" "HTTP ${http_code}" ""
    elif [[ "$http_code" == "503" ]]; then
        # /ready возвращает 503 если хотя бы одна подсистема (DB/Redis/NC/audit) упала.
        # Сам nginx + backend живы — показываем тело ответа (JSON с массивом checks),
        # чтобы сразу указать виновника.
        printf "  ${RED}%s${RESET}  %-14s  %-12s  %s\n" \
            "✗" "/ready" "HTTP ${http_code}" ""
        warn "nginx жив, но backend /ready сообщает о сбое подсистемы. Тело ответа:"
        docker exec "$nginx_container" cat /tmp/portal-ready-body 2>/dev/null | sed 's/^/  │ /'
        echo
        failed+=("backend")
    elif [[ "$http_code" == "000" ]]; then
        printf "  ${YELLOW}%s${RESET}  %-14s  %-12s  %s\n" \
            "⚠" "/ready" "нет ответа" ""
        warn "nginx не отвечает на http://localhost:80/ready (изнутри контейнера)."
        warn "Возможно nginx ещё стартует, либо упал backend-upstream."
        failed+=("${nginx_container:-nginx}")
    else
        printf "  ${RED}%s${RESET}  %-14s  %-12s  %s\n" \
            "✗" "/ready" "HTTP ${http_code}" ""
        failed+=("${nginx_container:-nginx}")
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
        echo -e "  ${DIM}• Неверный пароль в .env — пересоздайте через пункт «Настроить .env»${RESET}"
        echo -e "  ${DIM}• Порт из .env (HTTP_PORT/HTTPS_PORT) занят — проверьте: ss -tlnp${RESET}"
        echo -e "  ${DIM}• Нехватка памяти — рекомендуется минимум 4 GB RAM${RESET}"
        echo -e "  ${DIM}• Полные логи: docker compose logs <сервис>${RESET}"
        echo -e "  ${DIM}• Статус всех контейнеров: docker compose ps${RESET}"
        echo
        echo -e "  ${DIM}Если все сервисы healthy, но /ready падает — скорее всего проблема${RESET}"
        echo -e "  ${DIM}в подсистеме (DB/Redis/NC/audit), а не в nginx. Проверьте:${RESET}"
        echo -e "  ${DIM}  curl -sk http://localhost/ready   (изнутри nginx-контейнера)${RESET}"
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
    if [[ "$mode" == "dev" ]]; then
        echo -e "  ${BOLD}URL для разработки:${RESET}"
        echo -e "  ${DIM}Vue UI с HMR:              http://localhost:5173${RESET}"
        echo -e "  ${DIM}Backend (минуя nginx):     http://localhost:8000${RESET}"
        echo -e "  ${DIM}Postgres / Redis:          localhost:5432 / localhost:6379${RESET}"
        echo
        echo -e "  ${BOLD}Команды разработчика:${RESET}"
        echo -e "  ${DIM}Backend unit-тесты:        docker compose exec backend /app/scripts/run_pytest_unit.sh${RESET}"
        echo -e "  ${DIM}Backend все тесты:         docker compose exec backend /app/scripts/run_pytest_integration.sh${RESET}"
        echo -e "  ${DIM}Произвольный pytest:       docker compose exec backend pytest tests/<...>${RESET}"
        echo -e "  ${DIM}Backend lint (ruff):       docker compose exec backend ruff check app${RESET}"
        echo -e "  ${DIM}Backend typecheck (mypy):  docker compose exec backend mypy app${RESET}"
        echo -e "  ${DIM}Frontend unit-тесты:       docker compose exec frontend npm run test:unit${RESET}"
        echo -e "  ${DIM}Frontend lint (eslint):    docker compose exec frontend npm run lint:check${RESET}"
        echo -e "  ${DIM}Frontend typecheck:        docker compose exec frontend npm run typecheck${RESET}"
        echo -e "  ${DIM}Регенерация types.gen.d.ts:docker compose exec frontend npm run gen:types${RESET}"
        echo
    fi
    echo -e "  ${DIM}Перезапуск без пересборки: docker compose restart${RESET}"
    echo -e "  ${DIM}Остановка:                 docker compose down${RESET}"
    echo -e "  ${DIM}Логи в реальном времени:   docker compose logs -f${RESET}"
    echo
}

# ─── Загрузить переменные из .env в текущий шелл ───────────────────────────────
# Читаем вручную (grep + cut), чтобы не зависеть от.Env-парсера bash и не тащить
# лишнее (set -a; source .env; set +a ломается на значениях с пробелами/спец-символами,
# к тому же .env парсится docker'ом, а не bash — у них разные правила кавычек).
load_env_var() {
    local key="$1" default="${2:-}"
    local val
    val=$(grep -E "^${key}=" .env 2>/dev/null | head -1 | cut -d= -f2-)
    # Убираем одинарные кавычки, которыми setup_env оборачивает секреты
    val="${val#\'}"; val="${val%\'}"
    printf '%s' "${val:-$default}"
}

# ─── Подобрать compose-флаги для текущего режима ───────────────────────────────
compose_files_args() {
    local mode="$1"
    local -a files=(-f docker-compose.yml)
    case "$mode" in
        dev)     files+=(-f docker-compose.dev.yml) ;;
        staging) files+=(-f docker-compose.staging.yml) ;;
        prod)    : ;;
        *)       err "compose_files_args: неизвестный режим '$mode'" ;;
    esac
    printf '%s\n' "${files[@]}"
}

# ─── Бэкап PostgreSQL перед рискованными операциями ────────────────────────────
# Снимает pg_dump -Fc в backups/portal_<timestamp>.dump.
# Использует данные из .env (POSTGRES_USER / POSTGRES_DB).
# Возвращает 0 при успехе, 1 при ошибке.
pg_backup() {
    local backup_dir="backups"
    local ts pg_user pg_db container dump_file
    local started_by_us=false
    ts=$(date +%Y%m%d_%H%M%S)
    pg_user=$(load_env_var POSTGRES_USER portal)
    pg_db=$(load_env_var   POSTGRES_DB   portal)

    # Контейнер postgres — берём из текущего compose-стека (не хардкодим имя).
    mapfile -t compose_files < <(compose_files_args "$(cat "$MODE_FILE" 2>/dev/null || echo prod)")
    container=$(docker compose "${compose_files[@]}" ps --format '{{.Name}}\t{{.Service}}' 2>/dev/null \
        | awk -F'\t' '$2=="postgres"{print $1; exit}')

    # Если стек остановлен — но volume есть, временно поднимаем postgres,
    # снимаем дамп, аккуратно останавливаем. Это безопасно: volume на диске,
    # данные не теряются. См. docs/deploy.md §7.
    if [[ -z "$container" ]]; then
        if [[ ! -d base_data/postgres ]] || [[ -z "$(ls -A base_data/postgres 2>/dev/null)" ]]; then
            warn "Контейнер postgres не запущен и volume base_data/postgres/ пуст."
            warn "Если это первое развёртывание — это нормально (БД ещё не создана)."
            return 1
        fi
        echo -e "  ${DIM}Стек остановлен. Временно поднимаю postgres для дампа ...${RESET}"
        if ! docker compose "${compose_files[@]}" up -d --wait postgres 2>&1 | sed 's/^/  │ /'; then
            warn "Не удалось поднять postgres для дампа."
            return 1
        fi
        started_by_us=true
        # Обновим имя контейнера
        container=$(docker compose "${compose_files[@]}" ps --format '{{.Name}}\t{{.Service}}' 2>/dev/null \
            | awk -F'\t' '$2=="postgres"{print $1; exit}')
    fi

    mkdir -p "$backup_dir"
    dump_file="${backup_dir}/portal_${ts}.dump"

    echo -e "  ${DIM}Снимаю pg_dump в ${dump_file} ...${RESET}"
    local dump_ok=false
    if docker compose "${compose_files[@]}" exec -T postgres \
        pg_dump -U "$pg_user" -d "$pg_db" -Fc > "$dump_file" 2>/dev/null; then
        # Проверим, что файл не пустой и похож на pg_dump-custom (начинается с "PGDMP")
        if [[ -s "$dump_file" ]] && head -c 5 "$dump_file" | command grep -q "PGDMP"; then
            local size
            size=$(du -h "$dump_file" | cut -f1)
            ok "Бэкап готов: ${dump_file} (${size})"
            dump_ok=true
        fi
    fi

    # Если мы сами подняли postgres — остановим его обратно (приведём стек в исходное состояние).
    if $started_by_us; then
        echo -e "  ${DIM}Останавливаю временно поднятый postgres ...${RESET}"
        docker compose "${compose_files[@]}" stop postgres &>/dev/null || true
    fi

    if $dump_ok; then
        return 0
    fi
    warn "pg_dump завершился ошибкой или файл повреждён — продолжать без бэкапа рискованно."
    rm -f "$dump_file"
    return 1
}

# ─── Предложение снять бэкап перед операцией ───────────────────────────────────
# $1 — описание операции для контекста (например, «обновлением prod»).
offer_backup() {
    local op="$1" answer
    echo
    echo -e "  ${YELLOW}⚠${RESET}  Рекомендуется снять бэкап БД перед ${op}."
    read -r -p "  Снять pg_dump сейчас? (Y/n): " answer
    if [[ "${answer,,}" != "n" ]]; then
        pg_backup || warn "Бэкап не удался — решать тебе: продолжать или прервать."
    else
        warn "Продолжаю без бэкапа. Ответственность за потерю данных — на операторе."
    fi
}

# ─── Preflight: проверки перед запуском/обновлением ────────────────────────────
# Возвращает 0 если всё ок, 1 если есть блокирующие проблемы.
preflight() {
    local mode="$1"
    local fatal=0
    echo

    # ── Docker daemon ────────────────────────────────────────────────────────
    if ! docker info &>/dev/null; then
        err "Docker daemon недоступен. Проверьте: systemctl status docker / sudo service docker start"
    fi
    ok "Docker daemon: ok"

    # ── docker compose v2 ───────────────────────────────────────────────────
    if ! docker compose version &>/dev/null; then
        err "docker compose v2 недоступен. Установите: docker compose plugin."
    fi
    ok "docker compose v2: ok"

    # ── .env (кроме первого запуска) ─────────────────────────────────────────
    if [[ -f .env ]]; then
        # Проверяем обязательные ключи
        local missing=()
        for key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD REDIS_PASSWORD \
                   SECRET_KEY ADMIN_EMAIL ADMIN_PASSWORD; do
            if [[ -z "$(load_env_var "$key")" ]]; then
                missing+=("$key")
            fi
        done
        if [[ ${#missing[@]} -gt 0 ]]; then
            warn ".env есть, но пустые/отсутствуют ключи: ${missing[*]}"
            warn "Пересоздайте .env через пункт «Настроить .env»."
            fatal=1
        else
            ok ".env: все обязательные ключи заполнены"
        fi
    fi

    # ── Свободные порты ──────────────────────────────────────────────────────
    # Проверяем только prod/staging (dev использует переопределённые порты).
    if [[ "$mode" == "prod" || "$mode" == "staging" ]] && [[ -f .env ]]; then
        local http_port https_port
        http_port=$(load_env_var HTTP_PORT 80)
        https_port=$(load_env_var HTTPS_PORT 443)
        for p in "$http_port" "$https_port"; do
            # ss без root не показывает имя процесса; достаточно знать что порт занят.
            if ss -tlnH 2>/dev/null | awk '{print $4}' | grep -qE "[.:]${p}$"; then
                warn "Порт ${p} уже занят (обычно это сам портал или другой веб-сервер)."
                warn "Если это не сам портал — укажите другой порт в .env или освободите этот:"
                warn "    sudo ss -tlnp | grep ':${p} '  (покажет PID/имя процесса)"
                fatal=1
            else
                ok "Порт ${p}: свободен"
            fi
        done
    fi

    # ── Место под base_data/postgres ─────────────────────────────────────────
    local data_dir="base_data/postgres"
    mkdir -p "$data_dir" 2>/dev/null || true
    local avail_kb avail_gb
    avail_kb=$(df -P "$data_dir" 2>/dev/null | awk 'NR==2{print $4}')
    if [[ "$avail_kb" =~ ^[0-9]+$ ]]; then
        avail_gb=$(( avail_kb / 1024 / 1024 ))
        if [[ "$avail_gb" -lt 5 ]]; then
            warn "Места на диске для ${data_dir}: ${avail_gb} GB (< 5 GB минимум)."
            warn "PostgreSQL может остановиться при переполнении диска."
            fatal=1
        else
            ok "Свободно на диске: ${avail_gb} GB"
        fi
    fi

    return $fatal
}

# ─── Обновление Production до новой версии ─────────────────────────────────────
update_production() {
    h2 "Обновление Production"

    if [[ ! -f .env ]]; then
        err ".env не найден — сначала настройте (пункт «Настроить .env»)."
    fi
    if [[ "$(cat "$MODE_FILE" 2>/dev/null || echo prod)" != "prod" ]]; then
        warn "Текущий режим в .portal-mode — не prod. Обновляем всё равно prod-стек."
        read -r -p "  Продолжить? (y/N): " answer
        [[ "${answer,,}" == "y" ]] || { echo "  Отмена."; exit 0; }
    fi

    echo -e "  ${DIM}Процедура: git pull → pg_dump (опционально) → docker compose pull → up -d.${RESET}"
    echo -e "  ${DIM}Миграции применятся автоматически при старте backend (scripts/migrate.sh).${RESET}"
    echo

    # ── 1.Preflight ───────────────────────────────────────────────────────────
    preflight prod || {
        warn "Preflight выявил проблемы. Продолжить принудительно? (y/N): "
        read -r -p "  " answer
        [[ "${answer,,}" == "y" ]] || exit 1
    }

    # ── 2. git pull ───────────────────────────────────────────────────────────
    echo -e "  ${BOLD}1/4. Git pull ...${RESET}"
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        local branch
        branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
        echo -e "  ${DIM}Текущая ветка: ${branch}${RESET}"
        if ! git pull --ff-only 2>&1 | sed 's/^/  │ /'; then
            warn "git pull --ff-only не удался (локальные коммиты или расхождение)."
            warn "Разберитесь вручную: git status && git log --oneline -5"
            err "Прерываю обновление."
        fi
        ok "git pull: ok"
    else
        warn "Не в git-репозитории — пропускаю git pull."
    fi

    # ── 3. Backup ─────────────────────────────────────────────────────────────
    offer_backup "обновлением prod"

    # ── 4. docker compose pull ────────────────────────────────────────────────
    echo
    echo -e "  ${BOLD}2/4. Pull образов (если обновились в registry) ...${RESET}"
    if ! docker compose pull 2>&1 | sed 's/^/  │ /'; then
        warn "docker compose pull завершился с ошибкой — возможно часть образов собирается локально."
    fi

    # ── 5. build + up ─────────────────────────────────────────────────────────
    echo
    echo -e "  ${BOLD}3/4. Build + up -d ...${RESET}"
    docker compose down --remove-orphans 2>&1 | sed 's/^/  │ /' || true
    run_compose prod
    echo "prod" > "$MODE_FILE"

    # ── 6. Контроль миграций + check_services ─────────────────────────────────
    echo
    echo -e "  ${BOLD}4/4. Ожидаю применения миграций ...${RESET}"
    # Миграции отрабатывают в одноразовом контейнере migrations.
    # check_services дождётся его завершения и проверит /ready.
    check_services prod
    show_done prod
}

# ─── Служебные операции: restart / stop / status ───────────────────────────────
ops_restart() {
    local mode
    mode=$(cat "$MODE_FILE" 2>/dev/null || echo "prod")
    case "$mode" in prod|dev|staging) : ;; *) mode="prod" ;; esac

    mapfile -t compose_files < <(compose_files_args "$mode")
    echo -e "  Перезапуск сервисов (режим: $(current_mode_label)) ..."
    docker compose "${compose_files[@]}" restart 2>&1 | sed 's/^/  │ /'
    ok "Перезапущено. Проверьте /ready через ~10-20 секунд."
}

ops_stop() {
    local mode
    mode=$(cat "$MODE_FILE" 2>/dev/null || echo "prod")
    case "$mode" in prod|dev|staging) : ;; *) mode="prod" ;; esac

    mapfile -t compose_files < <(compose_files_args "$mode")
    echo -e "  Остановка сервисов (режим: $(current_mode_label)) ..."
    read -r -p "  Подтвердить остановку? (y/N): " answer
    [[ "${answer,,}" == "y" ]] || { echo "  Отмена."; exit 0; }
    docker compose "${compose_files[@]}" down 2>&1 | sed 's/^/  │ /'
    ok "Стек остановлен. Данные в base_data/ сохранены."
}

ops_status() {
    local mode
    mode=$(cat "$MODE_FILE" 2>/dev/null || echo "prod")
    case "$mode" in prod|dev|staging) : ;; *) mode="prod" ;; esac

    mapfile -t compose_files < <(compose_files_args "$mode")
    echo -e "  Статус сервисов (режим: $(current_mode_label)):"
    echo
    docker compose "${compose_files[@]}" ps
    echo
    echo -e "  ${DIM}Последние 30 строк логов backend:${RESET}"
    docker compose "${compose_files[@]}" logs --tail=30 backend 2>&1 | sed 's/^/  │ /'
    echo
}

# ─── Observability: запуск Grafana + Loki + Prometheus + Alloy + Alertmanager ──
# Overlay поднимается поверх основного стека (с обоими -f из корня репозитория),
# чтобы: (1) пути ./monitoring/... резолвились относительно корня (а не
# monitoring/ — иначе двойной путь monitoring/monitoring/... ломает mounts),
# (2) obs-контейнеры присоединились к сети portal_internal и видели backend.
start_monitoring() {
    h2 "Мониторинг (observability-overlay)"
    echo -e "  ${DIM}Grafana + Loki + Prometheus + Alertmanager + Alloy.${RESET}"
    echo -e "  ${DIM}Запускается как overlay поверх основного стека (оба compose-f из корня).${RESET}"
    echo

    # Проверка, что основной стек запущен — obs-контейнерам нужна сеть
    # portal_internal и живой backend для scrape /metrics.
    if ! docker compose ps --services --filter "status=running" 2>/dev/null \
         | grep -qE '^(backend|nginx)$'; then
        warn "Основной стек портала, похоже, не запущен (backend/nginx не найдены)."
        warn "Observability-overlay требует сеть portal_internal и живой backend для scrape."
        echo -e "  ${DIM}Сначала запустите портал (пункты 1/2/3), затем мониторинг.${RESET}"
        echo
        read -r -p "  Всё равно продолжить? (y/N): " ans
        [[ "${ans,,}" == "y" ]] || { echo -e "  ${DIM}Отмена.${RESET}"; return 1; }
    fi

    local overlay="monitoring/docker-compose.monitoring.yml"
    if [[ ! -f "$overlay" ]]; then
        err "Overlay $overlay не найден. Запускайте setup.sh из корня репозитория портала."
        return 1
    fi

    echo -e "  ${DIM}Grafana: логин admin / пароль admin — принудительная смена при первом входе.${RESET}"
    echo

    echo -e "  ${BOLD}Запуск observability-overlay...${RESET}"
    echo
    # КРИТИЧНО: оба -f из корня. Solo-запуск только overlay ломает пути
    # (project_directory = папка первого -f) → mount src удваивается до
    # monitoring/monitoring/... и падает с "not a directory".
    if ! docker compose \
            -f docker-compose.yml \
            -f "$overlay" \
            up -d prometheus alertmanager grafana loki alloy 2>&1 | sed 's/^/    /'; then
        err "Не удалось запустить observability-overlay. Проверьте вывод выше."
        return 1
    fi

    echo
    echo -e "  ${BOLD}Ожидание готовности сервисов (до 120 c)...${RESET}"
    echo

    # Проверяем готовность по HTTP-endpoints. Loki/Alloy не имеют встроенного
    # healthcheck (busybox убран в образах), поэтому опрашиваем с хоста.
    # curl может отсутствовать на сервере — используем временный контейнер
    # в сети portal_internal.
    local ready_loki=0 ready_prom=0 ready_grafana=0
    local attempt=0
    local max_attempts=24  # 24 × 5 c = 120 c
    while (( attempt < max_attempts )); do
        attempt=$((attempt + 1))
        # Loki /ready
        if (( ready_loki == 0 )); then
            if docker run --rm --network portal_internal curlimages/curl:latest \
                   -s --max-time 5 http://loki:3100/ready 2>/dev/null | grep -qi "ready"; then
                ready_loki=1
            fi
        fi
        # Prometheus /-/ready (отвечает "Prometheus Server is Ready." — case-insensitive)
        if (( ready_prom == 0 )); then
            if docker run --rm --network portal_internal curlimages/curl:latest \
                   -s --max-time 5 http://prometheus:9090/-/ready 2>/dev/null | grep -qi "ready"; then
                ready_prom=1
            fi
        fi
        # Grafana /api/health
        if (( ready_grafana == 0 )); then
            if docker run --rm --network portal_internal curlimages/curl:latest \
                   -s --max-time 5 http://grafana:3000/api/health 2>/dev/null | grep -qi "ok"; then
                ready_grafana=1
            fi
        fi
        # Все готовы — выходим раньше
        if (( ready_loki && ready_prom && ready_grafana )); then
            break
        fi
        printf "\r    Loki=%s  Prometheus=%s  Grafana=%s  (попытка %d/%d)   " \
            "$([ $ready_loki = 1 ] && echo '✓' || echo '·')" \
            "$([ $ready_prom = 1 ] && echo '✓' || echo '·')" \
            "$([ $ready_grafana = 1 ] && echo '✓' || echo '·')" \
            "$attempt" "$max_attempts"
        sleep 5
    done
    echo
    echo

    # Определяем адрес сервера для подсказки (внешний IP или hostname).
    local server_addr
    server_addr=$(hostname -I 2>/dev/null | awk '{print $1}')
    [[ -z "$server_addr" ]] && server_addr="<server>"

    echo -e "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}║          Мониторинг запущен!                 ║${RESET}"
    echo -e "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}"
    echo
    if (( ready_grafana )); then
        echo -e "  ${BOLD}Grafana:${RESET}        http://${server_addr}:3001"
        echo -e "  ${DIM}Логин admin / пароль admin (принудительная смена при первом входе).${RESET}"
        echo -e "  ${DIM}Доступ из Windows (WSL2): тот же URL или http://localhost:3001${RESET}"
    else
        echo -e "  ${YELLOW}Grafana:${RESET}        http://${server_addr}:3001 ${YELLOW}(ещё стартует — открой через ~30 c)${RESET}"
    fi
    echo
    echo -e "  ${BOLD}Прочие UI (опционально, для отладки):${RESET}"
    if (( ready_prom )); then
        echo -e "  Prometheus:     http://${server_addr}:9090 ${DIM}(метрики, targets, alert state)${RESET}"
    fi
    echo -e "  Alertmanager:   http://${server_addr}:9093 ${DIM}(состояние алертов)${RESET}"
    echo -e "  Loki API:       http://${server_addr}:3100 ${DIM}(обычно через Grafana)${RESET}"
    echo -e "  Alloy UI:       http://${server_addr}:12345 ${DIM}(pipeline сборщика логов)${RESET}"
    echo
    if (( ready_loki )); then
        ok "Логи портала уже собираются в Loki — открой дашборд «Portal — Logs» в Grafana."
    else
        warn "Loki ещё стартует — логи появятся в дашборде через ~30 c."
    fi
    echo
    echo -e "  ${BOLD}Остановка мониторинга (без остановки портала):${RESET}"
    echo -e "  ${DIM}docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \${RESET}"
    echo -e "  ${DIM}    stop prometheus alertmanager grafana loki alloy${RESET}"
    echo -e "  ${DIM}(ВНИМАНИЕ: 'down' вместо 'stop' остановит ВЕСЬ стек портала — оба compose-f.${RESET}"
    echo -e "  ${DIM} данные Grafana/Loki/Prometheus сохраняются в named volumes при любом варианте.)${RESET}"
    echo
}

# ─── Точка входа ───────────────────────────────────────────────────────────────
main() {
    # Неинтерактивный режим для CI: сгенерировать dev/staging compose-оверрайды и выйти.
    if [[ "${1:-}" == "gen-dev-files" ]]; then
        generate_dev_files
        exit 0
    fi

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
            preflight prod
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
            preflight dev
            echo "dev" > "$MODE_FILE"
            echo -e "  Запускаю ${CYAN}Разработка${RESET}..."
            echo
            run_compose dev
            check_services dev
            show_done dev
            ;;
        3)
            check_existing_data
            create_dirs
            apply_sysctl
            generate_dev_files
            preflight staging
            echo "staging" > "$MODE_FILE"
            echo -e "  Запускаю ${YELLOW}Стейджинг${RESET}..."
            echo
            run_compose staging
            check_services staging
            show_done staging
            ;;
        4)
            local saved_mode="prod"
            if [[ -f "$MODE_FILE" ]]; then
                saved_mode=$(cat "$MODE_FILE")
            fi
            case "$saved_mode" in
                prod|dev|staging) : ;;
                *) saved_mode="prod" ;;
            esac
            check_existing_data
            apply_sysctl
            preflight "$saved_mode"
            if [[ "$saved_mode" == "dev" || "$saved_mode" == "staging" ]]; then
                generate_dev_files
            fi
            echo -e "  Полная пересборка (--no-cache), режим: $(current_mode_label)"
            # --no-cache пересобирает образы — если что-то пойдёт не так,
            # откат без бэкапа будет болезненным. Предлагаем pg_dump.
            offer_backup "полной пересборкой (--no-cache)"
            echo
            echo -e "  ${DIM}Останавливаю контейнеры...${RESET}"
            docker compose down --remove-orphans
            run_compose "$saved_mode" no-cache
            check_services "$saved_mode"
            show_done "$saved_mode"
            ;;
        5)
            setup_env
            echo
            echo -e "  ${DIM}Вернитесь в меню чтобы запустить контейнеры с новыми настройками.${RESET}"
            echo
            ;;
        6)
            update_production
            ;;
        7)
            ops_restart
            ;;
        8)
            ops_stop
            ;;
        9)
            ops_status
            ;;
        10)
            start_monitoring
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
