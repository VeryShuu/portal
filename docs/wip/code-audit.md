# Аудит качества кода портала

> Дата: 2026-06-06 · Метод: трёхуровневый аудит (автоматические метрики → целевое AI-ревью → архитектурный анализ).
> Масштаб: backend ~41k LOC (279 файлов), frontend ~73k LOC (347 файлов), 65 миграций, 208 коммитов.
> Цель: оценить общее здоровье проекта и техдолг. Это **диагностический** документ, не план правок.

---

## 1. Executive summary

Проект **значительно здоровее, чем можно ожидать от кодовой базы, написанной разными ИИ-агентами**. Базовая гигиена образцовая: линтеры, типы и тесты проходят на обоих стеках, средняя сложность низкая, дублирование кода ~2%. Это означает, что декларируемый в `AGENTS.md` процесс (DoD: lint+typecheck+tests перед коммитом) реально соблюдался.

Однако глубина «зелёных галочек» обманчива. Найдены:
- **2 подтверждённых CRITICAL-дефекта** в файловом модуле (каскад при переименовании папки; дубликаты `FileItem` при перезаписи) и **1 CRITICAL** в email-outbox (потеря писем при падении воркера).
- **Системный разрыв между line-coverage и function-coverage на фронтенде** (72% строк против **49.8% функций**) — половина функций не вызывается тестами. Это ровно тот риск, о котором предупреждает сам `AGENTS.md`.
- **Дрейф паттернов между модулями** (признак «разных агентов»): часть модулей через сервис-слой, часть — с inline-SQL в роутах; смешение TanStack Query и прямых `fetch`.
- **Осиротевший код** (незавершённый рефакторинг `staff/`), оставленный одним из агентов.

### Оценка по осям (1–5)

| Ось | Оценка | Комментарий |
|---|---|---|
| Базовая гигиена (lint/types) | 5/5 | ruff/mypy/eslint/vue-tsc — 0 ошибок |
| Сложность / читаемость | 4/5 | средняя CC = A, MI всех файлов = A, ~17 «горячих» функций |
| Дублирование | 5/5 | ~2% (Python 0.6%, TS 2.1%) |
| Тестовое покрытие (backend) | 4/5 | 2499 тестов, 78% (line+branch) |
| Тестовое покрытие (frontend) | 2.5/5 | 1300 тестов, но **func-cov 49.8%** |
| Корректность бизнес-логики | 2.5/5 | критичные дефекты в files/email |
| Безопасность | 3.5/5 | ядро auth зрелое, но есть краевые дыры |
| Консистентность архитектуры | 3/5 | заметный дрейф паттернов |
| Документация | 5/5 | 40+ доков, ADR, curated+generated схемы |

**Вердикт:** каркас и инфраструктура — production-grade. Перед продом обязательно закрыть подтверждённые CRITICAL/HIGH в files и email и поднять функциональное покрытие фронта на риск-зонах. Глобальный рефакторинг **не требуется** — проблемы точечные.

---

## 2. Методология

| Уровень | Что делали | Инструменты |
|---|---|---|
| **1. Автометрики** | Линт, типы, сложность, безопасность, мёртвый код, покрытие, дубли, hotspots | ruff, mypy, radon, bandit, vulture, pytest-cov, eslint, vue-tsc, vitest-cov, jscpd, git |
| **2. AI-ревью** | Углублённое ревью 4 доменов 3 моделями (gpt-5-codex, gemini-3-pro, sonnet-4.6) | субагенты + ручная верификация находок |
| **3. Архитектура** | Слоистость, консистентность паттернов, соответствие ADR/docs | grep-анализ + ручная трассировка |

Находки AI-ревью разделены по **уровню достоверности**: `[verified]` — перепроверено чтением кода вручную; `[reported]` — выдано ревьюером, требует подтверждения.

---

## 3. Уровень 1 — Автоматические метрики

### 3.1 Backend (Python)

| Метрика | Результат |
|---|---|
| `ruff check` | **0 нарушений** |
| `mypy app` | **0 ошибок** в 279 файлах |
| Средняя цикломатическая сложность | **A (3.49)**, 1472 блока |
| Maintainability Index | **все 279 файлов = A** |
| Функции сложности D/E | ~17 (макс. E=39) |
| `bandit` | 1 HIGH + 47 всего — **ложные/низкорисковые** (см. ниже) |
| `vulture` (conf≥80) | 42 — почти все ложные (pydantic `cls` в валидаторах) |
| Unit-тесты | **2499 passed**, покрытие **78.1%** (line+branch), порог 75% соблюдён |

**Самые сложные функции** (кандидаты на декомпозицию, не баги):
`system_settings/_settings.py::_apply_settings` (E/31), `photos_acl.py::resolve_folders_permissions_batch` (E/39), `kb_acl/batch.py::batch_resolve_article_permissions` (E/39), `meetings/series_service.py::update_series` (E/38), `meetings/bookings_service/_crud.py::update_booking` (E/31).

**Bandit — разбор (реальной угрозы нет):**
- `files_acl.py:282` SHA1 (HIGH) — это хеш имени файла для cache-key, не для безопасности. Достаточно `usedforsecurity=False`.
- 8× B608 (SQL через f-string, Low confidence) — во всех случаях f-string собирает только статические фрагменты `WHERE`, а пользовательские данные идут через bind-параметры `:param`. Инъекции нет. Стоит добавить `# nosec` с пояснением.
- `keycloak_admin.py:27` bind all interfaces — конфигурационное значение по умолчанию.

**Низкое покрытие у отдельных модулей** (кандидаты на дотест): `worker/tasks/meetings/email.py` (63%), `photos_serializers.py` (57%), `worker/tasks/files.py` (68%), `photos_acl.py` (70%), `worker/tasks/audit.py` (70%).

### 3.2 Frontend (Vue 3 + TS)

| Метрика | Результат |
|---|---|
| `eslint` (lint:check) | **0 нарушений** |
| `vue-tsc` (typecheck) | **0 ошибок** |
| `i18n:check` | **OK**, 1853 ключа, все есть в `en.json` |
| `npm audit` (prod) | **0 уязвимостей** |
| `npm audit` (dev) | 7 (2 critical, 1 high, 4 moderate) — только dev-тулинг (vitest/ws/esbuild), на прод не влияет |
| Unit-тесты | **1300 passed** (90 файлов) |
| Покрытие | statements **72.4%**, branch **81.1%**, **functions 49.8%** |

> ⚠️ **Ключевая находка раздела.** Function-coverage 49.8% при statement-coverage 72% — половина функций не исполняется тестами. Тесты «добирают» строки через `mount`/smoke (`exists()`), но реальные хендлеры (submit, валидация, навигация, bulk-операции) не проверяются. Это в точности риск, описанный в `AGENTS.md` («line-coverage обманчив»). Пример: `PhotosIndexPage.vue` (387 строк, churn-hotspot) — **0% покрытия функций**.

### 3.3 Кросс-метрики

- **Размеры файлов — здоровые.** Макс. backend = 517 строк (`services/directories.py`); макс. реальный frontend = 578 (`StaffDirectoryPage.vue`). «Божественных» модулей (1000+) нет. `types.gen.d.ts` (19k) — авто-генерация, не в счёт.
- **Дублирование — низкое:** Python **0.61%**, TypeScript **2.1%**, CSS 3.63%, markup 3.47%. Итого ~2%. Страх «каждый агент переписывал helpers» **не подтверждается**.
- **Git-hotspots** (наибольший churn = риск-зоны): `NewsFormPage.vue` (23), `main.py` (20), `KbListPage.vue` (19), `ModulesTab.vue`/`FilesPage.vue`/`auth.py` (18), `PhotosIndexPage.vue` (14, при 0% func-cov — двойной риск).
- **Маркеры техдолга:** `TODO/FIXME/HACK` — **0**; `print()` — 3 (мелочь); `except Exception` — 193 (из них 37 через `contextlib.suppress`, голых `except: pass` — 0).

---

## 4. Уровень 2 — Целевое AI-ревью критичных доменов

### 4.1 Auth (Keycloak OIDC + локальный вход + Redis-сессия)

Ядро **зрелое**: PKCE + state + nonce, ротация `session_id`, серверная сессия в Redis, валидация JWT (issuer/audience/signature/exp). Проблемы — в краевых потоках.

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| A1 | HIGH | reported | `api/links.py:100,113`, `services/links_sso.py:29` | `GET /links/{id}/sso-url` возвращает URL с `id_token_hint` в JSON → токен попадает в JS-память/логи. Безопаснее — только серверный 302 (`sso-redirect`). |
| A2 | MEDIUM | reported | `api/auth/oidc.py:73-74` | `code`/`state` обязательны, но есть ветка `if error:`. Callback с `?error=` без `code` → FastAPI 422 до хендлера → аудит `oidc_error` и контролируемый редирект не срабатывают. |
| A3 | MEDIUM | reported | `middleware/csrf.py`, `api/auth/logout.py` | `/auth/logout` exempt от CSRF + есть GET-logout → возможен forced logout с внешнего сайта (UX/DoS-уровень). |
| A4 | LOW | reported | `api/auth/oidc.py:43-68` | Заявленная loop-protection `sso_attempts` реализована на фронте (sessionStorage), серверного guard нет. |

### 4.2 Files / ACL / Sharing

Положительное: `sanitize_name` защищает от path traversal; upload-защита (python-magic + CSP sandbox в preview) надёжна; эскалация через шары исключена на уровне Pydantic (`manager` недоступен). Но каскадные операции реализованы с критическими упущениями.

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| F1 | **CRITICAL** | **verified** | `api/files/folders.py::update_folder` (~221-281) | Переименование папки меняет её `nc_path` и делает `nc.move()`, но **не каскадирует** `nc_path` на дочерние `file_folders`/`file_items`/`file_shares`. Денормализованный `nc_path` потомков остаётся старым → листинг/скачивание вложенных → **404**. (UPDATE есть только в `delete_folder:315`.) |
| F2 | **CRITICAL** | **verified** | `api/files/upload.py:145` + `files_ops.py:70` | Перезалив файла с тем же именем делает `db.add(FileItem(...))` без проверки существования (нет UNIQUE на `(folder_id,name)`). Накапливаются дубли активных `FileItem` → `delete_file` через `scalar_one_or_none()` бросает `MultipleResultsFound` → **HTTP 500**, файл нельзя удалить. |
| F3 | HIGH | reported | `services/files_acl.py` | Создателю папки `manager` выдаётся виртуально в памяти (`if created_by == user.id`), записи в `file_folder_permissions` нет. Рекурсивный CTE ищет только в таблице → менеджер родителя не видит подпапки, созданные другими. |
| F4 | MEDIUM | verified | `services/files_shares_persistence.py` | Атомарность записи `files-shares.json` через in-memory `asyncio.Lock()` — защищает только в одном процессе. При нескольких воркерах (Gunicorn) — гонка read-modify-write, потеря шар. Нужен file-lock/Redis-lock. |
| F5 | MEDIUM | reported | `api/files/folders.py::delete_folder` | Soft-delete папки не инвалидирует `file_shares` (нет `revoked_at`). Листинги шар не фильтруют по `FileFolder.deleted_at` → у получателей висят «битые» шары (404). |
| F6 | LOW | reported | `api/files/_share_drift.py::move_file_shares` | Перемещаются только активные шары; отозванные остаются на старом пути → новый файл с тем же именем наследует чужую историю отзывов. |

### 4.3 Email Outbox (outbox-pattern + ARQ)

Ядро (FOR UPDATE SKIP LOCKED, классификация ошибок, backoff с jitter) реализовано корректно. Но есть критический пробел в recovery.

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| E1 | **CRITICAL** | **verified** | `worker/tasks/email_outbox.py` + `services/email_outbox.py:203-239` | **SENDING-trap.** `claim_pending` переводит строки в `SENDING` отдельным коммитом. Если воркер падает до `mark_sent`/`mark_failed`, строки навсегда застревают: `reschedule_for_retry` разрешает статусы `FAILED/DLQ/CANCELLED/SENT/PENDING`, но **не `SENDING`**. Watchdog отсутствует. Гарантия at-least-once нарушена — письма теряются молча. Нужен requeue по `status='SENDING' AND updated_at < NOW()-interval`. |
| E2 | HIGH | reported | `services/meetings/dispatch.py:23-36` | Meetings шлёт письма через FastAPI `BackgroundTasks` (после коммита бронирования, отдельная сессия) — **нарушение outbox-инварианта** «в той же транзакции». Падение между коммитом и задачей → booking есть, письма нет. Модуль meetings де-факто выведен из-под гарантии атомарности. |
| E3 | HIGH | reported | `worker/tasks/email_outbox.py:116-153` | MIME header injection: `msg["Subject"]=subject` / `msg["To"]=to_email` на политике `compat32` не фильтруют `\r\n`. Источник — `news_title`/`booking.title` из БД. Нужен strip `\r\n` или `email.policy.default`. |
| E4 | MEDIUM | reported | `services/meetings/notifications.py:245` | `html.escape(booking.title)` применён к plain-text Subject → `&amp;` в теме письма + ложное чувство безопасности (не защищает от newline). |
| E5 | MEDIUM | reported | `worker/tasks/notifications.py:143-169` | Глушение исключения внутри `session.begin()` оставляет сессию в `PendingRollback` → последующие вставки в батче падают, счётчик `enqueued` завышен. |
| E6 | MEDIUM | reported | `api/email_outbox.py:70-81` | LIKE-метасимволы (`%`,`_`) в admin-фильтре не экранируются → полный скан. (admin-only, низкий CVSS.) |
| E7 | LOW | reported | `worker/tasks/email_outbox.py:67` | Нет явного SMTP timeout → зависший SMTP держит батч ~20 мин, усугубляя E1. |

---

## 5. Уровень 3 — Архитектурный аудит

### 5.1 Слоистость (backend)

- **Смешанный паттерн доступа к данным.** Бизнес-логика преимущественно в `services/` (хорошо), но **inline-SQL присутствует прямо в роутах**: `db.execute`/`text()` встречаются в `api/kb/*` (sections, tags, comments, versions, trash, permissions…), `api/bookmarks.py`, `api/news_categories.py`, `api/audit.py` и др. При этом `news` имеет аккуратный `repo.py`, а `users` — `users_repo.py`. Это **дрейф между авторами**: одни модули вынесли data-access, другие нет. Не баг, но снижает консистентность и тестируемость.
- 56 из 105 api-файлов импортируют `app.models` напрямую — частично оправдано (под-пакеты с repo-файлами), частично — протечка слоя.

### 5.2 Консистентность (frontend) — признаки «разных агентов»

| # | Severity | Файл | Суть |
|---|---|---|---|
| C1 | **MEDIUM (dead code)** | `components/staff/StaffGrid.vue` + `components/staff/StaffCard.vue` | **Осиротевший рефакторинг.** Агент создал (30 мая) новые `staff/StaffGrid.vue` + `staff/StaffCard.vue`, но `StaffDirectoryPage` остался на старых `StaffGridView` + корневом `components/StaffCard.vue` (17 мая). `StaffGrid.vue` не импортируется никем → он и его `StaffCard` мертвы. Два почти идентичных `StaffCard` сосуществуют. |
| C2 | MEDIUM | `pages/NewsListPage.vue`, `pages/KbArticleFormPage.vue`, `pages/photos/PublicFolderPage.vue`, `PublicPhotoPage.vue` | Прямой `fetch`/`ofetch` в страницах при наличии `queries/`-слоя — расхождение кэша/retry. Часть модулей на TanStack Query, часть — императивно. |
| C3 | MEDIUM | `pages/admin/tabs/EmailOutboxTab.vue` | Для outbox есть query-keys, но таб написан императивно (без TanStack Query), тогда как соседний `AuditTab` — на query. |
| C4 | LOW | `AuditTab.vue`, `SystemTab.vue`, `useNewsFormState.ts` | Разный error-handling: где-то `parseApiError`, где-то всегда `errors.generic`. |
| C5 | LOW | `KbArticleFormPage.vue`, `NewsListPage.vue`, `KbListPage.vue` | Глобальные utility-классы `u-*` вопреки конвенции «без global utility-classes». |

### 5.3 Прочие баги (frontend, из ревью)

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| B1 | HIGH | reported | `pages/photos/MySharesPage.vue:34,87` | `absoluteUrl()` не фильтрует схему URL → `javascript:`/`data:` из backend-данных рендерится кликабельной ссылкой (XSS-вектор). Нужен whitelist `http/https`. |
| B2 | MEDIUM | reported | `components/meetings/RoomGrid.vue:214` | `isToday` через `toISOString().slice(0,10)` (UTC) → off-by-one на границе суток в локальной TZ. |
| B3 | MEDIUM | reported | `pages/photos/PublicFolderPage.vue:228` | `page++` до успешной загрузки → при ошибке страница «теряется», `loadMore` перескакивает данные. |

> Положительное по безопасности фронта: токены в `localStorage` **не найдены** (cookie + CSRF-header, как задекларировано); `v-html` в `NewsDetailPage`/`KbArticlePage` идёт строго через DOMPurify; highlight-утилита `useHighlight.ts` корректно экранирует HTML до вставки `<mark>` — XSS в staff-карточках **нет**.

---

## 6. Приоритизированный бэклог техдолга

### P0 — до прода (подтверждённые critical/high)

1. **F1** Каскадный апдейт `nc_path` (+ `file_shares`) при переименовании папки.
2. **F2** Upsert/проверка существования `FileItem` при перезаливе + UNIQUE `(folder_id, name)` (миграция).
3. **E1** Watchdog для `SENDING` (requeue по таймауту) или включить `SENDING` в `reschedule_for_retry`.
4. **B1** Whitelist схем в `absoluteUrl()` (XSS).
5. **A1** Убрать `id_token_hint` из JSON-ответа `sso-url` (оставить серверный редирект).

### P1 — ближайший спринт

6. **E2** Перенести отправку писем meetings внутрь транзакции бронирования (outbox-инвариант).
7. **E3** Санитизация `\r\n` в MIME-заголовках.
8. **F3** Материализовать `manager` создателю папки в `file_folder_permissions`.
9. **F4/F5** Межпроцессный lock для `files-shares.json`; инвалидация шар при soft-delete папки.
10. **Frontend func-coverage:** поведенческие тесты на риск-зоны (`PhotosIndexPage`, `RoomGrid`, `GlobalSearch`, `NewsFormPage`) — цель func-cov ≥ 70% на hotspots.

### P2 — гигиена / консистентность

11. **C1** Удалить осиротевшие `staff/StaffGrid.vue` + `staff/StaffCard.vue`, оставить один `StaffCard`.
12. **C2/C3** Унифицировать data-fetch на TanStack Query; убрать прямые `fetch` из страниц.
13. **5.1** Вынести inline-SQL из `api/kb/*` и др. в repo/service-слой.
14. **A2/A3/A4, E4–E7, F6, B2/B3, C4/C5** — мелкие фиксы по списку выше.
15. Декомпозиция ~17 функций сложности D/E; дотест backend-модулей < 75%.
16. Добавить в CI: `radon cc --min C` (gate сложности), `knip`/`ts-prune` (мёртвый код фронта), `jscpd` (gate дублей), а также измерение **function-coverage** отдельным порогом.

---

## 7. Что в проекте сделано хорошо (чтобы не сломать)

- Жёсткий DoD реально работает: lint/types/tests зелёные на обоих стеках.
- Outbox-pattern, серверные сессии, ACL через БД, разделение bootstrap/runtime config (ADR-037) — грамотные решения.
- Документация (`docs/`, ADR, curated+generated схемы) — выше среднего по индустрии.
- Низкое дублирование и компактные файлы — структура не «расплылась».
- Защита от path traversal, CSP-sandbox preview, DOMPurify, корректная highlight-утилита.

---

## 8. Дисклеймер по достоверности

Находки `[verified]` (F1, F2, E1, F4) перепроверены чтением кода. Находки `[reported]` получены AI-ревьюерами и требуют подтверждения через воспроизведение/тест перед заведением задач — возможны единичные ложные срабатывания. Рекомендуется на каждый P0/P1 сначала написать падающий тест (воспроизведение), затем фикс.
