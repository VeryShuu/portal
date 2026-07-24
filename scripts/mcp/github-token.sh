#!/usr/bin/env bash
# Wrapper для GitHub MCP: достаёт токен из `gh auth` (~/.config/gh/hosts.yml)
# и запускает официальный github-mcp-server в read-only режиме.
#
# Почему wrapper, а не прямой вызов:
#   - Токен уже хранится в gh — не дублируем секрет в .mcp.json / env.
#   - .mcp.json коммитится в git; скрипт безопасен (без секрета внутри).
#   - Флаг --read-only защищает от случайных мутаций через MCP.
#
# Если gh не авторизован — запустите: gh auth login (scopes: repo, read:org).

set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI не установлен. Установите и выполните 'gh auth login'." >&2
  exit 1
fi

TOKEN="$(gh auth token)"

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: gh auth token вернул пустоту. Выполните 'gh auth login'." >&2
  exit 1
fi

export GITHUB_PERSONAL_ACCESS_TOKEN="${TOKEN}"

# read-only: список PR/issues/CI/репо; toolsets ограничены тем, что реально нужно.
# Добавьте toolsets при необходимости (например: 'issues,pull_requests,actions,repos,code_security').
# Детерминированное имя + самоочистка осиротевших копий (см. postgres-run.sh):
# ZCode при reconnect бросает stdio, под WSL2 --rm не срабатывает → зомби.
CONTAINER_NAME="mcp-github"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

exec docker run --rm -i \
  --name "${CONTAINER_NAME}" \
  -e GITHUB_PERSONAL_ACCESS_TOKEN \
  ghcr.io/github/github-mcp-server:latest \
  stdio --read-only
