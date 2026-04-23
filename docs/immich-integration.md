# Интеграция Immich — Фотогалерея

## Обзор

[Immich](https://github.com/immich-app/immich) — self-hosted решение для хранения и управления фотографиями и видео (аналог Google Photos). 98k+ GitHub stars, активная разработка, лицензия **AGPL-3.0**.

Immich разворачивается как **отдельный сервис** рядом со стеком портала. Портал интегрируется с ним через:
- SSO (Keycloak OIDC) — единый вход без повторной авторизации
- Ярлык в панели сервисов с SSO-пробросом
- Виджет "Последние фото" на главной странице (через Immich REST API)

> Immich **не встраивается через iframe** и не переписывается — используется его родной веб-интерфейс (Svelte).

---

## Сценарии использования

| Тип | Кто создаёт | Кто видит |
|---|---|---|
| Корпоративные события / офис | editor, admin | Все сотрудники (через виджет и Immich) |
| Личные альбомы сотрудника | Каждый пользователь | Только владелец + ручной шеринг |
| Shared корпоративный альбом | admin | Все (настраивается в Immich Shared Albums) |

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│  Браузер пользователя                                            │
│                                                                  │
│  Портал (Vue 3)          Immich Web UI (Svelte)                  │
│  ┌─────────────────┐     ┌──────────────────────┐               │
│  │  Главная страница│     │  /photos/            │               │
│  │  [PhotosWidget] │     │  (отдельное приложение│               │
│  └────────┬────────┘     └──────────────────────┘               │
└───────────┼──────────────────────────────────────────────────────┘
            │ GET /api/v1/photos/recent
┌───────────▼──────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                               │
│                                                                  │
│  GET /api/v1/photos/recent  ──────────────────────────────────┐  │
│  GET /api/v1/photos/thumbnail/{asset_id}  ────────────────┐   │  │
└──────────────────────────────────────────────────────────┼─┼──┘
                                                           │ │
┌──────────────────────────────────────────────────────────▼─▼──┐
│  Immich (Docker: immich-server:2283)                           │
│                                                                │
│  REST API (/api/albums, /api/assets, /api/assets/:id/thumbnail)│
│  OAuth OIDC → Keycloak                                         │
└────────────────────────────────┬───────────────────────────────┘
                                 │ OIDC
┌────────────────────────────────▼───────────────────────────────┐
│  Keycloak (единый IdP)                                         │
└────────────────────────────────────────────────────────────────┘
```

---

## Блок 1: Docker Compose

Immich добавляется в `docker-compose.yml` отдельным блоком с **собственными** PostgreSQL и Redis (несовместимы с порталом из-за расширения `pgvecto.rs`).

```yaml
# docker-compose.yml — добавить к существующим сервисам

services:

  immich-server:
    image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION:-release}
    container_name: immich-server
    restart: unless-stopped
    env_file: .env
    environment:
      DB_HOSTNAME: immich-postgres
      DB_USERNAME: ${IMMICH_DB_USERNAME:-immich}
      DB_PASSWORD: ${IMMICH_DB_PASSWORD}
      DB_DATABASE_NAME: ${IMMICH_DB_NAME:-immich}
      REDIS_HOSTNAME: immich-redis
    volumes:
      - ${IMMICH_UPLOAD_LOCATION:-./data/immich}:/usr/src/app/upload
    depends_on:
      - immich-postgres
      - immich-redis
    networks:
      - internal
    # НЕ публикуем порт наружу — только через Nginx

  immich-machine-learning:
    image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION:-release}
    container_name: immich-ml
    restart: unless-stopped
    volumes:
      - immich-model-cache:/cache
    networks:
      - internal
    # Отключить если AI-поиск не нужен (экономия ~2 ГБ RAM):
    # profiles: ["ml"]

  immich-postgres:
    image: ghcr.io/immich-app/postgres:14-vectorchord0.3.0-pgvectors0.2.0
    container_name: immich-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${IMMICH_DB_USERNAME:-immich}
      POSTGRES_PASSWORD: ${IMMICH_DB_PASSWORD}
      POSTGRES_DB: ${IMMICH_DB_NAME:-immich}
    volumes:
      - immich-db-data:/var/lib/postgresql/data
    networks:
      - internal

  immich-redis:
    image: redis:7-alpine
    container_name: immich-redis
    restart: unless-stopped
    networks:
      - internal

volumes:
  immich-db-data:
  immich-model-cache:
```

**Nginx** — добавить location для Immich:

```nginx
location /photos/ {
    # Immich не поддерживает sub-path — роутим как отдельный (суб)домен
    # Вариант 1: subdomain photos.portal.company.local → immich-server:2283
    # Вариант 2: отдельный server block на том же хосте
    proxy_pass http://immich-server:2283/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    client_max_body_size 50000M;
    proxy_request_buffering off;
    proxy_read_timeout 600s;
}
```

> ⚠️ **Ограничение Immich**: не поддерживает `location /subpath/` (sub-path). Рекомендуется отдельный server block или поддомен: `photos.portal.company.local`.

---

## Блок 2: SSO через Keycloak

### 2.1 Настройка клиента в Keycloak

1. Realm: тот же что у портала
2. Clients → Create → **immich**
3. Настройки:

```
Client Type:            OpenID Connect
Client Authentication:  ON  (Confidential)
Authorization:          OFF
Standard Flow:          ON
Redirect URIs:
  https://photos.portal.company.local/auth/login
  https://photos.portal.company.local/user-settings
Web Origins:
  https://photos.portal.company.local
```

4. Clients → immich → **Client Scopes** → добавить `email`, `profile`

5. Clients → immich → **Mappers** → Create mapper:
   - Name: `immich_role`
   - Mapper type: User Attribute / Hardcoded Role
   - Token Claim Name: `immich_role`
   - Claim Value: `user` (для обычных пользователей)
   - Для admin — отдельное правило через Client Roles

### 2.2 Настройка OAuth в Immich

Administration → Settings → OAuth:

| Параметр | Значение |
|---|---|
| **Enabled** | `true` |
| **Issuer URL** | `https://keycloak.company.local/realms/portal` |
| **Client ID** | `immich` |
| **Client Secret** | *(из Keycloak → Clients → immich → Credentials)* |
| **Scope** | `openid email profile` |
| **Signing Algorithm** | `RS256` |
| **Storage Label Claim** | `preferred_username` |
| **Role Claim** | `immich_role` |
| **Button Text** | `Войти через корпоративный портал` |
| **Auto Register** | `true` *(пользователь создаётся автоматически при первом входе)* |
| **Auto Launch** | `true` *(пропускает страницу логина Immich → сразу на Keycloak)* |

**Результат**: пользователь кликает ярлык → попадает в Immich уже залогиненным.

---

## Блок 3: Ярлык в панели сервисов

INSERT в таблицу `service_links` (или через Admin UI портала):

```sql
INSERT INTO service_links (name, url, icon, category, supports_sso, description, is_active)
VALUES (
    'Фотогалерея',
    'https://photos.portal.company.local/auth/login?autoLaunch=1',
    'photo-film',
    'Корпоративные сервисы',
    true,
    'Корпоративный фотоархив — события, команды, офис',
    true
);
```

Параметр `?autoLaunch=1` — Immich немедленно делает redirect на Keycloak, пропуская свою страницу логина.

---

## Блок 4: Backend — проксирование Immich API

Создаётся сервисный API-ключ в Immich (Administration → API Keys → Create) и прописывается в `.env`.

Новый роутер `backend/app/api/photos.py`:

```python
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import httpx

from app.core.config import settings
from app.api.deps import get_current_user

router = APIRouter(prefix="/photos", tags=["photos"])

IMMICH_HEADERS = {"x-api-key": settings.IMMICH_API_KEY}


@router.get("/recent")
async def get_recent_photos(
    limit: int = Query(8, ge=1, le=32),
    _user=Depends(get_current_user),
):
    """Последние фото из корпоративного альбома для виджета главной страницы."""
    async with httpx.AsyncClient(base_url=settings.IMMICH_URL, timeout=10) as client:
        r = await client.get(
            f"/api/albums/{settings.IMMICH_CORP_ALBUM_ID}",
            headers=IMMICH_HEADERS,
            params={"withoutAssets": False},
        )
        r.raise_for_status()
        album = r.json()

    assets = album.get("assets", [])
    assets.sort(key=lambda a: a.get("fileCreatedAt", ""), reverse=True)

    return {
        "album_name": album.get("albumName"),
        "total": album.get("assetCount", 0),
        "items": [
            {
                "id": a["id"],
                "thumbnail_url": f"/api/v1/photos/thumbnail/{a['id']}",
                "type": a.get("type", "IMAGE"),
                "created_at": a.get("fileCreatedAt"),
                "original_filename": a.get("originalFileName"),
            }
            for a in assets[:limit]
        ],
        "immich_url": settings.IMMICH_PUBLIC_URL,
        "album_url": f"{settings.IMMICH_PUBLIC_URL}/albums/{settings.IMMICH_CORP_ALBUM_ID}",
    }


@router.get("/thumbnail/{asset_id}")
async def proxy_thumbnail(
    asset_id: str,
    size: str = Query("thumbnail", regex="^(thumbnail|preview)$"),
    _user=Depends(get_current_user),
):
    """Проксирует thumbnail из Immich (избегает CORS, Immich остаётся во внутренней сети)."""
    async with httpx.AsyncClient(base_url=settings.IMMICH_URL, timeout=10) as client:
        r = await client.get(
            f"/api/assets/{asset_id}/thumbnail",
            headers=IMMICH_HEADERS,
            params={"size": size},
        )
        r.raise_for_status()

    return StreamingResponse(
        content=r.aiter_bytes(),
        media_type=r.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

Регистрация в `backend/app/main.py`:
```python
from app.api import photos
app.include_router(photos.router, prefix="/api/v1")
```

---

## Блок 5: Frontend — виджет PhotosWidget.vue

Компонент для главной страницы (`src/components/widgets/PhotosWidget.vue`):

```vue
<template>
  <div class="photos-widget">
    <div class="widget-header">
      <h3>{{ t('photos.title') }}</h3>
      <a :href="galleryUrl" target="_blank" rel="noopener" class="see-all">
        {{ t('photos.see_all') }} →
      </a>
    </div>

    <div v-if="loading" class="photo-grid">
      <n-skeleton v-for="i in 8" :key="i" height="120px" />
    </div>

    <div v-else-if="items.length" class="photo-grid">
      <a
        v-for="item in items"
        :key="item.id"
        :href="galleryUrl"
        target="_blank"
        rel="noopener"
        class="photo-cell"
      >
        <img
          :src="item.thumbnail_url"
          :alt="item.original_filename"
          loading="lazy"
        />
        <span v-if="item.type === 'VIDEO'" class="video-badge">▶</span>
      </a>
    </div>

    <n-empty v-else :description="t('photos.empty')" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSkeleton, NEmpty } from 'naive-ui'
import { api } from '@/api'

const { t } = useI18n()

interface PhotoItem {
  id: string
  thumbnail_url: string
  type: 'IMAGE' | 'VIDEO'
  created_at: string
  original_filename: string
}

const loading = ref(true)
const items = ref<PhotoItem[]>([])
const galleryUrl = ref('#')

onMounted(async () => {
  try {
    const data = await api.get('/photos/recent', { params: { limit: 8 } })
    items.value = data.items
    galleryUrl.value = data.album_url
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.photos-widget { }

.widget-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.photo-cell {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 6px;
}

.photo-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s;
}

.photo-cell:hover img { transform: scale(1.05); }

.video-badge {
  position: absolute;
  bottom: 4px;
  left: 4px;
  background: rgba(0,0,0,.6);
  color: #fff;
  font-size: 10px;
  padding: 2px 5px;
  border-radius: 4px;
}
</style>
```

---

## Блок 6: Переменные окружения

Добавить в `.env.example`:

```env
# ── Immich ────────────────────────────────────────────────────
# Версия образа (https://github.com/immich-app/immich/releases)
IMMICH_VERSION=release

# Директория хранения загруженных фото/видео
IMMICH_UPLOAD_LOCATION=./data/immich

# БД Immich (отдельный PostgreSQL, несовместим с порталом из-за pgvecto.rs)
IMMICH_DB_USERNAME=immich
IMMICH_DB_PASSWORD=changeme_immich_db

# URL Immich для backend (внутренний Docker)
IMMICH_URL=http://immich-server:2283

# URL Immich для пользователей (публичный, в браузере)
IMMICH_PUBLIC_URL=https://photos.portal.company.local

# API-ключ сервисного аккаунта (Admin → API Keys → Create)
IMMICH_API_KEY=

# UUID корпоративного shared-альбома для виджета главной страницы
# Получить после создания альбома: GET /api/albums → найти по названию
IMMICH_CORP_ALBUM_ID=
```

Добавить в `backend/app/core/config.py`:

```python
# Immich
IMMICH_URL: str = "http://immich-server:2283"
IMMICH_PUBLIC_URL: str = ""
IMMICH_API_KEY: str = ""
IMMICH_CORP_ALBUM_ID: str = ""
```

---

## Блок 7: Настройка корпоративного альбома

После первого запуска Immich:

1. Войти в Immich как admin (через Keycloak SSO)
2. **Albums → Create Album** → название "Корпоративный архив"
3. **Share Album** → выбрать всех пользователей (или группу)
4. Получить UUID альбома из URL: `https://photos.../albums/{UUID}` → вписать в `IMMICH_CORP_ALBUM_ID`
5. Создать API-ключ: Administration → API Keys → Create → вписать в `IMMICH_API_KEY`

---

## Блок 8: Тесты

### Unit (pytest)
```python
# backend/tests/unit/test_photos_service.py
async def test_recent_photos_returns_sorted_by_date(httpx_mock):
    httpx_mock.add_response(
        url=f"{settings.IMMICH_URL}/api/albums/{settings.IMMICH_CORP_ALBUM_ID}",
        json={"albumName": "Test", "assetCount": 2, "assets": [
            {"id": "b", "fileCreatedAt": "2026-01-01T10:00:00", "type": "IMAGE"},
            {"id": "a", "fileCreatedAt": "2026-01-02T10:00:00", "type": "IMAGE"},
        ]}
    )
    result = await get_recent_photos_service(limit=8)
    assert result["items"][0]["id"] == "a"  # новее — первый

async def test_thumbnail_proxy_sets_cache_header(httpx_mock, authed_client):
    httpx_mock.add_response(
        url=re.compile(r".*/api/assets/.*/thumbnail"),
        content=b"fake-jpeg",
        headers={"content-type": "image/jpeg"},
    )
    r = await authed_client.get("/api/v1/photos/thumbnail/test-uuid")
    assert r.status_code == 200
    assert "max-age=3600" in r.headers["cache-control"]

async def test_recent_photos_requires_auth(client):
    r = await client.get("/api/v1/photos/recent")
    assert r.status_code == 401
```

### E2E (Playwright)
```typescript
// frontend/e2e/photos-widget.spec.ts
test('photos widget shows on homepage', async ({ page }) => {
  await loginAsUser(page)
  await page.goto('/')
  await expect(page.locator('.photos-widget')).toBeVisible()
})

test('photo link opens immich in new tab', async ({ page, context }) => {
  await loginAsUser(page)
  await page.goto('/')
  const [newPage] = await Promise.all([
    context.waitForEvent('page'),
    page.locator('.photo-cell').first().click(),
  ])
  await expect(newPage.url()).toContain(process.env.IMMICH_PUBLIC_URL)
})
```

---

## Требования к серверу

| Ресурс | Минимум (без ML) | Рекомендуется (с ML) |
|---|---|---|
| RAM | +2 ГБ | +6 ГБ |
| CPU | +1 core | +2 core |
| Диск | По объёму фото | По объёму фото |

> Сервис `immich-machine-learning` (AI-поиск лиц/объектов) — опциональный. Если не нужен — закомментировать в `docker-compose.yml`, RAM падает до ~2 ГБ.

---

## Ограничения и особенности

| Пункт | Описание |
|---|---|
| **Лицензия AGPL-3.0** | Self-hosted, исходный код открыт. Коммерческое SaaS-использование требует отдельной лицензии. Для корпоративного интранета проблем нет. |
| **Нет sub-path** | Immich не работает на `/subpath/` — нужен отдельный server block или поддомен |
| **Отдельный PostgreSQL** | `pgvecto.rs` расширение несовместимо с основной БД портала |
| **Права на альбомы** | Управляются в Immich UI, не синхронизируются с AD-группами (только вручную) |
| **Синхронизация пользователей** | Auto Register создаёт пользователя при первом входе; Keycloak claims маппятся на профиль |
| **Токены** | Immich хранит свои сессии независимо от портала; Single Logout не поддерживается автоматически |
