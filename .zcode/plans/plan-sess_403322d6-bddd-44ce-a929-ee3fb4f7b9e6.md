# План: CI-сборка образов в GHCR + переход на pull-based деплой

## Решения по умолчанию (оспоримы при рассмотрении)
- **Тегирование:** на каждый push в `main` → теги `sha-<7симв>` (точный откат) + `latest` (указатель на HEAD). При ручном push tag `v*` → дополнительно `v1.2.3`, `v1.2`, `v1`.
- **Postgres:** пушить в registry тоже (образ с hunspell).
- **Префикс registry:** через переменную `${IMAGE_PREFIX:-}` в compose. Пустая = локальная сборка (dev не ломается), на проде `IMAGE_PREFIX=ghcr.io/veryshuu/`.

## Контекст находок (почему план именно такой)
1. `docker-compose.yml` уже использует `${IMAGE_TAG:-latest}` на 6 из 7 образов — plumbing готов.
2. Но **имена без registry-префикса** (`portal-backend`), и `IMAGE_TAG` нигде не определяется в `.env` → на проде разрешается в `latest`, образы строятся локально.
3. CI (15 job'ов) тестирует отлично, но **ни один job не билдит/пушит образы**. Зато `compose-smoke` уже локально билдит стек и гоняет healthcheck — его используем как gate перед publish.
4. `setup.sh:run_compose()` **всегда передаёт `--build`** — несовместимо с pull-флоу, нужна ветвление.
5. Backend-образ один на три сервиса (backend, worker, migrations).

---

## Этап 1 — Compose: registry-префикс через IMAGE_PREFIX

**Файл:** `docker-compose.yml` (строки 71, 103, 123, 182, 234, 262, 285)

6 сервисов получают префикс (postgres — на этапе 2):
```
- image: portal-backend:${IMAGE_TAG:-latest}
+ image: ${IMAGE_PREFIX:-}portal-backend:${IMAGE_TAG:-latest}
```
Шаблон: `{portal-backend, portal-frontend, portal-nginx, portal-nginx-config, portal-screenshot}`. Поведение: `IMAGE_PREFIX` пуст → `portal-backend:latest` (локально, dev не меняется).

**Файл:** `monitoring/docker-compose.monitoring.yml:316` — `portal-storage-collector` аналогично.

## Этап 2 — Compose: postgres в registry

**Файл:** `docker-compose.yml` — postgres-сервис.
```
- image: portal-postgres:16
+ image: ${IMAGE_PREFIX:-}portal-postgres:16
```
Тег `:16` фиксируем по major-версии (как сейчас). Локально `IMAGE_PREFIX` пуст → `portal-postgres:16` собирается из `./postgres`. На проде → pull из GHCR.

## Этап 3 — CI: новый job `publish-images`

**Файл:** `.github/workflows/ci.yml` — добавить job после `compose-smoke`.

Логика:
- `needs: [backend-lint, backend-unit, frontend-lint, frontend-unit, compose-smoke]` (публикуем только если весь набор gate'ов зелёный).
- `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` (НЕ на PR — не пушим с pull_request-раннеров).
- Permissions: `contents: read`, `packages: write`.
- Compute tag:
  ```yaml
  - id: meta
    run: |
      echo "sha=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      # если пуш tag v1.2.3 — парсим semver
      ...
  ```
- `docker/login-action` → `ghcr.io` через `${{ github.token }}` (встроенный `GITHUB_TOKEN`, никаких секретов).
- Для каждого из 6 контекстов: `docker/build-push-action` с `push: true`, теги:
  - всегда: `ghcr.io/veryshuu/<image>:sha-<short>`, `ghcr.io/veryshuu/<image>:latest`
  - при tag `v*`: дополнительно `:v1.2.3`, `:v1.2`, `:v1`
- `cache-from`/`cache-to: type=gha` — кэш сборки между запусками (ускоряет с ~6 до ~2 мин).
- Build matrix (контексты): `backend` (target: production), `frontend`, `nginx`, `nginx-config` (context: `./nginx`, dockerfile: `Dockerfile.config`), `screenshot-service`, `postgres`.

Backend — одна сборка с `target: production`, далее используется 3 сервисами (backend/worker/migrations) по одному имени образа.

## Этап 4 — .env.example: документируем новые переменные

**Файл:** `.env.example` — добавить секцию в начало блока infra:
```dotenv
# === Container images (registry) ===
# Для pull из GHCR на проде: IMAGE_PREFIX=ghcr.io/veryshuu/
# Пусто (по умолчанию) = локальная сборка образов из исходников.
IMAGE_PREFIX=
# Тег образов. 'latest' = последний successful CI-билд из main.
# Для точечного отката: IMAGE_TAG=sha-abc1234 (short SHA из CI).
IMAGE_TAG=latest
```

## Этап 5 — setup.sh: ветвление pull vs build

**Файл:** `setup.sh`

5a. `run_compose()` (стр. 684-701): добавить режим pull. Новая сигнатура:
```bash
run_compose() {
    local mode="$1" no_cache="${2:-}"
    local -a files=(-f docker-compose.yml)
    case "$mode" in dev) ... ;; staging) ... ;; prod) : ;; *) ... ;; esac

    # На проде — pull из registry (если IMAGE_PREFIX задан), иначе локальная сборка.
    if [[ "$mode" == "prod" && -n "${IMAGE_PREFIX:-}" ]]; then
        docker compose "${files[@]}" pull
        docker compose "${files[@]}" up -d   # БЕЗ --build
    elif [[ -n "$no_cache" ]]; then
        docker compose "${files[@]}" build --no-cache
        docker compose "${files[@]}" up -d
    else
        docker compose "${files[@]}" up -d --build
    fi
}
```

5b. `update_production()` (стр. 1167-1178): убрать дублирующий `docker compose pull` (теперь `run_compose` сам решит). Поправить prose в echo (стр. 1137) под новое поведение.

5c. Функция записи `.env` (стр. 265-317 heredoc): добавить `IMAGE_PREFIX=` и `IMAGE_TAG=latest` в шаблон.

5d. В меню пункт «6. Обновить Production» — оставить как есть, но убедиться что prose корректно описывает новый флоу.

## Этап 6 — Документация

**6a. `docs/deploy.md`:**
- §6 (стр. 141-147): убрать альтернативу pull/build, зафиксировать pull-flow для прода; добавить «для dev — `IMAGE_PREFIX=` пустая». Исправить дублированный заголовок `## 6.` (стр. 137/139).
- §10 (стр. 217-231) — **главное изменение**:
  - Update: `git pull` → правка `IMAGE_TAG` в `.env` (или оставить `latest`) → `docker compose pull` → `up -d`. Убрать `docker compose build` для прода.
  - Rollback: **исправить сломанный флоу**. Сейчас `git checkout v1.(x-1).x` + `up -d` не меняет образ. Новая процедура: `IMAGE_TAG=sha-<старый>` в `.env` → `pull` → `up -d`. Добавить явный блок про откат миграций (`alembic downgrade`) и предупреждение про необратимые миграции 008→024.

**6b. `README.md`:**
- Стр. 58-63 (Production): убрать `--build`, добавить про `IMAGE_PREFIX`/`IMAGE_TAG` в `.env` и `setup.sh`.
- Стр. 89-94 (Staging): аналогично.
- Стр. 107-109 (Update): `git pull` + `docker compose up -d` (pull внутри), без `--build`.

**6c. `docs/adr.md`:** добавить **ADR-045 «CI-built images in GHCR + pull-based deploy»** — обоснование выбора GHCR (бесплатно для публичного репо), тегирования по SHA, почему postgres тоже в registry, миграционный путь с локальной сборки на pull.

**6d. `AGENTS.md`:** обновить строку про `setup.sh` и мониторинг-секцию, если они упоминают сборку. Раздел «Перед коммитом» — без изменений (не влияет).

## Этап 7 — Валидация

7a. Статическая проверка compose после правок:
```bash
IMAGE_PREFIX= IMAGE_TAG=latest docker compose config >/dev/null   # локальный режим
IMAGE_PREFIX=ghcr.io/veryshuu/ IMAGE_TAG=test docker compose config >/dev/null   # registry-режим
```
Оба должны проходить без ошибок интерполяции.

7b. `shellcheck setup.sh` (CI уже гоняет shellcheck — пройдёт локально).

7c. `npm run i18n:check` — не затрагивается, но прогоню для целостности.

7d. Локальный smoke: `IMAGE_PREFIX= docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` поднимается (dev-путь не сломан).

---

## Что НЕ делаем
- Не трогаем workflow security.yml/nightly-* (они сканируют файловую систему, не образы).
- Не меняем `compose-smoke` job — он остаётся gate'ом, билдит локально (как сейчас), не пушит.
- Не вводим signed images (cosign) — overkill для публичного интранет-портала, можно добавить позже.
- Не переписываем всю `setup.sh` — только точечные правки в 3 функциях.

## Риски / грабли
- **Backend-образ один на 3 сервиса** — имя `portal-backend` шарится. Если в будущем backend/worker разойдутся по образам, придётся разделять.
- **`compose-smoke` билдит локально** → publish-job тоже билдит (дубль). Это намеренно: smoke — это gate, publish — это публикация. Дубль ~2 мин, не критично. Альтернатива — передавать артефакт между job'ами, но это сложнее и хрупче.
- **GHCR: первый пуш создаёт package** — по умолчанию приватный. Нужно будет после первого релиза зайти на github.com/users/VeryShuu/packages и переключить `portal-*` пакеты в public (иначе pull с прода без auth упадёт). Отражу в ADR-045.
- **Force-pull на проде без `.env` правки** — если забыть обновить `IMAGE_TAG`, `pull` вытянет тот же `latest`. Это фича, не баг, но в docs явно напишу про откат через SHA.