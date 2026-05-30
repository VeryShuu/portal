# Отчёт по рефакторингу и проблемам кода (portal)

Документ — результат ревью репозитория: архитектурные проблемы, баги, недоделки,
костыли и неактуальная документация. Для каждого пункта указаны путь и строки.

**Легенда статуса:**
- ✅ *проверено* — лично подтверждено чтением кода в ходе ревью.
- ▫️ *из ревью* — найдено ревью-подагентом, цитата кода правдоподобна, но точные
  строки стоит перепроверить перед правкой.

**Шкала важности:** 🔴 высокая · 🟠 средняя · 🟡 низкая.

---

## 1. Безопасность / доступы

### 1.1 🔴 Обход ACL новостей в поиске для пользователей без департамента ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/api/search.py:120-131` (и аналогично `:317-323`).
- **Проблема:** при `user.department is None` условие таргетинга превращается в
  `News.target_departments @> ARRAY[]::varchar[]`. В PostgreSQL оператор `@>`
  (содержит) истинен для **любого** непустого массива → пользователь без
  департамента видит в поиске все новости, таргетированные на департаменты.
- **Фикс:** для пользователей без департамента отдавать только публичные новости
  (`News.target_departments IS NULL`), а не «пустой массив содержится везде».

### 1.2 🔴 `/search/suggest` раскрывает заголовки закрытых новостей ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/api/search.py:450-462`.
- **Проблема:** блок подсказок по новостям фильтрует только `deleted_at IS NULL`
  и `status == 'published'`, без таргетинга по департаменту/роли. Для статей KB
  рядом корректно применяется `filter_accessible_articles`, а для новостей — нет.
  Пользователь получает заголовки новостей, которые ему недоступны.
- **Фикс:** применить тот же ACL-фильтр таргетинга, что и в основном листинге/поиске новостей.

### 1.3 🟠 KB-вложения сохраняются при недопустимом MIME вместо отказа ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/api/kb/attachments.py:96-103`, `./backend/app/core/uploads.py:57-70`.
- **Проблема:** в `stream_upload_to_path` не передаётся `allowed_mimes`; файл с
  недопустимым типом сохраняется, а MIME просто понижается до
  `application/octet-stream` (вместо 422).
- **Фикс:** передавать `allowed_mimes=SAFE_MIME_TYPES` и отклонять неподдерживаемый MIME (422).

### 1.4 🟠 KB-импорт создаёт контент без проверки прав на секцию ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/api/kb/export_import.py:238-241`, `./backend/app/api/kb/_frontmatter.py:85-118`.
- **Проблема:** путь импорта находит/создаёт секцию по path и создаёт статью без
  вызова `require_section_permission` / `require_article_permission` — нарушение
  правила AGENTS «ВСЕ KB endpoints вызывают require_*_permission».
- **Фикс:** перед созданием/перезаписью резолвить целевую секцию и требовать `editor`.

### 1.5 🟡 Deprecated `/links/sso-url` возвращает `id_token_hint` в теле ответа ▫️
- **Где:** `./backend/app/api/links.py:181-199`.
- **Проблема:** endpoint помечен deprecated, но активен и отдаёт URL с токеном в
  JSON (риск утечки в логи/историю/JS). Рядом есть безопасный `/sso-redirect`.
- **Фикс:** удалить endpoint или вернуть 410 после миграции клиентов.

---

## 2. Баги / корректность

### 2.1 🟠 `links.list_links`: `total` не учитывает фильтр `category` ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/api/links.py:55-85`.
- **Проблема:** `category` применяется к выборке данных, но **не** к `count_stmt`,
  поэтому `total` неверен при заданном `category`. Дополнительно `total` не
  учитывает скрытые ссылки (`hidden_link_ids`), которые отфильтрованы в Python из
  `items`, — `items`/`total` расходятся.
- **Фикс:** применить тот же предикат `category` (и логику hidden) к `count_stmt`.

### 2.2 🟠 Небезопасное снятие startup-lock воркера ▫️ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/worker/main.py:106-109`.
- **Проблема:** на shutdown безусловно удаляется `_SYNC_LOCK_KEY` — можно стереть
  активный лок другого воркера. Правильный паттерн (token + compare-and-delete
  Lua) уже есть в `./backend/app/worker/tasks/files.py:22-26,138-141`.
- **Фикс:** хранить токен лока и снимать через compare-and-delete.

### 2.3 🟠 Снятие audit-flush lock без проверки владельца ▫️ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/worker/tasks/audit.py:39-43,92`.
- **Проблема:** значение лока фиксировано (`"1"`), снятие — безусловный delete.
  При истечении TTL и захвате лока другим воркером этот воркер удалит чужой лок.
- **Фикс:** случайный токен + compare-and-delete Lua (как в files.py).

### 2.4 🟠 Утечка таймера в `WorldClockWidget` при быстром размонтировании ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/components/widgets/WorldClockWidget.vue:108-119`.
- **Проблема:** `setInterval` создаётся внутри отложенного `setTimeout` (до 1000 мс).
  Если компонент размонтируется раньше, в `onBeforeUnmount` `timer` ещё `null`, и
  созданный позже интервал не очищается. Также дублирует готовый
  `./frontend/src/composables/useWorldClockClock.ts`.
- **Фикс:** хранить и отменять также handle от `setTimeout`; переиспользовать composable.

### 2.5 🟠 Слушатель `photos:processed` в Pinia-store не снимается ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/stores/photos.ts:35-45`.
- **Проблема:** `window.addEventListener('photos:processed', () => {...})` повешен
  на анонимную функцию → его нельзя снять. При повторной инициализации store
  (logout/login) слушатели накапливаются; нет `onScopeDispose`.
- **Фикс:** хранить ссылку на хендлер и снимать в `onScopeDispose`.

### 2.6 🟡 Слушатели вне `onMounted` (риск утечки) ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/composables/usePhotoUpload.ts:80-82`,
  `./frontend/src/components/OnboardingTour.vue:239-243`.
- **Проблема:** `addEventListener` вызывается синхронно на этапе setup, а не в
  `onMounted`. Вне жизненного цикла компонента cleanup не сработает.
- **Фикс:** перенести регистрацию в `onMounted`.

### 2.7 🟡 Module-level `watch` без эффект-скоупа (никогда не останавливается) ▫️
- **Где:** `./frontend/src/composables/useWorldClockWeather.ts:28-34` и `:14-15,81-103`
  (ручной `refCount` для module-scoped `setInterval`),
  `./frontend/src/composables/useWorldClockCities.ts:37-49`.
- **Проблема:** реактивное состояние и `watch` объявлены на уровне модуля
  (singleton), живут весь срок вкладки, мешают юнит-тестам, ручной refcount хрупок (HMR → отрицательный счётчик).
- **Фикс:** вынести в Pinia-store с `onScopeDispose`.

### 2.8 🟡 `NotificationsDropdown.openDrawer` не обрабатывает ошибку загрузки ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/components/NotificationsDropdown.vue:139`.
- **Проблема:** `store.loadNotifications()` (async) вызывается без `await`/`.catch()`
  — сетевая ошибка при открытии не показывается пользователю.
- **Фикс:** обработать промис и показать ошибку.

### 2.9 🟡 Жёстко зашитый `'ru-RU'` в форматтерах дат/времени ▫️
- **Где:** `./frontend/src/composables/useWorldClockClock.ts:17`,
  `./frontend/src/composables/useWorldClockForm.ts:61`,
  `./frontend/src/components/files/FilesTable.vue:73`.
- **Проблема:** локаль форматирования игнорирует текущий i18n-язык — англоязычные
  пользователи видят русское форматирование.
- **Фикс:** брать локаль из `useI18n()` или единый `./frontend/src/utils/formatDate.ts`.

---

## 3. Архитектура

### 3.1 🟠 Бизнес-логика в роутерах вместо services ▫️
- **Где:** `./backend/app/api/search.py:38-418` (построение запросов, ACL,
  пагинация, оркестрация сессий прямо в роуте);
  `./backend/app/api/links.py:304-349,396-422` (`upload_link_icon` + PIL-оптимизация
  иконок в HTTP-хендлере).
- **Проблема:** нарушение правила AGENTS «бизнес-логика в `services/`, не в роутах»;
  затрудняет тестирование и переиспользование.
- **Фикс:** вынести логику в `./backend/app/services/search.py` и `services/links_icons.py`.

### 3.2 🟡 Дублирование поиска subject'ов Keycloak ▫️
- **Где:** `./backend/app/api/kb/permissions.py:397-444`,
  `./backend/app/api/files/permissions.py:51-96`.
- **Проблема:** почти идентичный код поиска пользователей/групп и инъекции
  системных групп в двух модулях.
- **Фикс:** общий сервис, возвращающий нормализованный список subject'ов.

### 3.3 🟠 Дублирующийся composable `useArticleFormState` ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/composables/useArticleFormState.ts` и
  `./frontend/src/pages/composables/useArticleFormState.ts`.
- **Проблема:** файлы идентичны кроме пути импорта и одного метода
  (`initFromArticle`). Версия в `composables/` не имеет потребителей
  (`KbArticleFormPage.vue` импортирует из `pages/composables/`) — мёртвый дубль.
  Утилита `getErrorStatus` продублирована в трёх местах (оба файла + `KbArticleFormPage.vue:187`).
- **Фикс:** удалить мёртвый дубль, `getErrorStatus` вынести в `./frontend/src/utils/parseApiError.ts`.

### 3.4 🟠 `EmailOutboxTab` обходит TanStack Query ▫️
- **Где:** `./frontend/src/pages/admin/tabs/EmailOutboxTab.vue:238-414`.
- **Проблема:** единственная админ-вкладка, которая вручную управляет состоянием
  загрузки через прямые `async/await`, вместо `useQuery`/`useMutation`, как в
  остальном приложении.
- **Фикс:** перевести на TanStack Query, запрос вынести в `./frontend/src/queries/admin.ts`.

### 3.5 🟡 God-компоненты (>400 строк) ▫️
- **Где:** `./frontend/src/components/RichEditor.vue` (~830 строк; 4 диалога в одном
  шаблоне), `./frontend/src/pages/StaffDirectoryPage.vue` (~505),
  `./frontend/src/components/meetings/RoomGrid.vue` (~491),
  `./frontend/src/pages/admin/tabs/SystemTab.vue` (~474).
- **Фикс:** выделить диалоги/секции в подкомпоненты.

### 3.6 🟡 Локальный тип `SysSettingsOut` дублирует сгенерированный ▫️
- **Где:** `./frontend/src/pages/admin/tabs/SystemTab.vue:284-309`.
- **Проблема:** локальный интерфейс дублирует `SystemSettingsOut` из
  `./frontend/src/api/types.gen.d.ts` и уже расходится с ним (нет части полей).
- **Фикс:** использовать тип из `types.gen.d.ts`, локальный удалить.

### 3.7 🟡 Персистенс `lang` размазан по четырём файлам ▫️
- **Где:** `./frontend/src/composables/useLoginForm.ts:86`,
  `./frontend/src/components/layout/HeaderLangSwitcher.vue:48`,
  `./frontend/src/pages/AuthLocalPage.vue:331`,
  чтение — `./frontend/src/i18n/index.ts:9`.
- **Фикс:** централизовать через единый composable/стор (`setLocale()`).

---

## 4. Костыли / code smells

### 4.1 🟠 Детекция Mock/MagicMock в production-коде ACL ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/services/photos_acl.py:219-231`.
- **Проблема:** функция `resolve_folders_permissions_batch` проверяет
  `isinstance(resolve_folder_permission, (Mock, MagicMock))` и меняет поведение —
  тестовый костыль протёк в боевую логику прав доступа.
- **Фикс:** убрать детекцию моков из прод-кода; мокать на уровне фикстур/публичного API.

### 4.2 🟠 Кэш идемпотентности хранит полное тело ответа (нарушение правила) ✅
- **Где:** `./backend/app/middleware/idempotency.py:150-161` (`body_b64` в Redis).
- **Проблема:** AGENTS.md прямо запрещает (строки 214/334) хранить полный response
  body — только `{"id":"uuid"}`. Middleware кэширует весь base64-ответ в Redis.
  Реализация осознанная, но **противоречит зафиксированному правилу** → нужно либо
  поправить код, либо обновить ADR/AGENTS, синхронизировав решение.
- **Фикс:** привести к правилу (хранить только id) ИЛИ зафиксировать новое решение в ADR.

### 4.3 🟡 Глушение исключений `except Exception: pass` ▫️
- **Где (примеры):** `./backend/app/api/branding.py:103-108` (парс конфига молча
  откатывается к дефолтам), `./backend/app/api/kb/attachments.py:187-194`
  (ошибки Redis-дедупа аудита проглатываются). По репозиторию шаблон
  `except Exception` встречается широко (см. worker/tasks/photos/processing.py — ~10 раз).
- **Фикс:** как минимум логировать с контекстом, не «тихо» терять поведение.

### 4.4 🟡 Хардкод цветов/инлайн-стилей вместо токенов и scoped CSS ▫️
- **Где:** `./frontend/src/pages/admin/tabs/SystemTab.vue` (~18 инлайн-`style=`),
  `./frontend/src/components/RichEditor.vue:65,81,99,108,200,376` (`#ffe066` и пр.),
  `./frontend/src/pages/admin/tabs/EmailOutboxTab.vue:325` (style-строка в `h()`),
  `./frontend/src/components/staff/StaffTableView.vue:221` (`#f0f0f0 !important`).
- **Проблема:** нарушение конвенции «scoped CSS, без инлайн-стилей и хардкод-цветов».
- **Фикс:** перенести в классы/`admin-tabs.css`, использовать CSS-токены.

### 4.5 🟡 `Promise.all` с единственным промисом ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/pages/KbArticleFormPage.vue:258`
  (`const [secRes] = await Promise.all([fetchSections()])`).
- **Фикс:** `const secRes = await fetchSections()`.

### 4.6 🟡 `console.error` в прод-обработчиках ошибок ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/pages/admin/tabs/FileIconsTab.vue:244,257`.
- **Фикс:** убрать или заменить нормальным репортером ошибок.

### 4.7 🟡 Эмодзи как интерактивный UI-элемент ✅ — ⊘ ОТКЛОНЕНО (предпосылка неверна)
- **Где:** `./frontend/src/components/RichEditor.vue:73` (кнопка «🔗» в bubble-меню).
- **Факт:** весь редактор-тулбар использует текст/эмодзи-глифы, а не `@vicons/ionicons5`:
  bubble-menu — `B/I/U/S/<>/H`, основной тулбар
  `./frontend/src/components/editor/toolbar/groups/MediaGroup.vue:11,25,39` — `🔗/🖼/▶`.
  Замена одной кнопки на `<n-icon>` создала бы рассогласование, а не устранила его.

---

## 5. Недоделки / неактуальные/несогласованные данные

### 5.1 🟠 i18n: дефолтные строки захардкожены по-русски ▫️
- **Где:** `./frontend/src/composables/useWorldClockCities.ts:15-18` (названия
  городов «Москва»/«Владивосток» в localStorage минуя `t()`),
  `./frontend/src/stores/branding.ts:27` (`portal_name: 'Корпоративный портал'`),
  `./backend/app/worker/tasks/notifications.py` (`portal_name = "Корпоративный портал"` ✅).
- **Проблема:** англоязычные пользователи видят русские дефолты; бэкенд-воркер не
  берёт имя портала из branding-настроек.
- **Фикс:** ключи через `t()` (frontend) и из системных настроек (backend).

### 5.2 🟡 Неиспользуемое/мёртвое ▫️
- **Где:** `./frontend/src/pages/admin/tabs/SystemTab.vue:314,381` (`tlsLoadError`
  присваивается, но нигде не читается — ошибка загрузки TLS-статуса молча теряется);
  `kindOptions` в `EmailOutboxTab.vue:256-261` — не `computed`, метки не
  пересчитываются при смене локали.
- **Фикс:** показать ошибку TLS в UI; обернуть `kindOptions` в `computed`.

### 5.3 🟡 Баннер на главной не запоминает «закрыто» ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./frontend/src/pages/HomePage.vue:246` (`bannerDismissed = ref(false)`).
- **Проблема:** состояние локально к компоненту, сбрасывается при каждом переходе —
  баннер появляется снова.
- **Фикс:** хранить в `sessionStorage`.

---

## 6. Конвенции (расхождения с AGENTS.md)

### 6.1 🟡 List-endpoints без `{items,total,limit,offset}` ▫️
- **Где:** `./backend/app/api/meetings/bookings.py:71-114`,
  `./backend/app/api/kb/permissions.py:397-401`,
  `./backend/app/api/files/permissions.py:46-54`,
  `./backend/app/schemas/links.py:40-43` (`ServiceLinkList` без `limit/offset`).
- **Фикс:** привести list-ответы к единому конверту.

### 6.2 🟡 Дрейф модели и миграций по уникальности email ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/models/user.py:36` (`UniqueConstraint("email", name="uq_users_email")`)
  vs миграции `./backend/migrations/versions/030_email_unique_lower.py`,
  `037_users_email_partial_unique.py` (функциональный CI-индекс по `LOWER(email)`).
- **Проблема:** на уровне БД уникальность уже case-insensitive/partial, но модель
  всё ещё декларирует обычный case-sensitive `uq_users_email` — расхождение
  модель↔миграции (не security-дыра, т.к. в БД индекс есть).
- **Фикс:** синхронизировать декларацию в модели с фактическим состоянием БД.

### 6.3 🟡 Документированный список путей идемпотентности не совпадает с кодом ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./backend/app/middleware/idempotency.py:12-23` защищает
  `/api/v1/news`, `/api/v1/kb/articles`, `/api/v1/files/folders`,
  `/api/v1/notifications/send`; AGENTS.md:214 заявляет `POST /files/upload`
  (а не `/files/folders`).
- **Фикс:** привести в соответствие код и AGENTS.md.

---

## 7. Документация (неактуальность)

### 7.1 🔴 `CLOUD.md` — полный дубль `AGENTS.md` ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./CLOUD.md` (27.14 KB, побайтово идентичен `./AGENTS.md`).
- **Проблема:** два файла нужно синхронизировать вручную → неизбежный дрейф;
  cloud-специфики в файле нет.
- **Фикс:** удалить дубль или сделать редиректом на `./docs/deploy.md`.

### 7.2 🟠 Устаревший диапазон ADR ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./README.md:113`, `./AGENTS.md:113,138`.
- **Факт:** заявлен `ADR-001 – ADR-038`; в `./docs/adr.md` фактически до **ADR-041**.
- **Фикс:** обновить на `ADR-001 – ADR-041`.

### 7.3 🟠 Устаревший диапазон миграций ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./AGENTS.md:248` (`versions/ (001..060)`).
- **Факт:** в `./backend/migrations/versions/` — 62 файла, последний
  `062_backfill_users_directory_active_index.py`.
- **Фикс:** обновить на `001..062`.

### 7.4 🟠 `db-schema.generated.md` сильно устарел ▫️
- **Где:** `./docs/db-schema.generated.md` (последняя генерация ~2026-05-16).
- **Факт (отсутствует):** таблицы `email_outbox` (051), `meeting_rooms/bookings`
  (048), `news_polls*` (053/054); колонки `photos.blurhash` (060),
  `user_attribute_mappings.is_full_name_source` (047),
  `photo_folders.storage_kind/storage_root` (057); индексы `idx_users_active` (062),
  `idx_kb_comments_active` (061).
- **Фикс:** перегенерировать через `./backend/scripts/generate_db_schema_doc.py` и
  добавить в CI drift-check (по аналогии с `tests-generated-drift`).

### 7.5 🟠 `/trash` описан как soft-redirect, фактически — полноценная страница ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./AGENTS.md:198` vs `./frontend/src/router.ts:197-201` +
  `./frontend/src/pages/TrashPage.vue` (страница с вкладками news/photos).
- **Фикс:** исправить описание (роут промоутнут в полноценную admin-страницу).

### 7.6 🟠 `helpdesk.md` — ТЗ на нереализованный модуль ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./helpdesk.md` (~40 KB ТЗ helpdesk); в коде нет ни моделей, ни роутеров,
  ни страниц тикет-системы.
- **Фикс:** добавить в начало пометку «концептуальное ТЗ, не реализовано».

### 7.7 🟡 Неверные пути тест-скриптов в `testing.md` ✅ — ⊘ ОТКЛОНЕНО (не баг: строки внутри блока `cd backend`, путь уже корректен)
- **Где:** `./docs/testing.md:207-208` (`./scripts/run_pytest_unit.sh`,
  `./scripts/run_pytest_integration.sh`).
- **Факт:** скрипты лежат в `./backend/scripts/` (строка 229 того же файла уже
  ссылается корректно — внутренняя несогласованность).
- **Фикс:** добавить префикс `./backend/`.

### 7.8 🟡 Два lock-файла фронтенда (npm + pnpm) ✅
- **Где:** `./frontend/package-lock.json` и `./frontend/pnpm-lock.yaml` +
  `./frontend/pnpm-workspace.yaml`. README/AGENTS используют `npm`.
- **Проблема:** двойные lock-файлы → дрейф зависимостей и путаница.
- **Фикс:** оставить один пакет-менеджер, лишние lock-файлы удалить.

### 7.9 🟡 Неверный путь сгенерированных типов и стека в AGENTS ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./AGENTS.md:238` указывает `types/types.gen.d.ts`; фактически
  `./frontend/src/api/types.gen.d.ts`. `./AGENTS.md:106` относит `DOMPurify` к
  backend-стеку, тогда как это фронтенд-библиотека (`./frontend/package.json`).
- **Фикс:** поправить путь и переместить `DOMPurify` во frontend-список.

### 7.10 🟡 `api-contracts.md` не покрывает Meetings и Feedback ▫️
- **Где:** `./docs/api-contracts.md` (нет ссылок на `/api/v1/meetings/*` и
  `/api/v1/feedback/*`; они вынесены в `./docs/meetings.md`, `./docs/feedback.md`
  без перекрёстных ссылок).
- **Фикс:** добавить разделы/ссылки в основной индекс контрактов.

### 7.11 🟡 `SECURITY.md` — плейсхолдер вместо контакта ✅ — ✔ ИСПРАВЛЕНО
- **Где:** `./SECURITY.md:17` (`Email: укажите контакт владельца репозитория`).
- **Фикс:** указать реальный адрес для disclosure.

---

## Сводка по приоритету

| # | Пункт | Важность |
|---|-------|----------|
| 1.1 | Обход ACL новостей в поиске (нет департамента) | 🔴 |
| 1.2 | `/search/suggest` раскрывает закрытые заголовки | 🔴 |
| 7.1 | `CLOUD.md` = дубль `AGENTS.md` | 🔴 |
| 1.3–1.4 | KB: MIME-аплоад и импорт без проверки прав | 🟠 |
| 2.1–2.3 | `total` без фильтра, небезопасные локи воркеров | 🟠 |
| 2.4–2.5 | Утечки таймера/слушателя на фронте | 🟠 |
| 3.1,3.3,3.4 | Логика в роутерах, дубль composable, обход TanStack Query | 🟠 |
| 4.1–4.2 | Mock в прод-ACL, идемпотентность хранит тело | 🟠 |
| 7.2–7.6 | Устаревшие ADR/миграции/схема БД, /trash, helpdesk | 🟠 |
| остальные | code smells, мелкие конвенции, мелкая документация | 🟡 |

> Замечание по методологии: пункты со статусом ▫️ найдены ревью-агентами и
> правдоподобны, но перед правкой стоит перепроверить точные строки. Пункт
> «воркер рассылки не фильтрует `deleted_at`» был **отклонён** при проверке: таблица
> `users` использует hard-delete (колонки `deleted_at` нет, см. AGENTS.md:206).

---

## Журнал сессии (исправлено)

В этой сессии выполнены подтверждённые (✅) задачи безопасности, корректности и
документации. Бэкенд-правки проверены `ruff check` и полным юнит-прогоном
(**2253 passed**).

**Код:**
- **1.1 + 1.2** — устранён обход ACL новостей в поиске. В
  `./backend/app/services/news/_helpers.py` выделена публичная
  `news_targeting_conditions(user)`, экспортирована из
  `./backend/app/services/news/__init__.py`; в `./backend/app/api/search.py`
  заменён багованный `@> ARRAY[]` в `_news_multi`, в одиночном news-поиске и
  добавлен таргетинг в `/search/suggest` (под `role not in (editor, admin)`).
- **2.1** — `links.list_links`: общий список `conditions` для data-select и
  `count_stmt` (фикс `category`), исключение скрытых ссылок из `total`.
- **2.2** — `./backend/app/worker/main.py`: убрано безусловное снятие
  `_SYNC_LOCK_KEY` на shutdown, добавлена отмена фоновой sync-таски.
- **2.3** — `./backend/app/worker/tasks/audit.py`: случайный `lock_token` +
  compare-and-delete Lua.
- **4.1** — `./backend/app/services/photos_acl.py`: удалена детекция
  `Mock/MagicMock` из прод-кода; тесты перемокканы на публичной границе.
- **6.2** — `./backend/app/models/user.py`: декларация приведена к фактическому
  состоянию БД (функциональный partial unique по `lower(email)`).
- **1.3** — `./backend/app/api/kb/attachments.py`: в `stream_upload_to_path`
  передаётся `allowed_mimes=SAFE_MIME_TYPES` → недопустимый MIME отклоняется (422)
  до записи на диск; устаревший тест `falls_back_to_octet_stream` переписан на
  проверку проброса whitelist.
- **1.4** — `./backend/app/api/kb/export_import.py`: перед созданием новой статьи
  в импорте (`_import_single_article`, оба call-site: single + vault) резолвится
  целевая секция и требуется право `editor` через `require_section_permission`;
  путь `overwrite` остаётся под `require_article_permission`. Добавлен тест на 403.
- **2.4** — `./frontend/src/components/widgets/WorldClockWidget.vue`: добавлено
  отслеживание handle отложенного `setTimeout` (`startTimeout`) и его отмена в
  `onBeforeUnmount` — интервал, создаваемый внутри отложенного `sync`, больше не
  утекает при раннем размонтировании.
- **2.5** — `./frontend/src/stores/photos.ts`: слушатель `photos:processed`
  вынесен в именованный хендлер `_onPhotosProcessed`, добавлен `onScopeDispose`,
  снимающий слушатель, чистящий отложенный таймер и сбрасывающий `_sseInstalled`.
- **3.3** — удалён мёртвый дубль
  `./frontend/src/composables/useArticleFormState.ts`; утилита `getErrorStatus`
  вынесена в `./frontend/src/utils/parseApiError.ts` и переиспользована в
  `pages/composables/useArticleFormState.ts` и `KbArticleFormPage.vue` (локальные
  копии удалены).

**Документация:**
- **6.3** — путь идемпотентности в AGENTS.md синхронизирован с кодом.
- **7.1** — `CLOUD.md` заменён указателем на AGENTS.md + docs/deploy.md.
- **7.2** — ADR-диапазон → ADR-001–ADR-041 (README.md, AGENTS.md).
- **7.3** — диапазон миграций → `001..062` (AGENTS.md).
- **7.5** — описание `/trash` приведено к реальной admin-странице.
- **7.6** — в `helpdesk.md` добавлена пометка «концептуальное ТЗ, не реализовано».
- **7.9** — путь `api/types.gen.d.ts` и перенос DOMPurify во frontend-стек.
- **7.11** — `SECURITY.md`: канал disclosure — GitHub Security Advisory.

**Отклонено:**
- **7.7** — пути тест-скриптов в `testing.md` уже корректны: строки находятся
  внутри блока `cd backend`, добавление префикса `./backend/` их сломало бы.

---

## Журнал сессии 2 (фронтенд-правки)

Серия мелких самодостаточных фронтенд-фиксов. Проверено `eslint` (без новых
ошибок) и `vue-tsc --noEmit` (две оставшиеся ошибки — `ArticleAccessSection.vue`
и неиспользуемый `writeLocalDraft` — преджившие, подтверждено `git stash`).
Юнит-тесты затронутых модулей: **49 passed**.

- **2.6** — `addEventListener` перенесён в `onMounted`:
  `./frontend/src/composables/usePhotoUpload.ts` (слушатель `photos:processed`) и
  `./frontend/src/components/OnboardingTour.vue` (resize/scroll). Cleanup в
  `onBeforeUnmount` сохранён.
- **2.8** — `./frontend/src/components/NotificationsDropdown.vue`: `openDrawer`
  обрабатывает промис `loadNotifications().catch(...)` и показывает
  `message.error(t('common.errorOccurred'))` (добавлен `useMessage`).
- **4.5** — `./frontend/src/pages/KbArticleFormPage.vue`: `Promise.all([fetchSections()])`
  заменён на прямой `await fetchSections()`.
- **4.6** — `./frontend/src/pages/admin/tabs/FileIconsTab.vue`: убраны `console.error`
  из обоих catch-блоков (`onUpload`, `onDelete`).
- **5.3** — `./frontend/src/pages/HomePage.vue`: закрытие баннера сохраняется в
  `sessionStorage` по ключу содержимого (`banner_text|expires_at`) — при смене
  баннера он показывается снова.

**Отклонено:**
- **4.7** — предпосылка неверна: весь редактор-тулбар (включая
  `./frontend/src/components/editor/toolbar/groups/MediaGroup.vue`) использует
  эмодзи/текст-глифы, а не `@vicons/ionicons5`; замена одной кнопки на `<n-icon>`
  внесла бы рассогласование.
