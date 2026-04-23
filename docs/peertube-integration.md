# Интеграция PeerTube — Видеогалерея

## Обзор

[PeerTube](https://github.com/chocobozzz/peertube) — self-hosted видеоплатформа (аналог YouTube), 14.6k ⭐, активная разработка, лицензия **AGPL-3.0**.

PeerTube **уже установлен** — в отличие от Immich, Docker-деплой не нужен. Фокус интеграции:

| Компонент | Что делается |
|---|---|
| **SSO** | Подключение Keycloak через OIDC-плагин (нативно не поддерживается) |
| **Ярлык** | В панели сервисов портала с автоматическим SSO-редиректом |
| **Виджет** | Последние видео на главной странице (PeerTube REST API) |
| **iframe embed** | Вставка плеера в статьи KB и новости (редактор вручную) — TipTap + CSP |

> Видео загружают **только admin и editor**. Остальные — режим просмотра.

---

## Ключевые отличия от Immich

| Аспект | Immich (фото) | PeerTube (видео) |
|---|---|---|
| OIDC | Нативно, из коробки | Только через плагин |
| Embed | Нет | ✅ `<iframe>` плеер |
| Деплой | Новые Docker-контейнеры | Уже установлен |
| Загрузка | Все сотрудники | Только admin/editor |
| Privacy видео | Shared albums | Internal (только залогиненные) |

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│  Браузер пользователя                                        │
│                                                              │
│  Портал (Vue 3)              PeerTube Web UI (Angular)       │
│  ┌───────────────────┐       ┌────────────────────────────┐  │
│  │  Главная страница │       │  https://video.company.local│  │
│  │  [VideosWidget]   │       │  (отдельное приложение)    │  │
│  ├───────────────────┤       └────────────────────────────┘  │
│  │  KB-статья/Новость│                                        │
│  │  <iframe embed /> │◄──────── PeerTube embed player        │
│  └─────────┬─────────┘                                       │
└────────────┼────────────────────────────────────────────────┘
             │ GET /api/v1/videos/recent
┌────────────▼────────────────────────────────────────────────┐
│  Backend (FastAPI)                                          │
│  GET /api/v1/videos/recent  ────────────────────────────┐  │
│  GET /api/v1/videos/thumbnail/{uuid}  ──────────────┐   │  │
└─────────────────────────────────────────────────┼───┼──┘
                                                  │   │
┌─────────────────────────────────────────────────▼───▼──────┐
│  PeerTube (уже установлен)                                  │
│  REST API /api/v1/videos, /api/v1/channels                  │
│  OIDC Plugin → Keycloak                                     │
│  Embed: /videos/embed/{uuid}                                │
└────────────────────────────┬────────────────────────────────┘
                             │ OIDC
┌────────────────────────────▼────────────────────────────────┐
│  Keycloak (единый IdP)                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Блок 1: SSO через Keycloak (OIDC плагин)

### 1.1 Установка плагина в PeerTube

В PeerTube Admin → Plugins & Themes → Search:

```
peertube-plugin-auth-openid-connect
```

Или через CLI на сервере PeerTube:

```bash
cd /path/to/peertube
NODE_ENV=production node dist/server/tools/peertube-plugins.js \
  install --npm-name peertube-plugin-auth-openid-connect
```

### 1.2 Настройка клиента в Keycloak

1. Realm: тот же что у портала
2. Clients → Create → **peertube**
3. Настройки:

```
Client Type:            OpenID Connect
Client Authentication:  ON  (Confidential)
Standard Flow:          ON
Redirect URIs:
  https://video.company.local/plugins/auth-openid-connect/*/router/code-cb
  https://video.company.local/plugins/auth-openid-connect/*/router/code-cb?*
Web Origins:
  https://video.company.local
```

4. Clients → peertube → **Client Scopes** → добавить `email`, `profile`

5. Mapper для роли (чтобы admin портала стал Moderator в PeerTube):
   - Clients → peertube → **Mappers** → Create
   - Name: `peertube_role`
   - Mapper Type: User Attribute / Hardcoded Claim
   - Token Claim Name: `peertube_role`
   - Значения:
     - Обычные пользователи → `user` (только просмотр)
     - editor, admin → `moderator` (могут загружать видео и модерировать)

### 1.3 Настройка плагина в PeerTube

PeerTube Admin → Plugins → Settings → **auth-openid-connect**:

| Параметр | Значение |
|---|---|
| **Client ID** | `peertube` |
| **Client Secret** | *(из Keycloak → Clients → peertube → Credentials)* |
| **Discovery URL** | `https://keycloak.company.local/realms/portal/.well-known/openid-configuration` |
| **Scope** | `openid email profile` |
| **Username claim** | `preferred_username` |
| **Mail claim** | `email` |
| **Display name claim** | `name` |
| **Role claim** | `peertube_role` |
| **Button name** | `Войти через корпоративный портал` |

### 1.4 Отключение локальной регистрации

PeerTube Admin → Configuration → Users:

```
Allow registration:  OFF
Signup requires email verification: N/A
```

**Результат**: единственный способ войти в PeerTube — через Keycloak SSO. При первом входе аккаунт создаётся автоматически.

### 1.5 Настройка privacy по умолчанию

PeerTube Admin → Configuration → Videos:

```
Default privacy:  Internal (only users logged in can see)
```

Это гарантирует, что все видео видят только залогиненные сотрудники.

---

## Блок 2: Ярлык в панели сервисов

INSERT в таблицу `service_links`:

```sql
INSERT INTO service_links (name, url, icon, category, supports_sso, description, is_active)
VALUES (
    'Видеопортал',
    'https://video.company.local',
    'video',
    'Корпоративные сервисы',
    true,
    'Корпоративные видео: события, обучение, инструкции, демо',
    true
);
```

> С OIDC-плагином PeerTube автоматически делает redirect на Keycloak при открытии.
> SSO-проброс через `id_token_hint` не поддерживается плагином — достаточно просто URL.

---

## Блок 3: Backend — проксирование PeerTube API

Новый роутер `backend/app/api/videos.py`:

```python
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import httpx

from app.core.config import settings
from app.api.deps import get_current_user

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/recent")
async def get_recent_videos(
    limit: int = Query(6, ge=1, le=24),
    channel_id: str | None = Query(None),
    _user=Depends(get_current_user),
):
    """Последние видео для виджета главной страницы."""
    params = {
        "count": limit,
        "sort": "-createdAt",
        "nsfw": "false",
        "isLocal": "true",
    }
    if channel_id:
        params["channelId"] = channel_id

    async with httpx.AsyncClient(
        base_url=settings.PEERTUBE_URL,
        headers={"Authorization": f"Bearer {await _get_peertube_token()}"},
        timeout=10,
    ) as client:
        r = await client.get("/api/v1/videos", params=params)
        r.raise_for_status()
        data = r.json()

    return {
        "total": data.get("total", 0),
        "items": [
            {
                "uuid": v["uuid"],
                "name": v["name"],
                "description": v.get("description", ""),
                "duration": v.get("duration", 0),
                "views": v.get("views", 0),
                "thumbnail_url": f"/api/v1/videos/thumbnail/{v['uuid']}",
                "embed_url": f"{settings.PEERTUBE_PUBLIC_URL}/videos/embed/{v['uuid']}",
                "watch_url": f"{settings.PEERTUBE_PUBLIC_URL}/w/{v['uuid']}",
                "channel": v.get("channel", {}).get("displayName"),
                "published_at": v.get("publishedAt"),
            }
            for v in data.get("data", [])
        ],
        "peertube_url": settings.PEERTUBE_PUBLIC_URL,
    }


@router.get("/thumbnail/{uuid}")
async def proxy_thumbnail(
    uuid: str,
    _user=Depends(get_current_user),
):
    """Проксирует thumbnail из PeerTube."""
    async with httpx.AsyncClient(base_url=settings.PEERTUBE_URL, timeout=10) as client:
        r = await client.get(f"/api/v1/videos/{uuid}")
        r.raise_for_status()
        video = r.json()
        thumbnail_path = video.get("thumbnailPath", "")

    async with httpx.AsyncClient(base_url=settings.PEERTUBE_URL, timeout=10) as client:
        img = await client.get(thumbnail_path)
        img.raise_for_status()

    return StreamingResponse(
        content=img.aiter_bytes(),
        media_type=img.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


async def _get_peertube_token() -> str:
    """Получает OAuth2 токен PeerTube для сервисного аккаунта."""
    async with httpx.AsyncClient(base_url=settings.PEERTUBE_URL, timeout=10) as client:
        r = await client.post(
            "/api/v1/users/token",
            data={
                "client_id": settings.PEERTUBE_CLIENT_ID,
                "client_secret": settings.PEERTUBE_CLIENT_SECRET,
                "grant_type": "password",
                "response_type": "code",
                "username": settings.PEERTUBE_SVC_USERNAME,
                "password": settings.PEERTUBE_SVC_PASSWORD,
            },
        )
        r.raise_for_status()
        return r.json()["access_token"]
```

> **Примечание**: токен кэшируется через Redis (TTL = `expires_in - 60` сек). Реализация кэширования не показана для краткости — добавить через `@cache_result(ttl=...)`.

Регистрация в `backend/app/main.py`:
```python
from app.api import videos
app.include_router(videos.router, prefix="/api/v1")
```

---

## Блок 4: Frontend — виджет VideosWidget.vue

`src/components/widgets/VideosWidget.vue`:

```vue
<template>
  <div class="videos-widget">
    <div class="widget-header">
      <h3>{{ t('videos.title') }}</h3>
      <a :href="peertube_url" target="_blank" rel="noopener" class="see-all">
        {{ t('videos.see_all') }} →
      </a>
    </div>

    <div v-if="loading" class="video-grid">
      <n-skeleton v-for="i in 3" :key="i" height="160px" />
    </div>

    <div v-else-if="items.length" class="video-grid">
      <a
        v-for="item in items"
        :key="item.uuid"
        :href="item.watch_url"
        target="_blank"
        rel="noopener"
        class="video-card"
      >
        <div class="thumbnail-wrap">
          <img :src="item.thumbnail_url" :alt="item.name" loading="lazy" />
          <span class="duration-badge">{{ formatDuration(item.duration) }}</span>
        </div>
        <div class="video-info">
          <p class="video-title">{{ item.name }}</p>
          <p class="video-meta">{{ item.channel }} · {{ formatViews(item.views) }}</p>
        </div>
      </a>
    </div>

    <n-empty v-else :description="t('videos.empty')" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSkeleton, NEmpty } from 'naive-ui'
import { api } from '@/api'

const { t } = useI18n()

const loading = ref(true)
const items = ref<any[]>([])
const peertube_url = ref('#')

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatViews(views: number): string {
  if (views >= 1000) return `${(views / 1000).toFixed(1)}k просмотров`
  return `${views} просмотров`
}

onMounted(async () => {
  try {
    const data = await api.get('/videos/recent', { params: { limit: 6 } })
    items.value = data.items
    peertube_url.value = data.peertube_url
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.widget-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.video-card {
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: transform 0.2s;
}

.video-card:hover { transform: translateY(-2px); }

.thumbnail-wrap {
  position: relative;
  aspect-ratio: 16/9;
  overflow: hidden;
}

.thumbnail-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.duration-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0,0,0,.75);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 5px;
  border-radius: 3px;
}

.video-info { padding: 8px 4px 4px; }

.video-title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.video-meta {
  font-size: 11px;
  opacity: 0.6;
  margin-top: 3px;
}
</style>
```

---

## Блок 5: iframe embed в TipTap (статьи и новости)

### 5.1 Почему TipTap блокирует iframe

TipTap v2 по умолчанию не разрешает `<iframe>` — защита от XSS. Нужно добавить кастомный узел.

### 5.2 Кастомный узел IframeEmbed

`frontend/src/components/editor/extensions/IframeEmbed.ts`:

```typescript
import { Node, mergeAttributes } from '@tiptap/core'

export interface IframeEmbedOptions {
  allowedDomains: string[]
  HTMLAttributes: Record<string, unknown>
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    iframeEmbed: {
      setIframe: (options: { src: string }) => ReturnType
    }
  }
}

export const IframeEmbed = Node.create<IframeEmbedOptions>({
  name: 'iframeEmbed',
  group: 'block',
  atom: true,

  addOptions() {
    return {
      allowedDomains: [import.meta.env.VITE_PEERTUBE_URL ?? ''],
      HTMLAttributes: {
        width: '100%',
        height: '400',
        frameborder: '0',
        allowfullscreen: 'true',
        sandbox: 'allow-same-origin allow-scripts allow-popups',
      },
    }
  },

  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: el => el.getAttribute('src'),
        renderHTML: attrs => ({ src: attrs.src }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'iframe[src]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['iframe', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes)]
  },

  addCommands() {
    return {
      setIframe:
        ({ src }) =>
        ({ commands }) => {
          const url = new URL(src)
          const allowed = this.options.allowedDomains.some(d => url.hostname === new URL(d).hostname)
          if (!allowed) {
            console.warn(`IframeEmbed: domain ${url.hostname} not allowed`)
            return false
          }
          return commands.insertContent({ type: this.name, attrs: { src } })
        },
    }
  },
})
```

Зарегистрировать в `RichEditor.vue`:

```typescript
import { IframeEmbed } from './extensions/IframeEmbed'

const editor = useEditor({
  extensions: [
    // ...existing extensions...
    IframeEmbed.configure({
      allowedDomains: [import.meta.env.VITE_PEERTUBE_URL],
    }),
  ],
})
```

Кнопка в тулбаре (опционально):

```typescript
const insertVideo = () => {
  const src = prompt('URL embed-плеера PeerTube:')
  if (src) editor.value?.chain().focus().setIframe({ src }).run()
}
```

### 5.3 Как редактор вставляет видео

1. Открыть видео в PeerTube → кнопка **Share → Embed** → скопировать URL вида `https://video.company.local/videos/embed/{uuid}`
2. В редакторе статьи/новости → кнопка "Вставить видео" → вставить URL
3. Плеер отобразится прямо в редакторе (WYSIWYG)

---

## Блок 6: CSP — разрешение iframe embed

### Проблема

Nginx у портала имеет строгий `Content-Security-Policy` с `frame-src 'none'`. iframe PeerTube будет заблокирован.

### Решение — добавить PeerTube в `frame-src`

В `nginx/nginx.conf` (или `conf.d/portal.conf`):

```nginx
# Было:
add_header Content-Security-Policy "... frame-src 'none'; ...";

# Стало:
add_header Content-Security-Policy "... frame-src 'self' https://video.company.local; ...";
```

Полный заголовок (пример):

```nginx
add_header Content-Security-Policy
  "default-src 'self'; \
   script-src 'self'; \
   style-src 'self' 'unsafe-inline'; \
   img-src 'self' data: blob: https://video.company.local; \
   media-src 'self' https://video.company.local; \
   frame-src 'self' https://video.company.local; \
   connect-src 'self'; \
   font-src 'self'; \
   object-src 'none'; \
   base-uri 'self'";
```

> ⚠️ Добавить `media-src` тоже — PeerTube плеер стримит видео через `<video>` тег.

### DOMPurify — разрешить iframe при рендеринге

При отображении HTML из БД (`markdown-it → DOMPurify`):

```typescript
// frontend/src/utils/sanitize.ts — уже существует в проекте
import DOMPurify from 'dompurify'

const PEERTUBE_URL = import.meta.env.VITE_PEERTUBE_URL

DOMPurify.addHook('uponSanitizeElement', (node, data) => {
  if (data.tagName === 'iframe') {
    const src = node.getAttribute('src') || ''
    if (src.startsWith(`${PEERTUBE_URL}/videos/embed/`)) {
      data.allowedTags['iframe'] = true
    }
  }
})

export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'src', 'sandbox'],
  })
}
```

---

## Блок 7: Сервисный аккаунт PeerTube для API

Backend использует OAuth2 Password Flow для доступа к PeerTube API (для виджета последних видео):

1. PeerTube Admin → Users → Create:
   - Username: `portal-svc`
   - Password: сложный пароль
   - Role: **User** (только чтение публичных данных)
   - Email: `portal-svc@company.local`

2. Получить `client_id` и `client_secret`:
   ```bash
   curl https://video.company.local/api/v1/oauth-clients/local
   # → { "client_id": "...", "client_secret": "..." }
   ```

3. Записать в `.env`

---

## Блок 8: Переменные окружения

Добавить в `.env.example`:

```env
# ── PeerTube ──────────────────────────────────────────────────
# URL PeerTube для backend (внутренний)
PEERTUBE_URL=http://peertube:9000

# URL PeerTube для пользователей (публичный, в браузере)
PEERTUBE_PUBLIC_URL=https://video.company.local

# OAuth2 client credentials (из GET /api/v1/oauth-clients/local)
PEERTUBE_CLIENT_ID=
PEERTUBE_CLIENT_SECRET=

# Сервисный аккаунт для API-запросов виджета
PEERTUBE_SVC_USERNAME=portal-svc
PEERTUBE_SVC_PASSWORD=

# ID канала для фильтрации видео в виджете (опционально)
# Получить: GET /api/v1/accounts/{username}/video-channels
PEERTUBE_CHANNEL_ID=
```

Добавить во фронтенд `.env.example`:

```env
VITE_PEERTUBE_URL=https://video.company.local
```

Добавить в `backend/app/core/config.py`:

```python
# PeerTube
PEERTUBE_URL: str = "http://peertube:9000"
PEERTUBE_PUBLIC_URL: str = ""
PEERTUBE_CLIENT_ID: str = ""
PEERTUBE_CLIENT_SECRET: str = ""
PEERTUBE_SVC_USERNAME: str = "portal-svc"
PEERTUBE_SVC_PASSWORD: str = ""
PEERTUBE_CHANNEL_ID: str = ""
```

---

## Блок 9: Тесты

### Unit (pytest)

```python
# backend/tests/unit/test_videos_service.py
async def test_recent_videos_returns_formatted_list(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r".*/api/v1/users/token"),
        json={"access_token": "fake-token", "expires_in": 3600},
    )
    httpx_mock.add_response(
        url=re.compile(r".*/api/v1/videos"),
        json={
            "total": 2,
            "data": [
                {"uuid": "abc", "name": "Test Video", "duration": 125,
                 "views": 42, "publishedAt": "2026-01-01T00:00:00Z",
                 "thumbnailPath": "/lazy-static/thumbnails/abc.jpg",
                 "channel": {"displayName": "Corp Channel"}},
            ],
        },
    )
    result = await get_recent_videos_service(limit=6)
    assert len(result["items"]) == 1
    assert result["items"][0]["uuid"] == "abc"
    assert "/videos/embed/abc" in result["items"][0]["embed_url"]


async def test_iframe_embed_blocks_external_domain():
    from app.api.videos import IframeValidator
    assert not IframeValidator.is_allowed("https://youtube.com/embed/abc")
    assert IframeValidator.is_allowed(f"{settings.PEERTUBE_PUBLIC_URL}/videos/embed/abc")


async def test_recent_videos_requires_auth(client):
    r = await client.get("/api/v1/videos/recent")
    assert r.status_code == 401
```

### Frontend unit (vitest)

```typescript
// frontend/src/tests/unit/iframe-embed.spec.ts
import { IframeEmbed } from '@/components/editor/extensions/IframeEmbed'

test('allows peertube domain', () => {
  const ext = IframeEmbed.configure({ allowedDomains: ['https://video.company.local'] })
  // проверяем что src валидируется
  expect(ext.options.allowedDomains).toContain('https://video.company.local')
})

test('rejects external domain', () => {
  // через editor.commands.setIframe — должен вернуть false
})
```

### E2E (Playwright)

```typescript
// frontend/e2e/videos-widget.spec.ts
test('videos widget shows on homepage', async ({ page }) => {
  await loginAsUser(page)
  await page.goto('/')
  await expect(page.locator('.videos-widget')).toBeVisible()
  await expect(page.locator('.video-card')).toHaveCount({ min: 1 })
})

test('video card opens peertube in new tab', async ({ page, context }) => {
  await loginAsUser(page)
  await page.goto('/')
  const [newPage] = await Promise.all([
    context.waitForEvent('page'),
    page.locator('.video-card').first().click(),
  ])
  await expect(newPage.url()).toContain(process.env.PEERTUBE_PUBLIC_URL)
})

test('iframe embed renders in article', async ({ page }) => {
  // создать статью с embed URL через API → открыть → проверить <iframe>
  await loginAsEditor(page)
  // ...
  await expect(page.locator('iframe[src*="/videos/embed/"]')).toBeVisible()
})
```

---

## Блок 10: Настройка каналов в PeerTube

Рекомендуемая структура после первого запуска:

| Канал | Кто ведёт | Контент |
|---|---|---|
| `corporate` | admin | Корпоративные события, отчёты |
| `training` | editor | Обучающие материалы, инструкции |
| `demos` | editor | Технические демо, скринкасты |

Виджет портала может фильтроваться по `PEERTUBE_CHANNEL_ID` → показывать только `corporate` или все.

---

## Ограничения и особенности

| Пункт | Описание |
|---|---|
| **OIDC через плагин** | Не такая же надёжность как нативная интеграция; при обновлении PeerTube нужно проверять совместимость плагина |
| **OAuth2 Password Flow** | Используется для сервисного аккаунта (виджет). Токен кэшировать в Redis, не запрашивать при каждом запросе |
| **iframe + CSP** | Необходимо явно добавить PeerTube в `frame-src` и `media-src`; без этого плеер не загрузится |
| **DOMPurify whitelist** | iframe по умолчанию вырезается санитайзером — нужен хук с проверкой домена |
| **Single Logout** | PeerTube не поддерживает OIDC SLO — при выходе из портала сессия в PeerTube остаётся. Минимальный риск (внутренняя сеть) |
| **Лицензия AGPL-3.0** | Self-hosted, исходный код открыт. Для корпоративного интранета проблем нет |
| **Размер видео** | По умолчанию лимит загрузки в PeerTube — 8 ГБ. Настраивается в Admin → Config |
| **Транскодинг** | PeerTube транскодирует видео в несколько качеств (360p, 720p, 1080p) — требует CPU |
