#!/usr/bin/env bash
# Wrapper для Postgres MCP (crystaldba/postgres-mcp):
#   - читает POSTGRES_* из /home/snow/portal/.env (не дублируем секрет в .mcp.json);
#   - запускает контейнер в compose-сети portal_internal, чтобы достучаться до сервиса `postgres:5432`
#     (Postgres не экспонирован на хост — это единственный путь);
#   - --access-mode restricted = read-only (защита production-БД от случайных мутаций).
#
# Если меняете пароль в .env — перезапустите ZCode, чтобы wrapper подхватил новое значение.

set -euo pipefail

ENV_FILE="/home/snow/portal/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} не найден. Скопируйте .env.example → .env и заполните." >&2
  exit 1
fi

# Безопасный парсинг .env: достаём value, убираем ОДИНАРНЫЕ и двойные кавычки,
# обрезаем trailing whitespace. Не используем eval (security).
read_env_value() {
  local key="$1"
  awk -F= -v k="${key}" '
    $1 == k {
      v = substr($0, index($0, "=") + 1)
      # Убираем парные кавычки по краям.
      if ((substr(v,1,1) == "'"'"'" && substr(v,length(v),1) == "'"'"'") || \
          (substr(v,1,1) == "\"" && substr(v,length(v),1) == "\"")) {
        v = substr(v, 2, length(v) - 2)
      }
      # trim trailing CR/whitespace.
      sub(/[ \t\r\n]+$/, "", v)
      print v
    }
  ' "${ENV_FILE}" | tail -1
}

PG_DB="$(read_env_value POSTGRES_DB)"
PG_USR="$(read_env_value POSTGRES_USER)"
PG_PWD="$(read_env_value POSTGRES_PASSWORD)"

: "${PG_DB:=portal}"
: "${PG_USR:=portal}"
if [[ -z "${PG_PWD}" ]]; then
  echo "ERROR: POSTGRES_PASSWORD не задан в ${ENV_FILE}." >&2
  exit 1
fi

# URL-кодирование пароля (на случай спецсимволов).
urlencode_python() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=""))'
}
PG_PWD_ENC="$(printf '%s' "${PG_PWD}" | urlencode_python)"

DSN="postgresql://${PG_USR}:${PG_PWD_ENC}@postgres:5432/${PG_DB}"

# Детерминированное имя + самоочистка: ZCode при reconnect/restart «бросает»
# stdio-процесс, не закрывая stdin чисто — под WSL2 `docker run --rm` тогда не
# срабатывает (контейнер не получает EOF и висит зомби). Фиксим так: при каждом
# запуске убиваем осиротевший контейнер с тем же именем, затем поднимаем новый.
# --name гарантирует, что копий не плодится (иначе был бы случайный random-name).
CONTAINER_NAME="mcp-postgres"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

exec docker run --rm -i \
  --name "${CONTAINER_NAME}" \
  --network portal_internal \
  crystaldba/postgres-mcp:latest \
  --access-mode restricted \
  "${DSN}"
