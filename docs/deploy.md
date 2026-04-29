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
5. Получить `client_secret` → в `.env::KEYCLOAK_CLIENT_SECRET`.

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

---

## 4. Заполнение `.env`

```bash
cp .env.example .env
# Открыть .env и заполнить:
```

Обязательные:
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY` (≥32 симв.) — сгенерировать через `openssl rand -base64 32`.
- `DATABASE_URL`, `REDIS_URL` — синхронизировать пароли с предыдущим пунктом.
- `KEYCLOAK_URL`, `KEYCLOAK_CLIENT_SECRET`.
- `NEXTCLOUD_URL`, `NC_SERVICE_USERNAME=portal-svc`, `NC_SERVICE_APP_PASSWORD`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`.
- `PORTAL_BASE_URL=https://<portal-host>`.
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — для bootstrap первого admin'а (применяется один раз).

Рекомендуемые:
- `SENTRY_DSN` — error tracking.
- `METRICS_TOKEN` — bearer для `/metrics` (если выставлен — требуется в Prometheus scrape config).
- `MAX_UPLOAD_SIZE_MB=100`.

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
- `https://<portal-host>/api/v1/ready` → `200` (БД + Redis + NC OK) либо `503`.

Вход: `https://<portal-host>/login` → `ADMIN_EMAIL`/`ADMIN_PASSWORD` → **сразу сменить пароль в профиле**.

---

## 7. Бэкапы

| Что | Куда | Периодичность |
|-----|------|---------------|
| `base_data/postgres` | offsite (S3 / corporate backup) | ежедневно (`pg_dump`) |
| `upload_data/` | offsite | ежедневно |
| `system_data/secrets`, `.env` | secret-manager (не в git!) | при изменении |
| Audit-партиции `audit_log_YYYY_MM` | холодное хранилище | старше 12 мес. |

Скрипт `pg_dump` (пример):
```bash
docker compose exec -T postgres \
  pg_dump -U portal -Fc portal > "backups/portal_$(date +%F).dump"
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
- `/api/v1/ready` != 200 за 2 мин.
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
4. `NC_SERVICE_APP_PASSWORD` — пересоздать App Password в Nextcloud, обновить `.env`.
5. `KEYCLOAK_CLIENT_SECRET` — Regenerate в Keycloak admin.

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

⚠️ Перед обновлением — снять бэкап Postgres. Миграции 008→020 необратимые
без потери данных (kb_versions, photo_*, file_*).

---

## 11. Troubleshooting

| Симптом | Проверка | Решение |
|---------|----------|---------|
| 502 от nginx | `docker compose logs backend` | Проверить `/api/v1/ready`; чаще всего — недоступен Postgres/Redis/NC |
| Cookies не сохраняются после OIDC | DevTools → Network → `Set-Cookie` | `SameSite=Lax`, не `Strict`; домен совпадает с `PORTAL_BASE_URL` |
| FTS-поиск пустой | `psql -c "SELECT * FROM pg_ts_config"` | Нет `russian_hunspell` — проверить `postgres/Dockerfile` (apt `hunspell-ru`) |
| Collabora не открывается | DevTools console + NC logs | `frame-ancestors` блокирует iframe → portal использует `window.open` |
| Upload 413 | nginx `client_max_body_size` | Увеличить в `system_data/nginx/nginx.conf`, согласовать с `MAX_UPLOAD_SIZE_MB` |

