# Production deployment checklist

> **Когда читать:** production-развёртывание, TLS, бэкапы, ротация секретов.
> **Ключевой код:** `docker-compose.yml`, `nginx/`, `setup.sh`.
> **ADR:** 032, 036, 037, 038.

Развёртывание Portal во внутренней сети / VPN. Документ описывает минимально
необходимый набор шагов и параметров для рабочего инстанса.

---

## 1. Требования к инфраструктуре

### Хост
- Linux x86_64, 4 vCPU, 8 GB RAM, 50 GB SSD (минимум).
- Docker 24+ и Docker Compose v2.
- Часовой пояс `Europe/Moscow` (или указать через `TZ` в `.env`).

### Внешние сервисы (поднимаются отдельно — не в этом compose)
| Сервис | Назначение | Минимальная версия |
|--------|------------|--------------------|
| **Keycloak** | OIDC IdP (PKCE), Admin API | 22+ |
| **Nextcloud** | Файлохранилище через WebDAV + Collabora WOPI | 28+ |
| **Collabora Online** | Редактор документов (встроен в Nextcloud) | 23+ |
| **Postfix / SMTP relay** | Отправка email-уведомлений | — |

### Сеть
- Публикация UI/API через nginx-сервис (порты 80/443) только во внутреннюю сеть / VPN.
- IP-whitelist на уровне nginx (geo-блок) — см. `system_data/nginx/nginx.conf`.
- **Исходящие соединения (CSP `connect-src`)** — фронт должен иметь возможность напрямую обращаться к:
  - `https://api.open-meteo.com` — погода для виджета «Время в городах»;
  - `https://geocoding-api.open-meteo.com` — поиск координат города в `/settings`.

  Эти домены прописаны в `nginx/render-config.sh::CSP`. Если корпоративный egress-firewall блокирует open-meteo.com — виджет продолжит показывать время, но без иконок/температуры (graceful degradation, см. ADR-038). При добавлении новых внешних API правьте `connect-src` и перезапускайте `nginx-config` и `nginx`.

---

## 2. Конфигурация Keycloak

1. Создать realm (`portal`).
2. Создать клиента:
   - Client type: OpenID Connect
   - Authentication: ON
   - Standard flow: ON, Direct access grants: OFF
   - Valid Redirect URIs: `https://<portal-host>/auth/callback`
   - Web Origins: `https://<portal-host>`
   - PKCE: S256
3. В `Client scopes` добавить mappers для claims: `email`, `given_name`, `family_name`, `department`, `job_title`, `phone`, `groups`.
4. Создать service-account роль `portal-admin` (для `/admin/keycloak-admin/*`):
   - Realm-management: `manage-users`, `view-users`, `query-users`, `manage-realm` (или подмножество).
5. Получить `client_secret` → сохранить в Admin UI портала («Настройки → Keycloak → Client Secret»). Env-переменные `KEYCLOAK_*` не используются (ADR-037) — все параметры Keycloak задаются через UI и хранятся в `/data/secrets/keycloak-settings.json`.

---

## 3. Конфигурация Nextcloud (service account)

Portal **никогда** не использует JWT пользователя для NC.
Все файловые операции идут через единый service account `portal-svc` (см. ADR-032).

1. Создать пользователя `portal-svc` в Nextcloud.
2. В Settings → Security сгенерировать **App Password** для `portal-svc` →
   сохранить в Admin UI портала («Модули → Nextcloud → Service App Password»). Переменная `NC_SERVICE_APP_PASSWORD` в `.env` не используется — настройка хранится в `/data/settings/system.json` и применяется без рестарта (см. ADR-037).
3. Создать корневую папку `PortalFiles` (или указать другую через `NC_FILES_ROOT`).
4. Установить app `richdocuments` (Collabora) и `files_sharing` (есть из коробки).
5. CSP `frame-ancestors` для портала: см. `trb.md` — Collabora открывается через
   `window.open(_blank)`, а не iframe.
6. **Добавить хост портала в `gs.trustedHosts`** — иначе курсоры в Collabora
   будут подписаны как «Анонимный пользователь» (NC silently отклоняет
   federation-callback, см. `docs/integration-keycloak-nextcloud.md` §3.3):
   ```bash
   docker compose exec --user www-data nextcloud \
       php occ config:system:set gs.trustedHosts 0 --value="<portal-host>"
   ```

---

## 4. Заполнение `.env`

```bash
cp .env.example .env
# Открыть .env и заполнить:
```

Обязательные (только bootstrap, см. ADR-037):
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY` (≥32 симв.) — сгенерировать через `openssl rand -base64 32`.
- `DATABASE_URL`, `REDIS_URL` собираются автоматически в `docker-compose.yml` из паролей выше.
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — bootstrap первого admin'а (применяется один раз).

После первого запуска войти через `/auth/local` под bootstrap-админом и в Admin UI настроить:
- **Keycloak** (URL, realm, client_id, client_secret, sync-credentials) — раздел «Keycloak».
- **Nextcloud** (URL, service username, app password, files root) — раздел «Модули → Nextcloud».
- **Системные** (`PORTAL_BASE_URL`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_CIDR`, SMTP, `METRICS_TOKEN`, `LOG_LEVEL`, `PROMETHEUS_METRICS_ENABLED`, `ARQ_MAX_JOBS`) — раздел «Системные».

Все эти параметры хранятся в `/data/settings/system.json` и `/data/secrets/keycloak-settings.json` и меняются без рестарта контейнеров.

---

## 5. TLS-сертификаты

```bash
mkdir -p system_data/certs
# Положить:
#   system_data/certs/portal.crt
#   system_data/certs/portal.key
chmod 600 system_data/certs/portal.key
```

Для prod — выпустить через корпоративный CA / Let's Encrypt (если домен резолвится).
Для dev — self-signed (`openssl req -x509 ...`).

### Russian Trusted Root CA (для исходящих TLS к российским endpoint'ам)

Если включён модуль **Helpdesk → MAX-messenger** (`helpdesk_max_bot_settings.enabled=true`),
бэкенд ходит по TLS на `*.max.ru`, чей сертификат подписан `Russian Trusted Root CA`
(Минцифры) — этот корневой сертификат **отсутствует** в Mozilla CA Bundle / `certifi`
и без доустановки даёт `[SSL: CERTIFICATE_VERIFY_FAILED]`.

Решение уже вшито в Docker-образ `backend`:
- Сертификат лежит в репозитории: `backend/certs/russian_trusted_root_ca.crt`
  (расширение **обязательно `.crt`** — `update-ca-certificates` игнорирует `.pem`/`.cer`).
- В `backend/Dockerfile` stages `runtime-base` и `production` вызывается
  `update-ca-certificates`, и сертификат попадает в системный trust store
  (`/etc/ssl/certs/ca-certificates.crt`).
- В `services/max_messenger/_client.py` httpx создаётся с
  `verify=ssl.create_default_context()` — это заставляет httpx читать **системный**
  trust store, а не свой `certifi.where()`.

Это общий фикс: теперь любой российский TLS-endpoint (Госуслуги, Сбер, MAX и т.д.) с
сертификатом Минцифры работает из контейнера автоматически. Если при добавлении
нового endpoint'а получаете `CERTIFICATE_VERIFY_FAILED` — проверьте, что образ
собран свежим (с сертификатом в `backend/certs/`).

---

## 6. Первый запуск

Режим образов задаётся в `.env` переменными `IMAGE_PREFIX` и `IMAGE_TAG` (см. ADR-045):

- **`IMAGE_PREFIX=ghcr.io/veryshuu/`** (прод) — pull готовых CI-образов из GitHub Container Registry. Сервер не компилирует, откат = сменить `IMAGE_TAG` на short-SHA.
- **`IMAGE_PREFIX=` пусто** (dev/staging) — локальная сборка образов из исходников.

### 6.1 Запуск с готовыми образами из registry (прод)

```bash
# .env: IMAGE_PREFIX=ghcr.io/veryshuu/  и IMAGE_TAG=latest (или sha-XXXXXXX)
docker compose pull
docker compose up -d
docker compose logs -f migrations    # дождаться "Done" / exit code 0
docker compose ps                    # все сервисы должны быть Up / healthy
```

### 6.2 Запуск с локальной сборкой (dev/staging)

```bash
# .env: IMAGE_PREFIX=  (пусто)
docker compose up -d --build
docker compose logs -f migrations    # дождаться "Done" / exit code 0
docker compose ps                    # все сервисы должны быть Up / healthy
```

Порядок старта:
1. `postgres` (healthy) → `redis` (healthy)
2. `screenshot-service` (healthy) + `nginx-config` (healthy) — запускаются параллельно
3. `migrations` (одноразовый init-job, `alembic upgrade head`)
4. `backend` + `worker` (после `migrations` exit 0)
5. `frontend`
6. `nginx` (после `backend`, `frontend`, `nginx-config`)

Healthcheck:
- `https://<portal-host>/health` → `200 OK {"status":"ok"}`
- `https://<portal-host>/ready` → `200` (БД + Redis + NC OK) либо `503`.

Bootstrap-вход первого админа: `https://<portal-host>/auth/local` → `ADMIN_EMAIL`/`ADMIN_PASSWORD` → **сразу сменить пароль в профиле**. Маршрут `/auth/local` — backdoor для локальных админов и DevOps, в публичном UI ссылок на него нет; обычные сотрудники попадают на главную через auto-SSO. См. ADR-036.

---

## 7. Бэкапы

Резервное копирование выполняется **внешней инфраструктурой** (корпоративная backup-система).
Встроенного `pg-backup`-сервиса в `docker-compose.yml` нет — портал не управляет бэкапами.

Что должна включить инфраструктурная команда в свой backup-сценарий:

| Что | Комментарий |
|-----|-------------|
| `base_data/postgres` | основная БД (Postgres data dir) |
| `upload_data/` | пользовательские файлы: фото, KB-вложения, news media, аватары, branding |
| `system_data/secrets`, `system_data/settings`, `.env` | секреты и системные настройки (передавать в secret-manager, не в git) |
| Audit-партиции `audit_log_YYYY_MM` | холодное хранилище для записей старше 12 мес. |

Если требуется снять разовый дамп вручную перед обновлением:
```bash
docker compose exec -T postgres \
  pg_dump -U portal -Fc portal > "portal_$(date +%F).dump"
```

---

## 8. Мониторинг

- **Prometheus**: scrape `https://<portal-host>/metrics` (если выставлен `METRICS_TOKEN` —
  передать через `authorization: Bearer ...`).
- **Логи**: structlog → JSON в stdout → docker logs → агрегатор (Loki/ELK/Vector).
- Уровень `WARN+` отправлять в дежурный канал.

Ключевые алерты:
- HTTP 5xx rate > 1% за 5 мин.
- `/ready` != 200 за 2 мин.
- Backend container restart loop.
- Queue ARQ depth > 1000.
- Disk usage `/data/photos` > 85%.

---

## 9. Ротация секретов

Раз в 90 дней:
1. `SECRET_KEY` — сгенерировать новый, обновить в `.env`, перезапустить backend.
   ⚠️ Все активные Redis-сессии будут аннулированы — пользователи перелогинятся.
2. `POSTGRES_PASSWORD` — `ALTER USER portal WITH PASSWORD '...'` + обновить `.env` + `docker compose up -d`.
3. `REDIS_PASSWORD` — обновить `--requirepass` в compose + `.env` + перезапуск.
4. `NC_SERVICE_APP_PASSWORD` — пересоздать App Password в Nextcloud, обновить в Admin UI («Модули → Nextcloud»).
5. `KEYCLOAK_CLIENT_SECRET` — Regenerate в Keycloak admin, обновить в Admin UI («Настройки → Keycloak»).

---

## 10. Обновление до новой версии

> **Рекомендованный путь:** `bash setup.sh` → пункт «6. Обновить Production».
> Скрипт сам определяет режим (registry pull или локальная сборка) по `IMAGE_PREFIX`
> в `.env`, делает `git pull`, опциональный `pg_dump`, и `compose up -d` с проверкой
> миграций. Ниже — ручные процедуры для понимания и нестандартных случаев.

### 10.1 Обновление (registry pull — прод)

Каждый push в `main` собирает и публикует образы в GHCR: теги `sha-<7симв>` (точная
привязка к коммиту) и `latest` (указатель на HEAD main). См. ADR-045.

```bash
# 1. Обновить конфиг compose / миграции (нужны актуальные docker-compose.yml,
#    .env, alembic-файлы — миграции baked в образ, но compose/環境 живут в git).
git pull --ff-only

# 2. (Опционально) прицепить точный коммит вместо latest:
#    IMAGE_TAG=sha-abc1234 в .env  — иначе остаётся latest.

# 3. Pull новых образов + пересоздать контейнеры.
#    setup.sh сделает обе команды; вручную:
docker compose pull
docker compose up -d         # migrations отработают сами (one-shot сервис)
docker compose logs -f migrations
```

### 10.2 Обновление (локальная сборка — dev/staging)

```bash
# .env: IMAGE_PREFIX=  (пусто)
git pull --ff-only
docker compose up -d --build   # пересоберёт только изменившиеся образы
docker compose logs -f migrations
```

### 10.3 Откат

Откат образа — через `IMAGE_TAG` в `.env` (на проде), **не** через `git checkout`
(последний не меняет образ, который бежит из registry):

```bash
# 1. Узнать SHA предыдущего успешного CI-билда (вкладка Actions → publish-images).
# 2. Установить его в .env:
#    IMAGE_TAG=sha-abc1234
docker compose pull
docker compose up -d
docker compose logs -f migrations
```

⚠️ **Откат миграций БД** — отдельная операция, образ её не делает. Если новая версия
накатила миграцию, откат образа оставит схему опережающей:

```bash
# Откат одной миграции (в одноразовом контейнере из текущего образа):
docker compose run --rm migrations alembic downgrade -1
```

**Внимание:** миграции 008→024 необратимы без потери данных (kb_versions, photo_*,
file_*, fk-индексы). Перед откатом через эти ревизии — восстановить БД из дампа (§7),
это безопаснее ручного downgrade.

⚠️ Перед обновлением — убедиться, что инфраструктурный бэкап актуален (или снять
разовый `pg_dump`, см. §7).

---

## 11. Troubleshooting

| Симптом | Проверка | Решение |
|---------|----------|---------|
| 502 от nginx | `docker compose logs backend` | Проверить `/ready`; чаще всего — недоступен Postgres/Redis/NC |
| Cookies не сохраняются после OIDC | DevTools → Network → `Set-Cookie` | `SameSite=Lax`, не `Strict`; домен совпадает с `PORTAL_BASE_URL` |
| FTS-поиск пустой | `psql -c "SELECT * FROM pg_ts_config"` | Нет `russian_hunspell` — проверить `postgres/Dockerfile` (apt `hunspell-ru`) |
| Collabora не открывается | DevTools console + NC logs | `frame-ancestors` блокирует iframe → portal использует `window.open` |
| В Collabora все как «Анонимный пользователь» | NC log: `COOL-Federation-Source: ... is not a trusted server` | Добавить хост портала в `gs.trustedHosts` (см. §3 шаг 6); для уже открытых сессий — `./scripts/flush-nc-richdocuments-cache.sh` |
| Upload 413 | nginx `client_max_body_size` | Увеличить в `system_data/nginx/nginx.conf`, согласовать с `MAX_UPLOAD_SIZE_MB` |

