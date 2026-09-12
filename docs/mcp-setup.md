# MCP-серверы для разработки портала

> **Когда читать:** настраиваешь MCP-инструменты ZCode на новой машине / непонятно,
> какой MCP-сервер за что отвечает / `mcp__*`-тул не появляется в сессии.
> **Ключевой код:** `.zcode/config.json` (workspace, коммитится — секретов нет),
> `~/.zcode/cli/config.json` (user), `scripts/mcp/` (wrapper-скрипты; секреты читают
> из `.env`). **Связано:** таблица MCP-серверов в
> [`../AGENTS.md`](../AGENTS.md) §«Доступные инструменты (MCP)».
>
> Конфигурация для агента (ZCode) — какие MCP-серверы подключены, как их установить
> и как они настраиваются. Конфиг `.zcode/config.json` коммитится (`.gitignore`
> исключает всё содержимое `.zcode/`, кроме него; секретов в конфиге нет — только
> абсолютные пути к wrapper-скриптам).

## Что подключено

| MCP | Назначение | Режим |
|---|---|---|
| `codebase-memory` | Граф кодовой базы (callers/callees, hotspots) | user-scope |
| `playwright` | Браузерная автоматизация (firefox, isolated) | workspace |
| `postgres` | Read-only доступ к PostgreSQL | workspace, restricted |
| `grafana` | Логи Loki / метрики Prometheus / дашборды и алерты (Viewer, read-only) | workspace, monitoring-оверлей |
| `docker` | Управление контейнерами `portal-*` | workspace |
| `context7` | Актуальные version-specific доки библиотек | workspace |

> **Где Forgejo?** Для работы с Git-хостингом (PR, релизы, статусы CI) отдельного
> MCP-сервера нет — GitHub заблокирован, репозиторий переехал на self-hosted Forgejo
> (`forgejo.mage.ru/mage/portal`, см. ADR-048). Операции делаются через REST API Forgejo
> (Gitea-совместимый) с админ-токеном — см. §«Работа с Forgejo через API» ниже.

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
# скопировать scripts/mcp/postgres-run.sh
chmod +x scripts/mcp/*.sh
```

`.zcode/config.json` (ВНИМАНИЕ: пути — абсолютные, не `${...}`; npx-пакеты запинены
на конкретные версии — обновление пина ручное, чтобы новый релиз MCP не менял
поведение сессии внезапно):

```json
{
  "mcp": {
    "servers": {
      "playwright": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@0.0.79", "--isolated", "--headless", "--browser", "firefox"]
      },
      "postgres": {
        "type": "stdio",
        "command": "bash",
        "args": ["/home/<user>/portal/scripts/mcp/postgres-run.sh"]
      },
      "grafana": {
        "type": "stdio",
        "command": "bash",
        "args": ["/home/<user>/portal/scripts/mcp/grafana-run.sh"]
      },
      "docker": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-docker-server@1.0.1"]
      },
      "context7": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@4.0.4"]
      }
    }
  }
}
```

### 3. Предварительные требования

| Компонент | Зачем | Как проверить |
|---|---|---|
| `node` + `npx` (≥ 20) | playwright, docker, context7 MCP | `node --version` |
| `docker` + доступ к сокету | postgres (контейнер), docker MCP | `docker ps` |
| пользователь в группе `docker` | docker MCP без sudo | `id \| grep docker` |
| `python3` | postgres wrapper (urlencode) | `python3 --version` |
| `.env` с `POSTGRES_PASSWORD` | postgres MCP (DSN) | `grep POSTGRES_PASSWORD .env` |
| запущенный compose-стек | postgres MCP (сеть `portal_internal`) | `docker network ls \| grep portal_internal` |
| поднятый monitoring-оверлей + `GRAFANA_MCP_TOKEN` в `.env` | grafana MCP (Loki/Prometheus) | `docker compose ps grafana` && `grep -c GRAFANA_MCP_TOKEN .env` |
| админ-токен Forgejo (env `FORGEJO_TOKEN`) | операции с Git-хостингом через API | `curl -sH "Authorization: token $FORGEJO_TOKEN" https://forgejo.mage.ru/api/v1/user` |

> **WSL2:** используйте Linux-версии `node`, `npm` и `npx` одной версии (для портала —
> Node.js 20, как в CI). Не смешивайте `/usr/bin/node` с `npm` из `/mnt/c/Program Files`:
> нативные зависимости и shims из Windows `node_modules` несовместимы с Linux. После
> смены Node.js выполните `cd frontend && npm ci` и убедитесь, что `command -v node npm npx`
> указывает на Linux-пути (в текущей среде — `~/.nvm/versions/node/.../bin/`).

### 4. Скачать Docker-образы (один раз)

```bash
docker pull crystaldba/postgres-mcp:latest
```

npx-образы (`@playwright/mcp`, `mcp-docker-server`, `@upstash/context7-mcp`) скачаются
автоматически при первом запуске (версии запинены в конфиге). Образ `mcp/grafana`
подтянется при первом запуске wrapper'а — дайджест запинен прямо в скрипте.

### 5. Перезапустить ZCode и проверить

После правки `.zcode/config.json` — **обязательно перезапустить сессию ZCode**,
чтобы новый конфиг подхватился (MCP подключаются при старте).

В ZCode: **Settings → MCP** — все серверы должны быть в статусе `running`.
Если `failed` — см. `/diagnosing-mcp`.

## Работа с Forgejo через API

GitHub заблокирован, отдельного `forgejo`/`gitea` MCP не ставим. Вместо этого —
REST API Forgejo (Gitea-совместимый, `https://forgejo.mage.ru/api/v1/...`) через `curl`
с админ-токеном. Токен хранится в env `FORGEJO_TOKEN` (выдаётся в
**Settings → Applications → Access Tokens**, scope `write:repository`/`write:package`).

### Доступ Codex Desktop

В текущей рабочей среде Codex Desktop переменная `FORGEJO_TOKEN` доступна также
из WSL и аутентифицируется в Forgejo от имени `Reydan` (проверено 2026-08-13:
`GET /api/v1/user` → HTTP 200). Это полнопривилегированный личный токен владельца
`mage/portal`: агент может читать и изменять репозиторий, PR, Actions, релизы и
пакеты в рамках явно поставленной задачи.

Токен задан в пользовательском окружении Windows и проброшен в WSL через
`WSLENV=FORGEJO_TOKEN`; его значение не дублируется в `.env`, профиле оболочки,
`.zcode/config.json`, git или документации. При новой сессии достаточно безопасно
проверить доступ запросом `GET /api/v1/user`, не выводя значение токена.

```bash
# Создать PR
curl -X POST -H "Authorization: token $FORGEJO_TOKEN" \
  https://forgejo.mage.ru/api/v1/repos/mage/portal/pulls \
  -d '{"head":"feat/x","base":"main","title":"...","body":"..."}'

# Статусы CI-прогонов
curl -H "Authorization: token $FORGEJO_TOKEN" \
  https://forgejo.mage.ru/api/v1/repos/mage/portal/actions/runs?limit=5

# Создать Release (релизный процесс — см. scripts/release.sh + .forgejo/workflows/ci.yml::deploy-bundle)
curl -X POST -H "Authorization: token $FORGEJO_TOKEN" \
  https://forgejo.mage.ru/api/v1/repos/mage/portal/releases \
  -d '{"tag_name":"v1.2.3","name":"v1.2.3",...}'
```

## Безопасность

- **Секретов в `.zcode/config.json` и `scripts/mcp/*.sh` — нет.** Пароль Postgres
  читается из `.env`; Forgejo-токен — из env `FORGEJO_TOKEN` (не коммитить).
- **Postgres MCP — read-only** (`--access-mode restricted`): даже случайный
  `DROP TABLE` через агента не пройдёт. Для миграций используйте `alembic` как обычно.
- **Docker MCP** — полный доступ к `docker.sock`. Если хотите ограничить — добавьте
  в wrapper фильтрацию по имени контейнера.
- **Коммиты и пуши — только вручную** через `git` (см. AGENTS.md → «Коммиты — только пользователь»).

## Как это работает (технические детали)

### postgres MCP — почему wrapper + контейнер в `portal_internal`

Postgres в `docker-compose.yml` **не экспонирует порт на хост** — к нему можно
подключиться только из compose-сети. Поэтому wrapper:

1. Читает `POSTGRES_PASSWORD` из `.env` (не дублируем секрет).
2. URL-кодирует пароль (на случай спецсимволов).
3. Запускает контейнер `crystaldba/postgres-mcp` в сети `portal_internal`,
   где Postgres доступен по сервисному имени `postgres:5432`.
4. Передаёт `--access-mode restricted` (read-only).

### grafana MCP — контейнер в `portal_internal`, токен Viewer

Wrapper `scripts/mcp/grafana-run.sh` (по образцу postgres-run.sh):

1. Читает `GRAFANA_MCP_TOKEN` из `.env` — токен service account `zcode-mcp`
   с ролью **Viewer** (только чтение: Loki, PromQL, дашборды, алерты; мутации
   недоступны). Аккаунт создаётся в Grafana: *Administration → Users and
   permissions → Service accounts*.
2. Запускает контейнер `mcp/grafana` в сети `portal_internal` — Grafana доступна
   по имени сервиса `grafana:3000`; публикуемый хостом `:3001` не используется.
3. Образ запинен по digest (у `mcp/grafana` тегов версий нет — только `latest`).
   Обновление: `docker pull mcp/grafana:latest`, взять digest из
   `docker images --digests mcp/grafana`, подставить в скрипт.
4. Требуется поднятый monitoring-оверлей (`setup.sh` → пункт 10, ADR-044):
   без него контейнер MCP стартует, но каждый запрос вернёт connection refused.

## Устранение проблем

| Симптом | Причина | Решение |
|---|---|---|
| `postgres` failed, password auth failed | `.env` изменён, контейнер Postgres не перезапущен | `docker compose up -d postgres` (применит новый пароль) |
| `postgres` failed, connection refused | compose-стек не запущен | `docker compose up -d` |
| `docker` не видит контейнеры | пользователь не в группе `docker` | `sudo usermod -aG docker $USER && newgrp docker` |
| `${...}` в логах буквально | в config.json использован шаблон | заменить на абсолютный путь (schema строгая) |
| `grafana` failed: «GRAFANA_MCP_TOKEN не задан» | в `.env` нет токена | создать service account в Grafana (роль Viewer), вписать токен в `.env` |
| `grafana` запускается, но запросы падают | monitoring-оверлей не поднят | `setup.sh` → пункт 10 (`docker compose ps grafana`) |
| сервер отсутствует в Settings → MCP | неизвестный top-level ключ в JSON | убрать всё, кроме `type`/`command`/`args`/`cwd`/`env`/`enabled`/`timeoutMs` |
