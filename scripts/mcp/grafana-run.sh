#!/usr/bin/env bash
# Wrapper для Grafana MCP (grafana/mcp-grafana, образ mcp/grafana):
#   - читает GRAFANA_MCP_TOKEN из /home/snow/portal/.env (секрет не дублируется в конфиге);
#   - запускает контейнер в compose-сети portal_internal, Grafana доступна по
#     имени сервиса `grafana:3000` (работает только при поднятом мониторинг-оверлее:
#     `docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d`);
#   - токен Viewer (service account `zcode-mcp`) — только чтение: логи Loki,
#     метрики PromQL, дашборды, алерты. Мутации через этот MCP недоступны.
#
# Образ запинен по digest (тега версии у mcp/grafana нет — только `latest`).
# Обновление: docker pull mcp/grafana:latest, взять дайджест из
# `docker images --digests mcp/grafana`, подставить сюда и перезапустить ZCode.

set -euo pipefail

ENV_FILE="/home/snow/portal/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} не найден." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  awk -F= -v k="${key}" '
    $1 == k {
      v = substr($0, index($0, "=") + 1)
      if ((substr(v,1,1) == "'"'"'" && substr(v,length(v),1) == "'"'"'") || \
          (substr(v,1,1) == "\"" && substr(v,length(v),1) == "\"")) {
        v = substr(v, 2, length(v) - 2)
      }
      sub(/[ \t\r\n]+$/, "", v)
      print v
    }
  ' "${ENV_FILE}" | tail -1
}

GRAFANA_MCP_TOKEN="$(read_env_value GRAFANA_MCP_TOKEN)"
if [[ -z "${GRAFANA_MCP_TOKEN}" ]]; then
  echo "ERROR: GRAFANA_MCP_TOKEN не задан в ${ENV_FILE} (service account zcode-mcp в Grafana)." >&2
  exit 1
fi
export GRAFANA_MCP_TOKEN

# Внутри portal_internal Grafana — по имени сервиса; публикуемый хостом :3001 не нужен.
export GRAFANA_URL="${GRAFANA_URL:-http://grafana:3000}"
# mcp-grafana читает API-ключ из GRAFANA_API_KEY.
export GRAFANA_API_KEY="${GRAFANA_MCP_TOKEN}"

CONTAINER_NAME="mcp-grafana"
# Детерминированное имя + самоочистка (см. комментарий в postgres-run.sh — WSL2-зомби).
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

exec docker run --rm -i \
  --name "${CONTAINER_NAME}" \
  --network portal_internal \
  -e GRAFANA_URL \
  -e GRAFANA_API_KEY \
  mcp/grafana@sha256:9362bcf6aa0e44e61f645b905cec03fb346a946a34a4dafecd7f3e28d3724014 \
  -t stdio
