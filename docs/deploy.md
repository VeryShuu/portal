# Production deployment checklist

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
   в `.env::NC_SERVICE_APP_PASSWORD`.
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
- **Системные** (`PORTAL_BASE_URL`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_CIDR`, SMTP, `SENTRY_DSN`, `METRICS_TOKEN`, `LOG_LEVEL`, `PROMETHEUS_METRICS_ENABLED`, `ARQ_MAX_JOBS`) — раздел «Системные».

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

---

## 6. Первый запуск

```bash
docker compose pull          # если используете готовые образы из ghcr
docker compose build         # либо локальная сборка
docker compose up -d
docker compose logs -f migrations    # дождаться "Done" / exit code 0
docker compose ps            # все сервисы должны быть Up / healthy
```

Порядок старта:
1. `postgres` (healthy) → `redis` (healthy)
2. `migrations` (одноразовый init-job, `alembic upgrade head`)
3. `backend` + `worker` (после `migrations` exit 0)
4. `frontend`
5. `nginx`

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
- **Sentry**: задать `SENTRY_DSN` в `.env`.
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

```bash
git fetch --tags
git checkout v1.x.x
docker compose pull
docker compose build
docker compose up -d         # migrations отработают сами
docker compose logs -f migrations
```

Откат:
```bash
git checkout v1.(x-1).x
docker compose up -d
# при необходимости — alembic downgrade -1 в одноразовом контейнере
```

⚠️ Перед обновлением — убедиться, что инфраструктурный бэкап актуален (или
снять разовый `pg_dump`, см. §7). Миграции 008→024 необратимые без потери
данных (kb_versions, photo_*, file_*, fk-индексы).

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

