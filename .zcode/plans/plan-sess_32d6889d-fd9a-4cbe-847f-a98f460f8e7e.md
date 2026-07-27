# [H1] SSRF через `/bookmarks/favicon` — план реализации

## Контекст (из разведки)

**Текущий баг** (`backend/app/api/bookmarks.py:58-72, 86-95`): favicon-прокси валидирует только scheme/netloc, затем `httpx.AsyncClient(follow_redirects=True, max_redirects=3)` идёт на `{scheme}://{netloc}/favicon.ico` **без проверки IP / DNS-резолва / приватных диапазонов**. Редиректы не ре-валидируются. Это последний внешний SSRF-surface портала (audit [H1], DoD: `GET /bookmarks/favicon?url=http://10.0.0.1/` → 404).

**Production-референс уже есть** — `backend/app/services/helpdesk/email_images.py:132-698` реализует полный safe-fetcher (блок private+loopback+link-local+cloud-metadata, async-DNS `_resolve_is_safe`, double-resolve `_resolve_stable_public_ip` против DNS-rebinding, `follow_redirects=False` + ручной обход с re-валидацией каждого hop). Но он захардкожен в helpdesk-сервисе и не переиспользуется.

**Frontend fallback уже работает**: `LinkCard.vue:36-41` рендерит `<n-icon v-else><LinkOutline/></n-icon>` при ошибке/404 favicon. Менять API-контракт (200+SVG) не нужно — UX-default уже есть.

## Дефолты (UI не ответил — зафиксированы здесь как часть плана)

1. **Политика private-IP**: блокировать **все** private/loopback/link-local/multicast/unspecified/cloud-metadata (как `email_images._is_public_ip`, по audit DoD). Приватные интранет-домены (Nextcloud/Keycloak внутри VPN) перестанут получать favicon → покажется `<n-icon>LinkOutline</n-icon>` (приемлемо для интранет-портала; consistency с email_images; allowlist — отдельная правка если UX пострадает).
2. **API-контракт**: оставить `404 + UI-LinkOutline`. Контракт кэша (`{ok:false}` negative-cache TTL 1d) не трогаем.

---

## Этап 1 — `backend/app/core/net_guard.py` (новый модуль, чистые функции)

Обобщённый SSRF-guard, готовый к переиспользованию в bookmarks (этап 2), и позже — в keycloak_admin (M9) и консолидации email_images. Дизайн скопирован с email_images (лучшая реализация), но параметризован политикой.

**Публичный API:**
```python
# Чистые функции (unit-тестируемые без сети):
def is_public_ip(ip) -> bool          # из email_images._is_public_ip
def is_safe_remote_url(url) -> bool    # scheme + host-как-IP + localhost
                                        # (allow_private=False по умолчанию)

# Async-функции (через asyncio.get_running_loop().getaddrinfo):
async def resolve_all_ips(host) -> list[IPv4Address|IPv6Address]
async def assert_url_safe(url) -> bool  # is_safe_remote_url + resolve_all_ips (все public)
async def resolve_stable_ip(host) -> IPv4Address|IPv6Address|None  # double-resolve против rebinding
```

**Перенос из email_images:** `is_public_ip`, `is_safe_remote_url` (реэкспорт thin-shim для backward-compat → старый `email_images.is_safe_remote_url` остаётся как `from app.core.net_guard import is_safe_remote_url`, пока не консолидируем в M-задаче). **Переноса `_resolve_*`/`_assert_safe_to_fetch`/`_fetch_remote` из email_images НЕ делаем** — вне scope H1, risk.

**Файлы:**
- `backend/app/core/net_guard.py` — новый (~120 LOC, docstring + 5 функций)
- `backend/tests/unit/test_net_guard.py` — новый (parametrize: private/loopback/link-local/cloud-metadata/public/IPv6/localhost/DNS-rebinding mock)

---

## Этап 2 — переписать `bookmarks.py` favicon-fetcher

**`_do_favicon_fetch` (bookmarks.py:58-72)** → safe-fetcher по образцу `email_images._fetch_remote`:
- `follow_redirects=False` + ручной обход редиректов (`_MAX_REDIRECTS=3`, как сейчас)
- на каждом hop: `await assert_url_safe(current)` + `await resolve_stable_ip(host) is not None` (DNS-rebinding guard)
- если unsafe → вернуть специальный маркер (`raise _FaviconBlocked` или `return None`), отличимый от network-error, чтобы negative-cache TTL остался 1d

**`get_bookmark_favicon` (bookmarks.py:75-135):**
- добавить early-валидацию origin через `is_safe_remote_url(origin) + assert_url_safe(origin)` **до** кэш-lookup (быстрый 404 для `http://10.0.0.1/` без fetch) — но кэшировать negative-result всё равно (DoD: «не идёт запрос в приватную сеть»)
- остальная логика (кэш, content-type, size-cap) без изменений

**Что НЕ меняем:** response-type (`Response`, не StreamingResponse — favicon ≤500KB, стриминг избыточен), кэш-формат, content-type allowlist, auth.

---

## Этап 3 — тесты `test_bookmarks_favicon.py` (расширить)

Добавить класс `TestFaviconSsrfGuard` (по образцу `test_helpdesk_email_images.py::TestSsrfGuard` + `TestFetchRemoteRedirects`):

**Unit (нет сети) — `is_safe_remote_url` через endpoint:**
- `GET ?url=http://127.0.0.1/` → 404, `_do_favicon_fetch` не вызывается
- `GET ?url=http://10.0.0.1/` → 404 (DoD из аудита)
- `GET ?url=http://192.168.1.1/` → 404
- `GET ?url=http://172.16.0.1/` → 404
- `GET ?url=http://169.254.169.254/latest/meta-data/` → 404 (cloud-metadata, DoD из аудита)
- `GET ?url=http://[::1]/` → 404 (IPv6 loopback)
- `GET ?url=http://localhost/` → 404
- `GET ?url=https://example.com` → 200 (легитимный public) — регресс

**DNS-rebinding (mock `getaddrinfo`):** через `_FakeAsyncClient`-шаблон из `test_helpdesk_email_images.py:451-486` — первый резолв public, второй private → блокируется (DoD из аудита)

**Redirect-to-private (mock httpx):** 302 → `http://127.0.0.1/admin` → блокируется, второй запрос не уходит (DoD из аудита)

**Negative-cache:** SSRF-blocked URL пишется в Redis как `{ok:false}` TTL 1d (повторный запрос не доходит до fetch)

**Что НЕ трогаем:** существующие 30+ тестов в `test_bookmarks_favicon.py` (контракт кэша/CT/URL) — они остаются зелёными (только `test_http_url_allowed` с `http://intranet.company.local` нужно проверить — если резолв мокается, должен остаться 200).

---

## Этап 4 — верификация + аудит

1. `./scripts/ci_lint.sh` (ruff + mypy, как CI)
2. `pytest tests/unit/test_net_guard.py tests/unit/test_bookmarks_favicon.py tests/unit/test_helpdesk_email_images.py tests/unit/test_keycloak_admin.py -v` — regression
3. `pytest tests/unit` — полный backend unit
4. Обновить `audit.md` карточку [H1] → `[x]`, таблицу, Roadmap, история изменений (как для M21)

## Не входит в scope (отдельные задачи)

- ❌ Консолидация `keycloak_admin._is_unsafe_ip` в `net_guard` → задача **M9** (God Module), требует characterization-тестов keycloak test-endpoints
- ❌ Перенос `_resolve_*`/`_fetch_remote` из `email_images` в `net_guard` → риск-зона, helpdesk-email critical-path; отдельная задача после H1
- ❌ Allowlist интранет-доменов → только если UX пострадает (отдельная правка)
- ❌ httpcore transport-level IP-pinning → сознательно отклонено в email_images (документировано как sufficient для интранет)

## Риск-стратегия

- **Characterization-тесты первыми:** существующие 30+ favicon-тестов — сетка безопасности; новый safe-fetcher должен их все пройти
- **Backward-compat shim:** `email_images.is_safe_remote_url` остаётся импортом из `net_guard` (пока), чтобы не ломать helpdesk
- **Маленькие коммиты:** net_guard (этап 1) → bookmarks fetcher (этап 2) → тесты (этап 3) — каждый независимо тестируемый
- **mypy/ruff** после каждого этапа

## Оценка

- net_guard + тесты: ~150 LOC кода + ~100 LOC тестов
- bookmarks rewrite: ~50 LOC изменений
- favicon SSRF-тесты: ~120 LOC
- Итого: ~2-3 часа работы, 1 сессия