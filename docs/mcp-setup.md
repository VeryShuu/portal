# MCP-серверы для разработки портала

> Конфигурация для агента (ZCode) — какие MCP-серверы подключены, как их установить
> и как они настраиваются. Локальный конфиг `.zcode/config.json` в git НЕ идёт
> (`.zcode/` в `.gitignore`), эта инструкция — единственный источник истины для команды.

## Что подключено

| MCP | Назначение | Режим |
|---|---|---|
| `codebase-memory` | Граф кодовой базы (callers/callees, hotspots) | user-scope |
| `playwright` | Браузерная автоматизация (firefox, isolated) | workspace |
| `postgres` | Read-only доступ к PostgreSQL | workspace, restricted |
| `github` | Read-only GitHub API (через `gh auth token`) | workspace |
| `docker` | Управление контейнерами `portal-*` | workspace |

## Установка на новой машине

### 1. Установить `codebase-memory` (user-scope)

См. актуальную инструкцию в репозитории `codebase-memory-mcp`. Установленный бинарник
должен быть по пути `/home/<user>/.local/bin/codebase-memory-mcp` либо прописан в
`~/.zcode/cli/config.json`:

```json
{
  "mcp": {
    "servers": {
      "codebase-memory": {
        "type": "stdio",
        "command": "/home/<user>/.local/bin/codebase-memory-mcp",
        "args": []
      }
    }
  }
}
```

### 2. Скопировать workspace-конфиг

```bash
# из корня репозитория
mkdir -p .zcode
# создать .zcode/config.json по образцу ниже (заменить /home/snow → свой путь)
mkdir -p scripts/mcp
# скопировать scripts/mcp/postgres-run.sh и scripts/mcp/github-token.sh
chmod +x scripts/mcp/*.sh
```

`.zcode/config.json` (ВНИМАНИЕ: пути — абсолютные, не `${...}`):

```json
{
  "mcp": {
    "servers": {
      "playwright": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest", "--isolated", "--headless", "--browser", "firefox"]
      },
      "postgres": {
        "type": "stdio",
        "command": "bash",
        "args": ["/home/<user>/portal/scripts/mcp/postgres-run.sh"]
      },
      "github": {
        "type": "stdio",
        "command": "bash",
        "args": ["/home/<user>/portal/scripts/mcp/github-token.sh"]
      },
      "docker": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-docker-server"]
      }
    }
  }
}
```

### 3. Предварительные требования

| Компонент | Зачем | Как проверить |
|---|---|---|
| `node` + `npx` (≥ 20) | playwright, docker MCP | `node --version` |
| `docker` + доступ к сокету | postgres (контейнер), docker MCP | `docker ps` |
| пользователь в группе `docker` | docker MCP без sudo | `id \| grep docker` |
| `gh` CLI + `gh auth login` | github MCP (токен) | `gh auth status` |
| `python3` | postgres wrapper (urlencode) | `python3 --version` |
| `.env` с `POSTGRES_PASSWORD` | postgres MCP (DSN) | `grep POSTGRES_PASSWORD .env` |
| запущенный compose-стек | postgres MCP (сеть `portal_internal`) | `docker network ls \| grep portal_internal` |

### 4. Скачать Docker-образы (один раз)

```bash
docker pull crystaldba/postgres-mcp:latest
docker pull ghcr.io/github/github-mcp-server:latest
```

npx-образы (`@playwright/mcp`, `mcp-docker-server`) скачаются автоматически при первом запуске.

### 5. Перезапустить ZCode и проверить

После правки `.zcode/config.json` — **обязательно перезапустить сессию ZCode**,
чтобы новый конфиг подхватился (MCP подключаются при старте).

В ZCode: **Settings → MCP** — все 5 серверов должны быть в статусе `running`.
Если `failed` — см. `/diagnosing-mcp`.

## Безопасность

- **Секретов в `.zcode/config.json` и `scripts/mcp/*.sh` — нет.** Пароль Postgres
  читается из `.env`, GitHub-токен — из `~/.config/gh/hosts.yml` через `gh auth token`.
- **Postgres MCP — read-only** (`--access-mode restricted`): даже случайный
  `DROP TABLE` через агента не пройдёт. Для миграций используйте `alembic` как обычно.
- **GitHub MCP — read-only** (`--read-only`): агент не может пушить/мержить/закрывать PR.
  Коммиты и пуши — только вручную через `git`/`gh` (см. AGENTS.md → «Коммиты — только пользователь»).
- **Docker MCP** — полный доступ к `docker.sock`. Если хотите ограничить — добавьте
  в wrapper фильтрацию по имени контейнера.

## Как это работает (технические детали)

### postgres MCP — почему wrapper + контейнер в `portal_internal`

Postgres в `docker-compose.yml` **не экспонирует порт на хост** — к нему можно
подключиться только из compose-сети. Поэтому wrapper:

1. Читает `POSTGRES_PASSWORD` из `.env` (не дублируем секрет).
2. URL-кодирует пароль (на случай спецсимволов).
3. Запускает контейнер `crystaldba/postgres-mcp` в сети `portal_internal`,
   где Postgres доступен по сервисному имени `postgres:5432`.
4. Передаёт `--access-mode restricted` (read-only).

### github MCP — почему wrapper

GitHub-токен уже хранится в `gh` (`~/.config/gh/hosts.yml`). Чтобы не плодить
секреты в env-переменных или `.env`, wrapper достаёт его через `gh auth token`
в рантайме и передаёт как `GITHUB_PERSONAL_ACCESS_TOKEN` в Docker-контейнер.

## Устранение проблем

| Симптом | Причина | Решение |
|---|---|---|
| `postgres` failed, password auth failed | `.env` изменён, контейнер Postgres не перезапущен | `docker compose up -d postgres` (применит новый пароль) |
| `postgres` failed, connection refused | compose-стек не запущен | `docker compose up -d` |
| `github` failed, empty token | `gh auth login` не выполнен | `gh auth login` (scopes: `repo`, `read:org`) |
| `docker` не видит контейнеры | пользователь не в группе `docker` | `sudo usermod -aG docker $USER && newgrp docker` |
| `${...}` в логах буквально | в config.json использован шаблон | заменить на абсолютный путь (schema строгая) |
| сервер отсутствует в Settings → MCP | неизвестный top-level ключ в JSON | убрать всё, кроме `type`/`command`/`args`/`cwd`/`env`/`enabled`/`timeoutMs` |
