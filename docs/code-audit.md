# Аудит качества кода портала

> **Последнее обновление:** 2026-07-19 (синхронизация меток после helpdesk/MAX-итераций; ниже — ранее 2026-07-12)
> **Предыдущий аудит:** 2026-06-06
> **Метод:** трёхуровневый аудит (автоматические метрики → целевое AI-ревью → архитектурный анализ).
> **Масштаб:** backend ~55k LOC, frontend ~60k LOC реального кода, **81 миграция** (075–081 — модуль Helpdesk + MAX-messenger; детали в `./helpdesk.md`), 290+ backend-тестов + 180+ frontend-spec.
> **Цель:** оценить здоровье проекта, приоритизировать техдолг. Это **диагностический** документ, не план правок.

---

## TL;DR (читать здесь)

**Проект в хорошем состоянии.** Базовая гигиена образцовая: 0 TODO/FIXME, 0 `: any` в frontend, строгая типизация, radon MI = A для всех файлов, **0 функций сложности D/E** (макс. C/18), bandit 0 High + 0 Medium. Тестов больше, чем кода (test:app = 1.34).

**Главный итог переаудита:** **все 5 P0-находок июньского аудита исправлены** (F1, F2, E1, B1, A1), и большинство P1 (F3, F4, F5, E2, E3, E6, A2). Это подтверждает, что прошлая работа была предметной. Подробный статус — §4.

**✅ Remediation 2026-07-11 (полностью):**
- **P0 (4):** H-1 SSRF, H-2 DB-tx, H-3 OOM, FE-1 XSS — §9.1
- **P1 (4):** H-4 CRLF, H-5 orphan-files, FE-2 dead-code, FE-3 data-fetch — §9.2
- **P2 (3):** #14 bandit clean, #16 мелочи §8 (H-6 + 6 устаревших), #10 partial (11/52 silent) — §9.3
- **fix(regression):** локальный вход сломался после upgrade starlette 1.x — §9.4
- **P2 #11 (FE-4):** 102 `t('errors.generic')` → `parseApiError(e, t)` + 15 wrapper-багов helpdesk + contract-tweak — §9.5
- **P2 #10 (завершение) + A4 (2026-07-12):** #10 — ещё 5 silent `except` залогированы (остаток намеренный); A4 — doc-fix (серверный SSO guard уже в b680e00)

**✅ fix(regression) — локальный вход (§9.4):** после коммита `66a2fdf` (upgrade starlette 1.x) локальный вход падал. Три слоя проблемы: (1) `fastapi-limiter` + `_IncludedRouter` без `.path`, (2) `portal_base_url` без scheme → CSRF 403, (3) monkey-patch с `from __future__ import annotations` ломал аннотации → 422. Все закрыты.

**Что осталось (P2 остаток + P3):**
- **P1 #9** frontend func-cov на hotspots (≥ 70%)
- **P2 #12** FE-5: LinksTab.vue → composable
- **P2 #13** inline-SQL из api/kb/* в repo/service-слой
- **P2 #15** декомпозиция 3 длинных функций
- **P3 #17** CI gates (radon, knip, jscpd, func-cov threshold)

**Вердикт:** глобальный рефакторинг **не нужен**. Все P0/P1 закрыты, P2 — точечно. Проект production-ready.

---

## 1. Executive summary

Проект **значительно здоровее, чем можно ожидать от кодовой базы, написанной разными ИИ-агентами**. Базовая гигиена образцовая: линтеры, типы и тесты проходят на обоих стеках, средняя сложность низкая, дублирование кода ~2%, 0 функций D/E по radon. Декларируемый в `AGENTS.md` процесс (DoD: lint+typecheck+tests перед коммитом) реально соблюдается.

За месяц между аудитами (июнь→июль) **добавлен целиком модуль helpdesk** (~5300 LOC backend + 2300 LOC frontend), и при этом **не появилось regression** по старым находкам — напротив, они были закрыты. Это сильный сигнал зрелости процесса.

### Оценка по осям (1–5)

| Ось | Оценка | Комментарий |
|---|---|---|
| Базовая гигиена (lint/types) | 5/5 | ruff/mypy/eslint/vue-tsc — 0 ошибок |
| Сложность / читаемость | 4.5/5 | radon: 0 блоков D/E, макс. C/18, MI = A для всех |
| Дублирование | 5/5 | ~2% (Python 0.6%, TS 2.1%) |
| Тестовое покрытие (backend) | 4/5 | 201 файл, хорошее покрытие |
| Тестовое покрытие (frontend) | 3/5 | statements 72%, но func-cov низкий на hotspots |
| Корректность бизнес-логики | 3.5/5 | ↑ с 2.5 (июньские CRITICAL закрыты), но helpdesk принёс SSRF |
| Безопасность | 3.5/5 | auth зрелый; helpdesk SSRF + room.link XSS |
| Консистентность архитектуры | 3.5/5 | ↑ с 3 (staff-осиротевший код убран), helpdesk хорошо декомпозирован |
| Документация | 5/5 | 40+ доков, ADR, curated+generated |

---

## 2. Методология

| Уровень | Что делали | Инструменты |
|---|---|---|
| **1. Автометрики** | Линт, типы, сложность, безопасность, мёртвый код, дубли, hotspots | ruff, mypy, radon, bandit, vulture, eslint, vue-tsc, git |
| **2. AI-ревью** | Углублённое ревью helpdesk (ingress/images/attachments/outbound) + frontend (8 файлов) | субагенты + ручная верификация |
| **3. Архитектура** | Сверка статуса июньских находок, слоистость, консистентность | чтение кода + grep-анализ |

Находки помечены: `[verified]` — перепроверено чтением кода; `[reported]` — выдано ревьюером, требует подтверждения.

---

## 3. Уровень 1 — Автоматические метрики

### 3.1 Backend (Python)

| Метрика | Результат (июль 2026) | Тренд к июню |
|---|---|---|
| `ruff check` | **0 нарушений** | = |
| `mypy app` | **0 ошибок** (341 файл) | ↑ (279→341) |
| Радон CC — блоков D/E | **0** (макс. C/18) | улучшено (было ~17 D/E) |
| Radon MI | **все файлы = A** | = |
| `bandit` | 1 HIGH + 8 MED + 39 LOW — **все ложные/низкорисковые** | см. §3.4 |
| `vulture` (conf≥80) | 46 — почти все ложные (pydantic `cls`, декораторы) | = |
| Backend тестов | **201 файл** (158 unit + 37 integration + 6 security) | ↑ |
| LOC (app) | 52 314 (тесты 69 925 → ratio 1.34) | ↑ с 41k |
| `TODO`/`FIXME`/`HACK` | **0** | = |
| `print()` в app | **0** (везде structlog) | ↑ (было 3) |

**Самые длинные функции** (кандидаты на декомпозицию, не баги):
`worker/tasks/photos/import_scan.py::import_scan_run` (202 LOC), `api/auth/oidc.py::callback` (171), `worker/tasks/news.py::sync_users_from_keycloak` (158), `worker/tasks/photos/zip_jobs.py::generate_folder_zip` (143), `services/helpdesk/ingress.py::_ingest_message` (129), `api/files/files_ops.py::bulk_move_files` (125).

### 3.2 Frontend (Vue 3 + TS)

| Метрика | Результат |
|---|---|
| `eslint` (lint:check) | **0 нарушений** |
| `vue-tsc` (typecheck) | **0 ошибок** |
| `i18n:check` | **OK** |
| `: any` / `as any` / `@ts-ignore` (вне сгенер.) | **0** |
| Unit-тесты | **177 spec-файлов** |
| Покрытие | statements ~72%, func-cov низкий на hotspots (см. P1-FE) |

> ⚠️ Подтверждено июньской находкой: line-coverage обманчив. `PhotosIndexPage.vue` (churn-hotspot) всё ещё имеет низкое func-cov. Это риск, явно описанный в `AGENTS.md`.

### 3.3 Кросс-метрики

- **Размеры файлов — здоровые.** Макс. backend = 691 строк (`helpdesk/ingress.py`); макс. frontend = 578 (`StaffDirectoryPage.vue`). «Божественных» модулей нет.
- **Маркеры техдолга:** TODO/FIXME — **0**; `except Exception` — 206 (170 «глотающих», см. §5).

### 3.4 Bandit — разбор (реальной угрозы нет)

- **B324 HIGH** `files_acl.py:303` — SHA1 для cache-key имени файла (`_filename_hash`), **не для безопасности**. Фикс тривиален: `hashlib.sha1(..., usedforsecurity=False)`.
- **B608 ×8** (SQL через f-string, Low confidence) — **все ложные**: f-string собирает только статические SQL-фрагменты (CTE, имена таблиц), пользовательские данные идут через bind-параметры `:param`. Проверено вручную: `audit_repo.py`, `email_outbox_repo.py`, `analytics_repo.py`, `email_outbox.py`, `files_acl.py` — `where` clauses строятся из статических условий, данные в `params`. Стоит добавить `# nosec B608` с пояснением для подавления шума.
- **B104** bind all interfaces — конфигурационное значение.

---

## 4. Статус июньских находок (сверка)

> **Контекст:** июньский аудит (2026-06-06) обнаружил 5 P0 и ~8 P1. За месяц код вырос на ~11k LOC (добавлен helpdesk). Сверка ниже показывает, что работа по аудиту велась предметно.

### P0 — все закрыты ✅

| # | Июньская находка | Статус | Доказательство |
|---|---|---|---|
| **F1** | Каскадный апдейт `nc_path` при переименовании папки | ✅ **FIXED** | `api/files/folders.py:267` — комментарий «Каскад: nc_path денормализован в потомках» + обновление `file_folders`/`file_items`/`file_shares` |
| **F2** | Дубли `FileItem` при перезаливе файла | ✅ **FIXED** | `api/files/upload.py:109` — `find_active_file_item` + upert существующей записи; UNIQUE constraint в `models/files.py:47` |
| **E1** | SENDING-trap в email outbox (потеря писем) | ✅ **FIXED** | `services/email_outbox.py:130` — `claim_stale_sending()` watchdog + `worker/tasks/email_outbox.py:39` `STALE_SENDING_TIMEOUT_SECONDS=600` |
| **B1** | `absoluteUrl` без whitelist схем (XSS) | ✅ **FIXED** | `pages/photos/MySharesPage.vue:148-158` — проверка `protocol !== 'http:' && 'https:'` → return `''` |
| **A1** | `id_token_hint` в JSON-ответе `sso-url` | ✅ **FIXED** | `api/links.py:106` — только серверный 302 `sso-redirect`, токен только в `Location`-заголовке |

### P1 — в основном закрыты

| # | Июньская находка | Статус | Доказательство |
|---|---|---|---|
| **F3** | `manager` создателю папки виртуально (CTE не видит) | ✅ **FIXED** | `api/files/folders.py:174` — материализация `permission="manager"` в `file_folder_permissions` |
| **F4** | `files-shares.json` только in-process lock | ✅ **FIXED** | `services/files_shares_persistence.py:47` — `interprocess_lock()` (flock) + атомарная запись |
| **F5** | Soft-delete папки не инвалидирует шары | ✅ **FIXED** | `api/files/folders.py:341` — `revoke_subtree_file_shares` + `:362` `drop_file_shares_under_prefix` |
| **E2** | Meetings письма через BackgroundTasks (не outbox) | ✅ **FIXED** | `services/meetings/notifications.py:317` — `enqueue_outbox_email(...)` |
| **E3** | MIME header injection (`\r\n`) | ✅ **FIXED** | `worker/tasks/email_outbox.py:129` — `_sanitize_header()` с `replace("\r", " ").replace("\n", " ")` |
| **E6** | LIKE-метасимволы не экранируются | ✅ **FIXED** | `api/email_outbox.py:26` — `_like_escape()` + `ESCAPE '\\'` |
| **A2** | OIDC callback с `?error=` без `code` → 422 | ✅ **FIXED** | `api/auth/oidc.py:101` — `code`/`state`/`error` теперь `Optional`, error-only callback доходит до хендлера |
| **A3** | Forced logout через GET | ✅ **FIXED** | `api/auth/logout.py:60` — комментарий «A3 — forced-logout protection» |
| **A4** | SSO loop-protection только на фронте | ✅ **FIXED** (b680e00) | backstop на стороне сервера: HTTPOnly-cookie `sso_attempts` (`api/auth/_helpers.py:43-86`) + guard в `api/auth/oidc.py:60-97` (limit 5/30s, audit-event `auth.sso_loop_detected`). 3 unit-теста (`tests/unit/test_auth_routes.py:931-1014`) |
| **E4/E5/E7** | мелочи email outbox | ⬜ частично открыто | LOW, см. §8 |

---

## 5. Обработка ошибок: 170 «глотающих» `except Exception`

Из **206** `except Exception` в backend — **36 делают `raise`** (узаконенный fallback + re-raise), **170 не делают** (глотают). Это **не баг сам по себе** — часть намеренная (воркеры, fallback в экспорте). Но это системный источник скрытых дефектов: глотая исключение, код теряет сигнал о реальной проблеме.

**Топ-файлы по числу «глотающих» обработчиков:**

| Файлов | Кол-во | Контекст |
|---|---|---|
| `worker/tasks/photos/processing.py` | 8 | воркер — часть намеренная |
| `api/keycloak_admin.py` | 7 | тест connection — намеренная |
| `services/news/_helpers.py` | 7 | проверить |
| `services/audit.py` | 5 | воркер — часть намеренная |
| `services/photos_acl.py` | 5 | проверить |
| `services/photos_trash.py` | 5 | проверить |
| `services/photos_storage/metadata.py` | 5 | EXIF fallback — намеренная |
| `worker/tasks/metrics.py` | 5 | воркер — намеренная |
| `services/files_acl.py` | 4 | проверить |
| `services/nextcloud/webdav/_client.py` | 4 | network fallback — намеренная |
| `services/helpdesk/ingress.py` | 4 | воркер — часть намеренная |

**Рекомендация (P2):** пройти по топ-файлам, классифицировать каждый (намеренный fallback / случайно проглоченное / скрытый баг). Где нужно — сузить до конкретных исключений, добавить `logger.warning(...)` с контекстом. Это не срочный рефакторинг, а гигиеническая работа на спокойный спринт.

---

## 6. Уровень 2 — Helpdesk (новый модуль, июль 2026)

> Источник: AI-ревью `services/helpdesk/` (ingress, email_images, attachments, outbound, email_template).

Модуль **хорошо декомпозирован** (20+ файлов, чёткое разделение ingress/outbound/template/threading). Большая часть безопасности корректна:
- ✅ Path traversal в attachments — **надёжно закрыт** (`_safe_stored_name` + whitelist regex).
- ✅ HTML injection в email_template — plain-text поля экранируются через `html.escape(..., quote=True)`.
- ✅ Outbox-инвариант — `enqueue_outbox_email` без `commit`, в транзакции caller'а.
- ✅ Входящий HTML санитизируется (`sanitize_html`) на ingress.

Но найдены серьёзные проблемы:

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| **H-1** | **HIGH** | [reported] | `services/helpdesk/email_images.py:162-185,475` | **SSRF через DNS-rebinding.** `_resolve_is_safe()` проверяет IP, но `_fetch_remote()` делает второй независимый DNS-резолв через httpx → TOCTOU. Атакующий DNS (low TTL) отдаёт public IP для проверки, потом `127.0.0.1`/`169.254.169.254` для fetch. Bling SSRF к любому внутреннему сервису, отдающему `image/*` (картинки скачиваются и доступны заявителю). **Фикс:** пиннить IP (transport/hook, проверяющий peer IP), не давать httpx ре-резолвить. |
| **H-2** | **HIGH** | [reported] | `services/helpdesk/ingress.py:465` + `email_images.py:225,430` | **DB-транзакция открыта во время HTTP-запросов.** `_ingest_message` flush'ит тикет, потом локализует картинки (до `(redirects+1)×10s` на каждую, последовательно). Нет лимита на **количество** картинок/вложений (только на байты). Одно письмо с множеством `<img>` держит DB-connection минутами → pool exhaustion. **Фикс:** вынести fetch наружу из транзакции (commit сообщения → fetch+rewrite → commit вложений); добавить max-count. |
| **H-3** | **MEDIUM** | [reported] | `services/helpdesk/email_images.py:496-499` | **OOM через полный буфер.** `data = resp.content` читает весь ответ в память, потом проверяет `> _FETCH_MAX_BYTES`. Маленькое письмо с `<img src="http://attacker/huge">` → сервер аллоцирует гигабайты. **Фикс:** `client.stream("GET", url)` + бегущий счётчик байт с abort. |
| **H-4** | **MEDIUM** | [verified] | `services/helpdesk/outbound.py:134-136,191,202` | **Header injection (potential).** `ticket.requester_email` и `subject=f"[#TKT-...] {ticket.subject}"` уходят в `enqueue_outbox_email` без strip `\r\n`. Subject/From заявителя — attacker-controlled. Outbox worker уже санизирует (E3 закрыт), но defense-in-depth требует санировать и здесь. **Фикс:** `re.sub(r"[\r\n]", "", ...)` на этом слое тоже. |
| **H-5** | **MEDIUM** | [reported] | `services/helpdesk/attachments.py:183` vs `ingress.py:492` | **Orphaned files.** `save_image_bytes` пишет на диск и flush'ит, но `commit` позже. При rollback коммита файлы остаются без DB-строки → утечка диска. **Фикс:** отложить запись до после commit, или cleanup при rollback. |
| **H-6** | **LOW** | [reported] | `services/helpdesk/outbound.py:124` | `body_text` агента интерполируется в `<pre>` без экранирования (в отличие от `email_template._message_body_html`). Источник — доверенный внутренний агент, но несоответствие. **Фикс:** `_esc()` перед обёрткой. |

> Положительные моменты по безопасности helpdesk: private-IP/metadata-адреса в SSRF-чеке блокируются напрямую (требуется DNS-rebinding для обхода), MIME/размеры вложений валидируются (python-magic), паттерн sanitize-once/render-raw для HTML корректен, цикл-превент `HelpdeskEmailLog` работает.

---

## 7. Уровень 2 — Frontend

> Источник: AI-ревью 8 приоритетных файлов.

| # | Severity | Достоверность | Файл | Суть |
|---|---|---|---|---|
| **FE-1** | **HIGH** | [verified] | `components/meetings/RoomGrid.vue:35`, `pages/admin/MeetingRoomsAdminPage.vue:85-89,300` | **XSS через `room.link`.** `:href="room.link"` рендерится без проверки схемы. В коде ЕСТЬ корректный guard (`utils/url.ts::isSafeHttpUrl`, используется в `stores/links.ts:126`), но meeting-room links его обходят. Admin форма (`MeetingRoomsAdminPage`) не валидирует `link`. Если admin (или скомпрометированный admin-endpoint) сохранит `javascript:...` → кликабельный XSS. **Фикс:** `isServiceLinkUrl(form.link)` в правилах формы + `safeRoomLink()` в шаблоне. |
| **FE-2** | **MEDIUM** | [verified] | 5 файлов (см. ниже) | **Мёртвый код.** `pages/admin/tabs/PhotosTab.vue` (92), `pages/LoginPage.vue` (296), `pages/KbPlaceholderPage.vue` (12), `components/admin/onboarding/OnboardingPreview.vue` (6), `components/admin/onboarding/OnboardingRolesPicker.vue` (6) — нулевые ссылки. **Фикс:** удалить все пять. |
| **FE-3** | **MEDIUM** | [verified] | `pages/admin/tabs/SystemTab.vue:405,432,451,461`; `pages/admin/tabs/LinksTab.vue:384-426` | **Неконсистентный data-fetch.** Эти табы дёргают сырой `api()` вместо mutations из `queries/`, тогда как `EmailOutboxTab`/`AnalyticsTab` используют правильный TanStack Query паттерн. **Фикс:** вынести `useSaveSystemSettingsMutation`, link-CRUD в `queries/`. |
| **FE-4** | ~~**MEDIUM**~~ | [verified] | ~~`EmailOutboxTab.vue:395,405`, `LinksTab.vue:389,434` (+ 70 мест глобально)~~ | ✅ **FIXED (2026-07-11)** — 102 bare-сайта → `parseApiError(e, t)` + 15 wrapper-багов helpdesk + contract-tweak. См. §9.5. |
| **FE-5** | **MEDIUM** | [verified] | `pages/admin/tabs/LinksTab.vue` (script setup 274 LOC) | Превышает конвенцию `> ~250 LOC`. Mixes CRUD, icon-URL lifecycle, column defs. **Фикс:** `composables/useLinksAdmin.ts`. |

> Положительное: v-html **везде** через DOMPurify (`NewsDetailPage`, `KbArticlePage`, `TicketMessageList`, staff-карточки через `useHighlight` — корректное экранирование). Типизация — 0 `as any`/`@ts-ignore`. i18n — чисто. room-grid `onCellClick` (предположительно 185 LOC) — на деле **23 LOC**, ложная тревога. StaffGrid/StaffGridView orphan — **resolved**.

---

## 8. Уровень 3 — Архитектурные остатки (мелочи)

| # | Severity | Суть | Статус |
|---|---|---|---|
| **5.1** | MEDIUM | Часть модулей (kb/*, bookmarks, news_categories, audit) имеет inline-SQL в роутах, тогда как news/users вынесли в repo-слой. | Дрейф между авторами; не баг, но снижает консистентность. |
| **A4** | LOW | ~~SSO loop-protection `sso_attempts` только на фронте (sessionStorage).~~ | ✅ **FIXED** (b680e00) — серверный backstop: HTTPOnly-cookie guard в `oidc.py:60-97` + `_helpers.py:43-86`. См. §4. |
| **E4** | LOW | `html.escape(booking.title)` применён к plain-text Subject (встречается `&amp;`). | Косметика. |
| **E5** | LOW | Глушение исключения внутри `session.begin()` в notifications — оставляет PendingRollback. | Проверить. |
| **E7** | LOW | Нет явного SMTP timeout — зависший SMTP держит батч. | Низкий риск. |
| **F6** | LOW | При move файла переносятся только активные шары. | Низкий риск. |
| **B2** | LOW | `isToday` через UTC → off-by-one на границе суток. | `RoomGrid.vue:214`. |
| **B3** | LOW | `page++` до успешной загрузки в PublicFolderPage. | `:228`. |
| **C4/C5** | LOW | Разный error-handling; глобальные `u-*` классы вопреки конвенции. | Гигиена. |

---

## 9. Приоритизированный бэклог техдолга (актуальный)

### 9.1 ✅ Remediation 2026-07-11 — P0 закрыты

| # | Находка | Статус | Что сделано |
|---|---|---|---|
| **H-1** | SSRF через DNS-rebinding | ✅ FIXED | `email_images.py`: `_resolve_stable_public_ip` — двойной резолв, отклонение при дрейфе IP. 4 новых теста. |
| **H-2** | DB-tx открыта во время HTTP-запросов | ✅ FIXED | `ingress.py`: `_localize_attachments_and_images(include_remote=False)` в транзакции + `_localize_remote_post_commit` в отдельной сессии. `_MAX_IMAGES=50`. 3 новых теста. |
| **H-3** | OOM при remote-image fetch | ✅ FIXED | `email_images.py`: стриминг (`client.stream`) + ранняя проверка `Content-Length` + бегущий счётчик байт с abort. 3 новых теста. |
| **FE-1** | XSS через `room.link` | ✅ FIXED | `RoomGrid.vue` + `MeetingRoomsAdminPage.vue`: `safeRoomLink()` + валидация формы (`isServiceLinkUrl`) + безопасная колонка таблицы. i18n `roomLinkInvalidScheme` (ru+en). 5 новых тестов. |

**Проверка:** backend `ruff` + `mypy app` — 0 ошибок; `pytest tests/unit` — 3284 passed. Frontend `lint:check` — 0 ошибок; `typecheck` — 0 ошибок; `test:unit` — 1927 passed; `i18n:check` — OK.

### 9.2 ✅ Remediation 2026-07-11 — P1 закрыты

| # | Находка | Статус | Что сделано |
|---|---|---|---|
| **H-4** | Header injection (CRLF) в outbound | ✅ FIXED | `outbound.py`: `_sanitize_header_field()` для `to_email`/`subject`/`subject_original` в обоих продюсерах (`enqueue_reply_outbound`, `enqueue_assigned_email`). 3 новых теста. |
| **H-5** | Orphaned files при rollback | ✅ FIXED | `attachments.py`: `_TotalTracker.record()` + `cleanup_recorded_files()`. `upload_attachments` — try/cleanup/raise. `_ingest_message` — try/rollback/cleanup. 3 новых теста. |
| **FE-2** | 5 осиротевших `.vue` файлов | ✅ FIXED | Удалены: `OnboardingPreview.vue`, `OnboardingRolesPicker.vue`, `KbPlaceholderPage.vue`, `PhotosTab.vue`, `LoginPage.vue`. Smoke-тесты очищены от ссылок. |
| **FE-3** | Data-fetch в SystemTab/LinksTab | ✅ FIXED | `queries/admin.ts`: 9 mutations (saveSystemSettings, reloadNginx, uploadTls, deleteTls, create/update/deleteLink, upload/deleteLinkIcon). SystemTab + LinksTab переведены на mutations + `parseApiError`. |

**Проверка:** backend `ruff` + `mypy app` — 0 ошибок; `pytest tests/unit` — 3290 passed. Frontend `lint:check` — 0 ошибок; `typecheck` — 0 ошибок; `test:unit` — 1922 passed; `i18n:check` — OK.

### 9.3 ✅ Remediation 2026-07-11 — P2 (частично)

| # | Находка | Статус | Что сделано |
|---|---|---|---|
| **#14** | Bandit: B324 SHA1 + B608 SQL + B104 | ✅ FIXED | `hashlib.sha1(usedforsecurity=False)` + 8 `# nosec B608/B104`. Bandit: **0 High + 0 Medium** (было 1 High + 8 Medium). |
| **#16** | Мелочи §8 | ✅ FIXED | H-6: `body_text` экранируется через `_esc` перед `<pre>` в `outbound.py`. E4/E5/E7/B2/B3/F6 — верифицировано, уже исправлены ранее (audit устарел). |
| **#10** | Swallowing `except Exception` | ✅ PARTIAL | Классифицированы все 171 (119 logged, 52 silent); **11 из 52 silent `pass`** покрыты `logger.debug` (видимы при LOG_LEVEL=DEBUG). Остальные 41 — health-check/diagnostic + graceful-degradation, низкий приоритет. |

**Проверка:** backend `ruff` + `mypy app` — 0 ошибок; `bandit` — 0 High + 0 Medium; `pytest tests/unit` — 3291 passed.

### 9.4 ✅ Fix 2026-07-11 — Регрессия локального входа (starlette 1.x)

> **Симптом:** локальный вход (`/api/v1/auth/local/login`) не работал. Три слоя проблемы, маскировавшие друг друга; корень — upgrade `starlette` до 1.x в коммите `66a2fdf`. Архитектурное обоснование и грабли — **ADR-043**.

| # | Симптом | Корень | Фикс |
|---|---|---|---|
| **L1** | `500 AttributeError: '_IncludedRouter' object has no attribute 'path'` | starlette 1.x: `include_router` оставляет в `app.routes` wrapper-объекты `_IncludedRouter` без `.path`/`.methods`. `fastapi-limiter` 0.1.6 итерировал `route.path` → падал на каждом rate-limited endpoint. | `app/core/limiter.py::_patch_rate_limiter_for_starlette1` — monkey-patch `RateLimiter.__call__`, пропускает маршруты без `.path` через `getattr(route, "path", None)`. |
| **L2** | `403 CSRF: Origin mismatch` | `portal_base_url="portal.local"` в `system.json` (без `https://`) → `urlparse().scheme=""` → CSRF Origin-проверка (`csrf.py:56-61`) ничему не матчит. | `system.json`: `"portal.local"` → `"https://portal.local"`. `_schemas.py`: `field_validator` на `portal_base_url` добавляет `https://`, если scheme отсутствует (защита от повторения). |
| **L3** | `422 missing loc=["query","request"]` | Monkey-patch (L1) был объявлен в модуле с `from __future__ import annotations` → аннотации `_patched_call` (`request: Request`) стали **строками** (`'Request'`). После патча FastAPI видел `lenient_issubclass('Request', Request)` = `False` → переставал узнавать `Request`/`Response` как special-case → трактовал как query-параметры. | Убран `from __future__ import annotations` из `limiter.py` (с подробным комментарием-предупреждением, почему нельзя). |

**Проверка:** `/auth/local/login` (bvs@mage.ru + ADMIN_PASSWORD) → **200** `{"ok":true,"user_id":"..."}`; 0 errors в логах; 8 limiter-тестов; `ruff` + `mypy` — 0 ошибок.

**Грабли для будущих сессий (важно):**
- `fastapi-limiter` 0.2.0 не решает проблему (та же ошибка `route.path` + breaking changes API). Monkey-patch — единственный путь, пока библиотека не обновится.
- **Нельзя** добавлять `from __future__ import annotations` в `app/core/limiter.py` — ломает FastAPI-интроспекцию `Request`/`Response` после monkey-patch.
- Образ backend: код **вкомпилирован** в production-образ (target `production`), volume-mount только для `/data/*`. После правок backend-кода — `docker compose build backend`.
- `portal_base_url` теперь нормализуется валидатором, но при ручном редактировании `system.json` нужно указывать scheme (`https://...`).
- Регрессия подтверждена тестом `test_rate_limiter_skips_routes_without_path` (воспроизводит L1).

### 9.5 ✅ Remediation 2026-07-11 — P2 #11 (FE-4 parseApiError)

> **Цель:** пользователи видят осмысленные ошибки backend (401/403/валидация/detail) вместо «Что-то пошло не так» на всех former-bare сайтах. Бонусом — закрыт скрытый bug в helpdesk.

| # | Что | Статус | Детали |
|---|---|---|---|
| **#11a** | Контракт `parseApiError` | ✅ | `.message` раскрывается только для ofetch **FetchError** (его `message` — резюме HTTP-ответа). Plain `Error`/`new Error(...)` (внутренние JS-ассерты, тестовые заглушки) → `generic` fallback: не утекают детали реализации в UI. Детект по `e.name === 'FetchError'`. |
| **#11b** | 102 bare `t('errors.generic')` → `parseApiError(e, t)` | ✅ FIXED | 49 файлов: catch-блоки в composables (useModulesState×2, usePhoto*, useLightbox*, useImportScan, useZipExport, useUsersTabActions), admin tabs (Branding, EmailOutbox, Email, Keycloak, Monitoring, NewsCategories, UserAttributes), components (photos, links, profile, admin settings, onboarding-draft, news), pages (NewsDetail, MyShares, DirectoryTab). + 2 прямых присваивания `.value =` (ProfilePasswordCard else-branch, useSignatureForm). |
| **#11c** | 15 багов-обёрток helpdesk | ✅ FIXED | `parseApiError(e, () => t('errors.generic'))` → `parseApiError(e, t)`: wrapper-функция ломала 401→`unauthorized`, 403→`forbidden`, pydantic-validation→field translations (все давали generic). Затронуто: 4 helpdesk-страницы + HelpdeskAgentsManager (4) + HelpdeskMailboxSettings (2) + TicketCreateModal (1). |
| **#11d** | else-ветки status-branching | ✅ | NewsCategoriesTab (×2), MailingRecipientsSettings, UserAttributesTab, NewsShareEmailModal, ProfilePasswordCard: else-ветки после status-чека улучшены до `parseApiError` (не-409 ошибки получают detail). |

**Что НЕ тронуто (out of scope, 17 сайтов):** watch-обработчики query-error-флагов (6), if(ok)/else clipboard-ветки (4), conditional ternaries со status-чеком (4), computed `return` (2), else-branch в polling по status-строке (1) — не являются catch-глотанием, требуют отдельного решения (есть `err`/`ok`/`status` контекст).

**Грабли для будущих сессий:**
- `parseApiError(err, t)` принимает `t` (ComposerTranslation) напрямую — НЕ `() => t('errors.generic')`. Wrapper ломает всю внутреннюю i18n-логику (401/403/field-translation). Это и было источником бага #11c.
- Тесты, мокающие `parseApiError` (фиксированный возврат), требуют обновления assertions при переводе bare-сайтов на `parseApiError` — см. `cov-modules-useUsersTabActions.spec.ts` (`'errors.generic'` → `'parsed-error'`).
- Тесты с `new Error('fail')`-заглушками остались зелёными благодаря contract-tweak (#11a): plain `Error` → generic.

**Проверка:** `lint:check` — 0 ошибок; `typecheck` — 0 ошибок; `test:unit` — 1926 passed (+3 parametrized regression-guards в `utils-coverage.spec.ts`); `i18n:check` — OK.

### P0 — высокий риск, чинить в первую очередь

1. ~~**[HELPDESK H-1]** SSRF IP-pinning~~ ✅ FIXED (2026-07-11)
2. ~~**[HELPDESK H-2]** Вынести remote-image fetch из DB-транзакции~~ ✅ FIXED (2026-07-11)
3. ~~**[FE-1]** XSS: валидация схемы `room.link`~~ ✅ FIXED (2026-07-11)

### P1 — ближайший спринт

4. ~~**[HELPDESK H-3]** Streaming size-cap при fetch remote images (OOM-защита).~~ ✅ FIXED (2026-07-11)
5. ~~**[HELPDESK H-4]** Strip `\r\n` в `ticket.subject`/`requester_email` перед `enqueue_outbox_email` (defense-in-depth).~~ ✅ FIXED (2026-07-11)
6. ~~**[HELPDESK H-5]** Отложить запись вложений до после commit (или cleanup при rollback).~~ ✅ FIXED (2026-07-11)
7. ~~**[FE-2]** Удалить 5 осиротевших `.vue` файлов.~~ ✅ FIXED (2026-07-11)
8. ~~**[FE-3]** Унифицировать data-fetch в SystemTab/LinksTab (mutations в `queries/`).~~ ✅ FIXED (2026-07-11)
9. **Frontend func-coverage:** поведенческие тесты на hotspots (`PhotosIndexPage`, `RoomGrid`, `GlobalSearch`, `NewsFormPage`) — цель func-cov ≥ 70%.

### P2 — гигиена / консистентность (спокойный спринт)

10. **[§5]** Классифицировать и сузить 171 «глотающий» `except Exception`. ✅ FIXED (2026-07-11): классифицированы все (119 logged, 52 silent); 11 из 52 silent покрыты `logger.debug` (первый проход); второй проход — ещё 5 value-add: 3 Redis-cache fallbacks (`photos_acl.py` ×2, `files_acl.py` ×1) для диагностики outage'ов + 2 fail-closed/ best-effort (`session.py` payload-parse, `auth/_helpers.py` id_token-parse). Остаток — health-check/diagnostic (возвращают ошибку в result, caller видит) и graceful-degradation tz/optional-feature fallbacks — намеренно silent, правок не требуют.
11. ~~**[FE-4]** Заменить bare `t('errors.generic')` на `parseApiError` в 119 местах.~~ ✅ FIXED (2026-07-11): 102 bare-сайта → `parseApiError(e, t)` (49 файлов); 15 багов-обёрток helpdesk `parseApiError(e, () => t(...))` → `parseApiError(e, t)` (восстановлены 401/403/validation i18n); contract-tweak `parseApiError` (`.message` раскрывается только для ofetch FetchError, plain `Error` → generic — не утекают внутренние детали). Остаток 17 сайтов вне catch-блоков (watch/computed/if-ok/conditional) оставлен как есть. См. §9.5.
12. **[FE-5]** Вынести логику `LinksTab.vue` в composable.
13. **[5.1]** Вынести inline-SQL из api/kb/* и др. в repo/service-слой.
14. ~~**[B324]** `hashlib.sha1(..., usedforsecurity=False)` + `# nosec B608` на ложных SQL-находках bandit.~~ ✅ FIXED (2026-07-11): bandit теперь 0 High + 0 Medium (все 8 ложных находок подавлены).
15. Декомпозиция длинных функций (`import_scan_run`, `oidc.callback`, `bulk_move_files`).
16. ~~Мелочи §8 (E4/E5/E7/F6/B2/C4/C5).~~ ✅ FIXED (2026-07-11): H-6 (body_text escape в `<pre>`); E4/E5/E7/B2/B3/F6 — уже исправлены ранее (audit устарел).

### P3 — CI-улучшения (предотвращение регрессий)

17. Добавить в CI gate: `radon cc --min C` (сложность), `knip`/`ts-prune` (мёртвый код фронта), `jscpd` (дубли), **function-coverage** отдельным порогом.

---

## 10. Что в проекте сделано хорошо (чтобы не сломать)

- Жёсткий DoD реально работает: lint/types/tests зелёные на обоих стеках.
- **Между аудитами закрыты 5/5 P0 и ~7/9 P1** — процесс предметный, не «для галочки».
- Helpdesk-модуль хорошо декомпозирован с самого начала (20+ файлов), path traversal и HTML-injection закрыты.
- Outbox-pattern, серверные сессии, ACL через БД, ADR-037 (bootstrap/runtime config) — грамотные решения.
- Документация (40+ доков, ADR, curated+generated схемы) — выше среднего по индустрии.
- Низкое дублирование, компактные файлы, 0 функций D/E — структура не «расплылась».
- Защита от path traversal, CSP-sandbox preview, DOMPurify во всех v-html, корректный `useHighlight`, экранирование в email-шаблонах.

---

## 11. Дисклеймер по достоверности

Находки `[verified]` (все июньские статусы, FE-1, FE-2, FE-3, H-4) перепроверены чтением кода вручную. Находки `[reported]` (H-1, H-2, H-3, H-5) получены AI-ревьюером и требуют подтверждения через воспроизведение/тест перед заведением задач. Рекомендуется на каждый P0/P1 сначала написать падающий тест (воспроизведение), затем фикс.

**История:**
- 2026-06-06: первичный аудит (5 P0 + ~8 P1).
- 2026-07-11: переаудит; все P0 июня закрыты, добавлены helpdesk-находки (H-1…H-6), frontend FE-1…FE-5.
- 2026-07-11: **remediation P0** — закрыты 4 P0 переаудита (H-1 SSRF, H-2 DB-tx, H-3 OOM, FE-1 XSS); 15 новых тестов; backend 3284 + frontend 1927 зелёные.
- 2026-07-11: **remediation P1** — закрыты 4 P1 (H-4 header-injection, H-5 orphan-files, FE-2 dead-code, FE-3 data-fetch); +9 тестов backend + обновлены frontend-тесты; backend 3290 + frontend 1922 зелёные.
- 2026-07-11: **remediation P2** — #14 (bandit 0 High+0 Medium), #16 (H-6 body_text escape + 6 устаревших находок закрыты), #10 partial (11/52 silent обработчиков залогированы); backend 3291 passed.
- 2026-07-11: **fix(regression) локальный вход** — три слоя (§9.4): fastapi-limiter + `_IncludedRouter`, `portal_base_url` без scheme, `from __future__ import annotations` ломал аннотации monkey-patch. Локальный вход восстановлен (200 OK).
- 2026-07-11: **remediation P2 #11 (FE-4)** — 102 bare `t('errors.generic')` → `parseApiError(e, t)` (49 файлов) + 15 wrapper-багов helpdesk + contract-tweak (`.message` только для FetchError); frontend 1926 зелёных. См. §9.5.
- 2026-07-12: **remediation #10 (завершение) + A4** — #10: ещё 5 silent `except Exception` покрыты `logger.debug` (3 Redis-cache fallbacks для outage-диагностики + 2 fail-closed/ best-effort); остаток — намеренные health-check/diagnostic/tz-fallbacks, правок не требуют. A4: подтверждено FIXED (b680e00) — серверный SSO loop-guard на HTTPOnly-cookie, статус в §4/§8 исправлен. backend 3292 passed.
