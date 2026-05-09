# ТЗ 2.8 — Унификация подходов к загрузке данных на vue-query

> **Источник:** `ref.md`, пункт 2.8 (раздел 2 «Frontend»).
> **Цель:** убрать гибрид из двух подходов к data-fetching и привести весь клиент к единой модели на `@tanstack/vue-query`.
> **Сложность:** ●●● • **Приоритет:** 🟡 • **Оценка:** 16–24 ч.

---

## 1. Контекст и проблема

### 1.1 Текущее состояние

В проекте сосуществуют **два подхода** к загрузке серверных данных:

**A. `@tanstack/vue-query`** — установлен, зарегистрирован в `.\frontend\src\main.ts` (`VueQueryPlugin`, `staleTime: 30s`, `retry: 1`). Используется в:

- `.\frontend\src\pages\KbListPage.vue` — `useQuery(['kb-articles', ...])`, `useQuery(['kb-tags'])`, инвалидация через `queryClient.invalidateQueries`.
- `.\frontend\src\pages\KbArticlePage.vue` — fetch статьи + связанных данных.
- `.\frontend\src\pages\NewsDetailPage.vue` — fetch новости.
- `.\frontend\src\pages\NewsListPage.vue` — fetch списка.
- `.\frontend\src\pages\NewsFormPage.vue` — частично (есть `useQueryClient` для инвалидации, но сама загрузка через `ref`).

**B. Ручные `ref`-флаги** (`loading: ref(false)`, `error: ref(null)`, `try/finally`):

- `.\frontend\src\pages\FilesPage.vue` — после 2.1.a загрузка инкапсулирована в `useFilesStore` (state `loadingTree`, `loadingDetail`, `syncing`).
- `.\frontend\src\pages\NewsFormPage.vue` — загрузка категорий/тегов/существующей новости через ручные ref.
- `.\frontend\src\pages\UserProfileView.vue` — загрузка профиля и связанных данных.
- `.\frontend\src\stores/*.ts` (auth, branding, links, modules, notifications, photos) — pinia-actions с ручным `loading`/`error`.

### 1.2 Что не так

| Проблема | Цена |
|---|---|
| **Двойная ментальная модель** | разработчик при правке должен помнить, как именно загружается этот экран, чтобы корректно инвалидировать данные. |
| **Дублирование boilerplate** | в каждом «ручном» месте — `loading`/`error`/`try/finally`/`onMounted`/refetch-on-action. В сумме сотни строк, которые vue-query даёт «бесплатно». |
| **Отсутствие dedup-кэша** | при возврате на ту же страницу выполняется новый сетевой запрос даже если данные актуальны (`staleTime` не работает там, где нет `useQuery`). |
| **Неконсистентные ошибки** | в одних местах `try/catch` с `message.error`, в других — `error.value`, в третьих — `result.failed`. UX неровный. |
| **Stale-данные после мутаций** | в ручных store-actions требуется явный refetch (легко забыть); vue-query инвалидирует по `queryKey` декларативно. |
| **SSR/prefetch/persist в будущем** | при текущем гибриде любые улучшения (persistedClient, prefetch на роутере, devtools) применяются только к части приложения. |

### 1.3 Что даст унификация

1. **Меньше кода в компонентах.** Каждое место «ручной загрузки» в среднем теряет 10–20 строк boilerplate.
2. **Согласованный кэш.** Возвраты по навигации (например, `/news → /news/:id → back`) не дёргают сеть лишний раз; `staleTime` уже сконфигурирован глобально.
3. **Декларативная инвалидация.** Мутации (создание/правка/удаление) приводят к `invalidateQueries({ queryKey: [...] })` — без ручного дёрганья методов в разных местах.
4. **Единая обработка ошибок.** Через глобальный `QueryCache.onError` или `MutationCache.onError` можно централизованно ловить 401/403/500 (UX и логи).
5. **Готовность к Devtools.** `@tanstack/vue-query-devtools` подключаются разово и покрывают всё приложение.
6. **Снижение энтропии** при будущих рефакторингах (2.1.* стиля): новые компоненты пишутся по одному паттерну.

---

## 2. Объём работ

### 2.1 Что мигрируем (страницы / компоненты)

| Файл | Что внутри | Приоритет миграции |
|---|---|---|
| `.\frontend\src\pages\NewsFormPage.vue` | Загрузка категорий, тегов, авторов, существующей новости (для edit). Уже есть `useQueryClient`. | A (легко, частично сделано) |
| `.\frontend\src\pages\UserProfileView.vue` | Загрузка профиля, отделов, коллег. | A |
| `.\frontend\src\pages\AdminPage.vue` + `pages/admin/tabs/*.vue` | Каждый таб делает свой fetch (Users, Email, Branding, KB, Audit, Analytics, NewsCategories, Monitoring, Modules, Links, UserAttributes, Photos, System, Keycloak). | B (много мест, но независимы) |
| `.\frontend\src\pages\photos/*.vue` | `PublicPhotoPage`, `PublicFolderPage`, `PhotosIndexPage`, `MySharesPage`. | B |
| `.\frontend\src\pages\HomePage.vue` | Дайджест/виджеты. | C (если есть fetch) |
| `.\frontend\src\pages\BookmarksPage.vue`, `LinksPage.vue` | Уже через store (`links`); либо мигрируем store, либо оборачиваем. | C |

### 2.2 Что мигрируем (Pinia-stores)

**Принцип:** разделить ответственность.

- **Серверное состояние** (то, что приходит из API: списки, детали, деревья) → **vue-query** (`queryKey` + queryFn).
- **Локальное / клиентское состояние** (UI-флаги, выборки, текущий пользователь, тема, locale) → остаётся в Pinia.

| Store | Текущее содержимое | Что делать |
|---|---|---|
| `.\frontend\src\stores\auth.ts` | currentUser, isAdmin, isEditor, токены, SSO. | **Оставить в Pinia** — это session-state, не серверный список. fetch профиля можно завернуть в `useQuery(['me'])` внутрь composable `useCurrentUser`, но Pinia остаётся фасадом. |
| `.\frontend\src\stores\branding.ts` | assets, settings + actions upload/reset. | **Гибрид:** queries для GET (`['branding']`), `useMutation` для upload/reset с инвалидацией. Pinia → тонкий фасад или полностью заменить composable `useBranding()`. |
| `.\frontend\src\stores\links.ts` | links + bookmarks + ordering. | **Полностью на vue-query** через composable `useLinks()`/`useBookmarks()`; store удалить **или** превратить в reactive wrapper над query-данными. |
| `.\frontend\src\stores\modules.ts` | список включённых модулей. | `useQuery(['modules'])`. |
| `.\frontend\src\stores\notifications.ts` | список уведомлений + счётчик. | `useQuery(['notifications'])` + polling/refetchInterval; mutations для read/delete. |
| `.\frontend\src\stores\photos.ts` | альбомы, фото, шары. | `useQuery(['photos', ...])`. |
| `.\frontend\src\stores\layout.ts` | UI-state. | **Оставить.** |
| `.\frontend\src\stores\theme.ts` | UI-state. | **Оставить.** |
| `.\frontend\src\stores\files.ts` (новый из 2.1.a) | tree, currentFolder, ncItems, breadcrumbs + actions. | **Гибрид:** перенести `loadTree`/`loadDetail` в `useQuery`, оставить в store только `selectedFolderId` (UI-state). Подробности — раздел 4.6. |

> Решение по каждому store принимать прагматично: если store используется как «глобальная шина» и вне него много кода — оставлять как фасад, внутри него вызывать `useQueryClient().fetchQuery` (но это анти-паттерн вне `setup`); чище — заменить на composable.

### 2.3 Что НЕ мигрируем

- Tokens / SSO redirect — `auth.ts`.
- UI-only state (`layout`, `theme`).
- Realtime через WebSocket / SSE (если есть). Подписка остаётся отдельно, но обновляет данные через `queryClient.setQueryData` или `invalidateQueries`.
- Команды без обращения в API (например, `useConfirmDialog`).

---

## 3. Целевые соглашения (style guide)

### 3.1 Расположение query-функций

Создаём `.\frontend\src\queries/` — по одному файлу на доменный модуль:

```
frontend/src/queries/
├── keys.ts                 # фабрики queryKey (типизированные)
├── kb.ts                   # useKbArticlesQuery, useKbArticleQuery, useKbTagsQuery, useCreateArticleMutation, ...
├── news.ts                 # useNewsListQuery, useNewsDetailQuery, useNewsCategoriesQuery, useUpdateNewsMutation, ...
├── files.ts                # useFolderTreeQuery, useFolderDetailQuery, useUploadFilesMutation, ...
├── links.ts                # useLinksQuery, useBookmarksQuery, useReorderMutation, ...
├── notifications.ts
├── photos.ts
├── branding.ts
├── modules.ts
├── users.ts                # useCurrentUserQuery, useUserProfileQuery, useColleaguesQuery
└── system.ts               # useSystemSettingsQuery, useEmailSettingsQuery, ...
```

### 3.2 Фабрики ключей (`queries/keys.ts`)

```ts
export const queryKeys = {
  news: {
    all: ['news'] as const,
    list: (params: NewsListParams) => ['news', 'list', params] as const,
    detail: (id: string) => ['news', 'detail', id] as const,
    categories: () => ['news', 'categories'] as const,
  },
  kb: {
    articles: (params: KbListParams) => ['kb', 'articles', params] as const,
    article: (slug: string) => ['kb', 'article', slug] as const,
    tags: () => ['kb', 'tags'] as const,
    sections: () => ['kb', 'sections'] as const,
  },
  files: {
    tree: () => ['files', 'tree'] as const,
    folder: (id: string) => ['files', 'folder', id] as const,
  },
  // ...
} as const
```

**Правила:**
- `queryKey` — массив, первый элемент — домен (`'news'`/`'kb'`/...), второй — подресурс.
- Для инвалидации каскадом — `invalidateQueries({ queryKey: queryKeys.news.all })`.
- Все ключи проходят через фабрики. **Прямые литералы запрещены** (lint-правило при возможности).

### 3.3 Сигнатура composable

```ts
// queries/news.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { fetchNewsList, type NewsListParams } from '../api/news'
import { queryKeys } from './keys'

export function useNewsListQuery(params: MaybeRefOrGetter<NewsListParams>) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.list(toValue(params))),
    queryFn: () => fetchNewsList(toValue(params)),
  })
}

export function useUpdateNewsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateNews,
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.all })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(vars.id) })
    },
  })
}
```

**Правила:**
- Composables возвращают **результат vue-query как есть** (`{ data, isLoading, isError, error, refetch }`). Не оборачивать в свои объекты — сломаем reactivity.
- `queryFn` дергает только функции из `api/*.ts` (никаких axios прямо здесь).
- Реактивные параметры — через `MaybeRefOrGetter` + `toValue`.
- Для условного запуска — `enabled: computed(() => !!id.value)`.

### 3.4 Глобальная конфигурация (`main.ts`)

Расширить:

```ts
.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,    // решение по проекту
      },
      mutations: {
        // глобальный onError → message.error через i18n
      },
    },
    queryCache: new QueryCache({
      onError: (err) => { /* лог + toast при 500 */ },
    }),
    mutationCache: new MutationCache({
      onError: (err) => { /* лог + toast */ },
    }),
  },
})
```

### 3.5 Обработка ошибок в компоненте

Минимально:

```vue
<script setup>
const { data, isLoading, isError, error } = useNewsListQuery(params)
</script>

<template>
  <SkeletonCard v-if="isLoading" ... />
  <ErrorState v-else-if="isError" :message="parseApiError(error)" @retry="refetch" />
  <NewsList v-else :items="data.items" />
</template>
```

Глобально 401 — обрабатывает auth-interceptor (`.\frontend\src\api\http.ts`), не vue-query.

### 3.6 Devtools (опционально, dev-only)

```ts
if (import.meta.env.DEV) {
  const { VueQueryDevtools } = await import('@tanstack/vue-query-devtools')
  app.component('VueQueryDevtools', VueQueryDevtools)
}
```

И `<VueQueryDevtools v-if="dev" />` в `App.vue`.

---

## 4. План работ (этапы)

### Этап 0 — подготовка (1–2 ч)

1. Baseline: `npm --prefix frontend run typecheck && npm --prefix frontend run lint && npm --prefix frontend test` — должно быть зелено (211/211).
2. Завести ветку `refactor/2.8-vue-query`.
3. Создать `.\frontend\src\queries\keys.ts` (только фабрики ключей под существующие vue-query вызовы).
4. Создать `.\frontend\src\queries\index.ts` (re-export).
5. Расширить глобальную конфигурацию (см. 3.4) — `MutationCache`/`QueryCache` с централизованным toast.

### Этап 1 — миграция уже частично-vue-query страниц (2–3 ч)

Цель — закрепить шаблон до раскатки.

1. **`KbListPage.vue`** — вынести inline `useQuery({queryKey:['kb-articles',...]})` в composable `useKbArticlesQuery` в `queries/kb.ts`, ключи через фабрику. То же для `kb-tags`. Все `invalidateQueries` — через `queryKeys.kb.*`.
2. **`KbArticlePage.vue`** — аналогично.
3. **`NewsListPage.vue`**, **`NewsDetailPage.vue`** — то же.

После этапа: ни одного `queryKey: ['...']` строкового литерала вне `queries/keys.ts`. `npm test` — зелено.

### Этап 2 — миграция «ручных» страниц (4–6 ч)

Порядок (от простого к сложному):

1. **`UserProfileView.vue`** → `useUserProfileQuery`, `useColleaguesQuery`.
2. **`NewsFormPage.vue`** — fetch категорий/тегов/новости-для-edit на queries; `saveAsDraft`/`publish` → `useMutation`s с `onSuccess`-инвалидацией.
3. **Admin tabs** (по одному PR/коммиту на таб):
   - `UsersTab` → `useUsersQuery` + mutations (create/update/delete).
   - `EmailTab`, `BrandingTab` (после 2.3 уже частично через store — заменить store на composable либо оставить store как фасад).
   - `AuditTab`, `AnalyticsTab`, `MonitoringTab` — read-only queries с `staleTime` под характер данных (audit — 0, analytics — 60s).
   - `NewsCategoriesTab`, `LinksTab`, `KeycloakTab`, `KbTab`, `ModulesTab`, `UserAttributesTab`, `PhotosTab`, `SystemTab` — аналогично.
4. **Photos pages** (`PublicPhotoPage`, `PublicFolderPage`, `PhotosIndexPage`, `MySharesPage`).

После каждой страницы:
- typecheck + lint зелёно;
- ручная smoke-проверка (loading state, навигация туда-обратно, мутации).

### Этап 3 — миграция Pinia-stores (3–5 ч)

Подход: **incremental, без one-shot переписывания**. Для каждого store, который содержит серверные данные:

1. Создать `queries/<domain>.ts` с queries/mutations.
2. В компонентах постепенно заменять `useXxxStore()` на queries/mutations.
3. Когда последний потребитель ушёл — удалить серверные части store. Локальное UI-состояние оставить.

Порядок:

1. **`modules.ts`** (легкий) → `useModulesQuery`. Удалить store или оставить selectors.
2. **`notifications.ts`** → `useNotificationsQuery({ refetchInterval: 30_000 })` + mutations `markRead`/`markAllRead`/`delete`.
3. **`links.ts`** → `useLinksQuery`/`useBookmarksQuery` + mutations. Учесть, что `LinksAndBookmarksPage` (после 2.1.b) уже использует store — обновить компоненты `links/*`.
4. **`branding.ts`** → queries/mutations. Перепроверить, что `BrandingTab` (после 2.3) работает.
5. **`photos.ts`** → queries (с учётом параметризации по альбому).
6. **`auth.ts`** → `useCurrentUserQuery` (только для профиля); токены и `isAdmin`/`isEditor` остаются в Pinia.

### Этап 4 — `useFilesStore` (2–3 ч)

После 2.1.a `useFilesStore` инкапсулирует tree/detail/syncing.

1. Заменить state `tree`, `loadingTree`, `currentFolder`, `ncItems`, `breadcrumbs`, `loadingDetail` на queries:
   - `useFolderTreeQuery()` → `tree`, `isLoading`.
   - `useFolderDetailQuery(folderId)` → `currentFolder`, `ncItems`, `breadcrumbs`. `enabled: !!folderId`.
   - `useSyncFromNcMutation()` → `syncing` через `isPending`, `onSuccess` инвалидирует `files.tree`.
   - `useCreateFolderMutation`, `useDeleteFolderMutation` — инвалидируют `files.tree` + при удалении сбрасывают `selectedFolderId`.
2. В store оставить только UI-state: `selectedFolderId`. Computed `canUpload`/`canManage` — переехать в composable `useFilesPermissions(currentFolder, auth)`.
3. Обновить `useFilesTree`/`useFilesUpload`/`useFilesBulkOps`/`useFilesSelection` — там, где они дёргали store-actions, заменить на mutations.
4. Прогнать тесты (`files-store.spec.ts` придётся переписать → `files-queries.spec.ts` + msw).

### Этап 5 — обработка ошибок и UX (1–2 ч)

1. Глобальный `MutationCache.onError` → `useMessage`/`window`-event для toast.
2. `QueryCache.onError` — только для логов, без toast (queries часто фоновые refetch).
3. Стандартный компонент `ErrorState` (если ещё нет) для inline-ошибок страниц.
4. Перепроверить все retry — текущий `retry: 1` ОК для GET, для mutations — 0.

### Этап 6 — тесты и документация (2–3 ч)

1. Добавить `msw` (если ещё нет) для unit-тестов queries; либо использовать уже существующий стиль `vi.mock('../../api/...')` (быстрее, без msw).
2. Покрыть hot paths: `useKbArticlesQuery` (success/error), `useUpdateNewsMutation` (инвалидирует ключи), глобальный onError.
3. Обновить ADR / `docs/` (если ведётся): «vue-query — единственный способ работы с серверным state; queryKey — через фабрики».
4. Обновить `ref.md`: пункт 2.8 → «Закрытые ранее».

---

## 5. Технические детали и риски

### 5.1 Reactive parameters

`vue-query` принимает `Ref`/`computed`/`MaybeRefOrGetter` в `queryKey`. При смене значения — автоматический refetch. Не передавать «развёрнутые» значения (`.value`) — потеряем реактивность.

### 5.2 `enabled`

Для зависимых запросов:

```ts
useFolderDetailQuery(folderId, { enabled: computed(() => !!folderId.value) })
```

Это заменяет `watch + if (id) loadDetail(id)`.

### 5.3 Optimistic updates

Для тяжёлых сценариев (drag-and-drop порядка ссылок, bulk операции) использовать `onMutate` + `setQueryData` + rollback в `onError`. Внедрять **только** там, где сейчас уже есть оптимистичное поведение, чтобы не менять UX.

### 5.4 Параллельные/зависимые queries

- Параллельные — просто несколько `useQuery` в setup.
- Зависимые — `enabled` по флагу из первого.
- Множественные с одинаковой структурой — `useQueries({ queries: [...] })`.

### 5.5 SSR / persistence

В рамках 2.8 **не вводим**. Просто оставляем дверь открытой.

### 5.6 Файл `auth.ts`

Особый случай: `currentUser` нужен синхронно во многих местах (роут-гарды, AppLayout). Решение: `useCurrentUserQuery` для refetch, а Pinia-store auth.ts становится тонкой обёрткой, которая хранит `currentUser` и обновляется из query. Альтернатива — не трогать auth и оставить вне vue-query.

### 5.7 Регрессии

Типовые:
- **Race conditions:** ручные ref-флаги часто маскируют lateset-wins. vue-query решает это сам.
- **Двойные запросы:** при включённом `refetchOnMount` + локальный `loadX` в `onMounted` остаётся старая логика → удалять обе ветки одновременно.
- **Утечка `isLoading` смысла:** в vue-query `isLoading` = первый запрос; повторный refetch = `isFetching`. В UI часто нужен именно `isFetching` (showed-once skeleton ≠ background spinner).

### 5.8 Совместимость с тестами

Для unit-тестов компонентов придётся:
- Создавать `QueryClient` per-test (`new QueryClient({ defaultOptions: { queries: { retry: false }}})`).
- Оборачивать mount в `VueQueryPlugin` или `provide(QueryClientKey, client)`.
- Хелпер `tests/helpers/withQueryClient.ts` (создать единожды).

---

## 6. Definition of Done

- [ ] Создан каталог `.\frontend\src\queries\` с `keys.ts` + по файлу на домен.
- [ ] Все `useQuery({ queryKey: [...] })` в коде используют фабрики из `queryKeys`.
- [ ] Ни в одной странице/компоненте/store не осталось пары «`loading: ref(false)` + `try/finally` + `loadXxx()` для серверного GET».
- [ ] Серверный state в Pinia ограничен: `auth.ts` (currentUser/токены), `layout.ts`, `theme.ts`. Все остальные stores либо удалены, либо оставлены тонкими фасадами без `loading`/`fetch`.
- [ ] `useFilesStore` после миграции содержит только `selectedFolderId` (+ при необходимости небольшие helpers).
- [ ] Глобальные `QueryCache.onError`/`MutationCache.onError` подключены, ошибки логируются единообразно.
- [ ] Devtools подключены (dev-only) — опционально, но желательно.
- [ ] `npm --prefix frontend run typecheck` — 0 ошибок.
- [ ] `npm --prefix frontend run lint` — 0 ошибок.
- [ ] `npm --prefix frontend test` — все существующие тесты + новые зелёные.
- [ ] Ручная регрессия (см. 6.1) пройдена.
- [ ] `ref.md`: пункт 2.8 удалён из активных, перенесён в «Закрытые ранее».

### 6.1 Чек-лист ручной регрессии

1. **News:** список → детали → назад. Повторный заход не дёргает сеть (staleTime). Создание/правка инвалидирует список.
2. **KB:** список с фильтрами/поиском, статья, теги. После создания — список обновлён.
3. **Files:** дерево, выбор папки, аплоад → список обновлён, sync from NC → дерево обновлено.
4. **Profile (UserProfileView):** загрузка профиля, отделы, коллеги.
5. **Admin tabs:** каждый таб — корректный loading-state, корректное обновление после мутаций.
6. **Photos:** альбомы, фото, шары.
7. **Notifications:** счётчик обновляется (refetchInterval), markRead/markAll работают.
8. **Links/Bookmarks:** drag-and-drop сохраняет порядок (если был optimistic — поведение сохранилось).
9. **Branding:** загрузка/сброс ассетов отражается мгновенно.
10. **Offline / 401 / 500:** глобальный обработчик показывает toast, не дублируется по 5 раз.

---

## 7. Оценка по этапам

| Этап | Часы |
|------|------|
| 0. Подготовка (keys.ts, глобальная конфигурация) | 1–2 |
| 1. Миграция KB/News (уже на vue-query) → composables | 2–3 |
| 2. Ручные страницы (Profile, NewsForm, Admin tabs, Photos) | 4–6 |
| 3. Pinia stores (modules, notifications, links, branding, photos, auth) | 3–5 |
| 4. `useFilesStore` → vue-query | 2–3 |
| 5. Глобальные ошибки + Devtools | 1–2 |
| 6. Тесты + документация + `ref.md` | 2–3 |
| **Итого** | **15–24 ч** |

Соответствует плановой оценке **●●●** из `ref.md`.

---

## 8. Возможные подводные камни (краткая шпаргалка)

| Симптом | Причина | Решение |
|---|---|---|
| После мутации UI не обновился | забыли `invalidateQueries` | `onSuccess: () => qc.invalidateQueries(...)` |
| Двойной refetch на mount | оставили старый `onMounted(() => loadX())` рядом с `useQuery` | удалить старый код полностью |
| `data.value` undefined в первом render | нет `placeholderData`/`initialData` или забыли `v-if="!isLoading"` | `<template v-if="data">` или `placeholderData: keepPreviousData` |
| Лишние сетевые запросы при тайпинге | реактивный `queryKey` без debounce | оборачивать input в `useDebounce` (как сейчас в `KbListPage`) |
| `enabled` не работает | передан `boolean` вместо `computed` | `enabled: computed(() => !!id.value)` |
| Тест mount падает на отсутствии QueryClient | не подключили плагин | хелпер `withQueryClient(component)` |
