# Модуль «Генератор email-подписей»

> **Когда читать:** правишь генератор HTML-подписей сотрудников (форма → preview →
> копирование/скачивание `.htm`), меняешь матрицу «устройство × язык → логотип/
> вёрстка», настраиваешь города/телефоны/домен.
> **Legacy:** исходный PHP-сервис `./sign` уже перенесён и **удалён из репозитория**;
> источник истины теперь — этот файл + тесты (см. §4, §9).
> **Ключевой код:** `./backend/app/api/signature.py`, `./backend/app/services/signature.py`,
> `./backend/app/services/signature_settings.py`, `./backend/app/schemas/signature.py`,
> `./frontend/src/pages/SignaturePage.vue`, `./frontend/src/pages/composables/useSignatureForm.ts`,
> `./frontend/src/components/signature/SignaturePreview.vue`,
> `./frontend/src/components/signature/SignatureActions.vue`,
> `./frontend/src/components/admin/SignatureModuleSettings.vue`,
> `./frontend/src/api/signature.ts`, `./frontend/src/queries/signature.ts`.
> **ADR:** специального ADR нет; решения зафиксированы в этом файле (источник —
> перенос `./sign`).

> Модуль повторяет функциональность standalone PHP-сервиса `./sign` (PHP+Nginx+
> jQuery) на стеке портала (Vue 3 + FastAPI). Сотрудник заполняет форму, видит
> live-preview подписи в `iframe`, копирует HTML в буфер или скачивает `.htm`
> для вставки в почтовый клиент. Модуль **stateless** — БД-таблиц нет, ПДн не
> сохраняются (в оригинале подписи писались в webroot `trash/` — утечка ПДн,
> здесь устранена).

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/signature.py`), без БД (stateless) |
| Frontend | Vue 3 + Pinia + TanStack Query + Naive UI (`./frontend/src/pages/SignaturePage.vue`) |
| Хранилище | Нет (рендер in-memory). Runtime-конфиг — `/data/settings/signature.json` |
| Префикс API | `/api/v1/signature` |
| Master-flag | `signature.enabled` в `/data/settings/modules.json` (выкл → весь раздел `404`) |
| Логотипы | Внешние ссылки на `http://mage.ru/signature/images/` (локально НЕ хостятся) |
| Email-домен | Строго `@mage.ru` (константа в коде, не настройка) |

### Возможности
- **Форма подписи**: имя (≤20), фамилия (≤20), должность (≤150), язык, устройство,
  город, городской телефон (из списка) + 3-значный добавочный, мобильный
  (опционально), email (`@mage.ru`).
- **Языки** `Ru` / `Eng`: переключают список городов на локализованные названия и
  суффикс должности.
- **Устройства** `PC` / `Web` / `Apple` / `Phone` — разная вёрстка и логотип
  (см. §4 матрица).
- **Предзаполнение из профиля** (`UserMe`): ФИО, должность, email, язык, мобильный.
- **Live-preview** в изолированном `iframe` (`srcdoc`).
- **Копирование** HTML (rich-text через `ClipboardItem text/html`) и **скачивание**
  `.htm` (имя файла с суффиксом по устройству/языку).
- **Admin-настройки**: города, городские телефоны, email техподдержки,
  `company_url`, `logo_base_url`.

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/signature.py` | API: config / generate / download + admin settings |
| Service (render) | `./backend/app/services/signature.py` | Pure-рендер HTML (`_render_table` / `_render_phone`), без шаблонизатора |
| Service (config) | `./backend/app/services/signature_settings.py` | Чтение/запись `signature.json` (atomic) |
| Schema | `./backend/app/schemas/signature.py` | Pydantic-схемы запроса/ответа/настроек + валидация домена |
| Module-flag | `./backend/app/core/modules_config.py` (`SignatureModuleSettings`), `./backend/app/api/modules.py` (`SignatureModuleOut/In`, `PUT /admin/modules/signature`) | Мастер-переключатель `enabled` |
| Frontend Page | `./frontend/src/pages/SignaturePage.vue` | Wiring-слой: форма + preview + admin-drawer |
| Frontend Composable | `./frontend/src/pages/composables/useSignatureForm.ts` | Состояние формы, предзаполнение, валидация, маска телефона, генерация, copy/download |
| Frontend Component | `./frontend/src/components/signature/SignaturePreview.vue` | Превью в `iframe srcdoc` |
| Frontend Component | `./frontend/src/components/signature/SignatureActions.vue` | Кнопки create/copy/download + mailto-ТП |
| Frontend Admin | `./frontend/src/components/admin/SignatureModuleSettings.vue` | Drawer настроек (`?manage=module`) |
| Frontend API | `./frontend/src/api/signature.ts` | Типы + клиент (config/generate/settings) |
| Frontend Query | `./frontend/src/queries/signature.ts` | TanStack Query (config/settings + mutation) |
| Router | `./frontend/src/router.ts` | Роут `/signature` + module-guard |
| Store | `./frontend/src/stores/modules.ts` | `signature.enabled` в `isEnabled(...)` |

---

## 3. Конфигурация (stateless)

### 3.1. Master-flag
В `/data/settings/modules.json` — ключ `signature.enabled` (по аналогии с
`meetings` / `directories`). TTL-кэш 60s, инвалидация через
`invalidate_modules_cache()`. Выключен → все эндпоинты раздела возвращают `404`,
роут `/signature` редиректит на главную (`requireModule` в `./frontend/src/router.ts`).

### 3.2. Runtime-конфиг `/data/settings/signature.json`
Модель `SignatureSettings` (`./backend/app/schemas/signature.py`). Запись atomically
(`atomic_write`), редактируется только из Admin UI. При отсутствии файла — дефолты
(текущие значения `./sign`):

- **`cities`**: `[{ id, label_ru, label_eng, suffix_ru, suffix_eng }]` — 4 города
  (Мурманск / Москва / Санкт-Петербург / Сочи).
- **`office_phones`**: список городских номеров (4 по умолчанию).
- **`support_email`**: `it@mage.ru`.
- **`company_url`**: `http://mage.ru/` (ссылка под логотипом).
- **`logo_base_url`**: `http://mage.ru/signature/images/` — база для `img src`.

> **Email-домен `@mage.ru`** — константа `EMAIL_DOMAIN` в коде, НЕ редактируемая
> настройка. **Имена/размеры логотипов** захардкожены в `_LOGO_SPEC`
> (`./backend/app/services/signature.py`).

---

## 4. Матрица генерации (источник истины — этот раздел + снапшот-тесты)

16 PHP-шаблонов оригинала свёрнуты в 2 функции рендера, параметризованные языком,
устройством и наличием мобильного телефона.

| Устройство | Вёрстка | Логотип Ru / Eng | Размер | Файл (суффикс) |
|---|---|---|---|---|
| `PC` | таблица с логотипом | `Mage_Ru.png` / `Mage_Eng.png` | 60×48 | `_Ru` / `_Eng` |
| `Apple` | таблица (как PC) | `Mage_Ru.png` / `Mage_Eng.png` | 60×48 | `_AppleRu` / `_AppleEng` |
| `Web` | таблица с логотипом | `WebRu.png` / `WebEng.png` | 68×125 | `_Ru` / `_Eng` |
| `Phone` | текст (`<span>`), **без логотипа**, заканчивается строкой `www.mage.ru` | — | — | `_AndroidRu` / `_AndroidEng` |

- **Логотип** (`PC/Apple/Web`): `img src` = `logo_base_url` + имя файла (внешняя
  ссылка на `mage.ru`, файлы локально не хостятся).
- **Суффикс должности по городу × языку**: Мурманск → ``; Москва →
  `, МАГЭ Москва` / `, MAGE Moscow`; СПб → `, МАГЭ Санкт-Петербург` /
  `, MAGE St. Petersburg`; Сочи → `, МАГЭ Сочи` / `, MAGE Sochi`.
- **Строка телефона**: `office_phone` + (` / ` + `extension`, если задан).
- **Имя файла**: `f"{name}{surname}{suffix}.htm"`.

---

## 5. REST API

Все эндпоинты под master-flag (выкл → `404`). Префикс `/api/v1/signature`.
Зависимости — из `./backend/app/api/deps.py`.

| Метод | Путь | Описание | Права |
|---|---|---|---|
| **GET** | `/signature/config` | Данные для формы (cities, office_phones, support_email, email_domain) | `CurrentUser` |
| **POST** | `/signature/generate` | Сгенерировать → `{ html, filename }` (preview/копирование) | `CurrentUser` |
| **POST** | `/signature/download` | `text/html; charset=utf-8` + `Content-Disposition: attachment` (RFC 5987 для кириллицы) | `CurrentUser` |
| **GET** | `/signature/admin/settings` | Текущие настройки (`SignatureSettings`) | `AdminDep` |
| **PUT** | `/signature/admin/settings` | Обновить настройки | `AdminDep` |
| **PUT** | `/admin/modules/signature` | Master-переключатель `enabled` | `AdminDep` |

---

## 6. Frontend

### 6.1. Роут и навигация
- Роут `/signature` (lazy, `requiresAuth`), gated module-guard'ом
  (`requireModule` в `./frontend/src/router.ts`, fail-closed).
- **Пункта в основном меню нет** — переход через корпоративный ярлык
  (`ServiceLink`) в «Ярлыки сервисов» (см. `./docs/links-bookmarks.md`). Ярлык
  заводит admin вручную (runtime-данные, не код).

### 6.2. Предзаполнение из профиля (`UserMe`)
Источник — `auth`-store, без новых эндпоинтов. Все поля остаются редактируемыми.

| Поле формы | Источник | Правило |
|---|---|---|
| `name` | `full_name` | первый токен («Имя Фамилия») |
| `surname` | `full_name` | остаток после первого токена |
| `position` | `position` | как есть |
| `email` | `email` | как есть |
| `language` | `lang` | `ru → Ru`, `en → Eng` |
| `mobile_phone` | `phone` | с маской `+7 (XXX) XXX XXXX` |
| `city_id`, `office_phone`, `extension` | — | в профиле нет → выбирает пользователь |

> В профиле нет поля «город» и нет раздельных имя/фамилия (`full_name` — одна
> строка) → город выбирается вручную, ФИО разбивается по первому пробелу.

### 6.3. Маска телефона
`formatRuPhone()` в `./frontend/src/pages/composables/useSignatureForm.ts`
(перенос `./sign/web/js/Mob.js`): оставляет цифры, нормализует ведущую `8 → 7`,
формат `+7 (XXX) XXX XXXX`, максимум 11 цифр.

### 6.4. Копирование / скачивание
- **Копировать HTML** — `navigator.clipboard.write` с `ClipboardItem`
  (`text/html` + `text/plain`); fallback — `writeText`.
- **Скачать .htm** — `Blob` + временная `<a download>` (имя файла с бэкенда).

### 6.5. Admin-настройки
Шестерёнка на `SignaturePage` (admin-only) → drawer `?manage=module`
(`composables/useManageDrawer.ts`) → `SignatureModuleSettings.vue`: города
(`NDynamicInput`), городские телефоны, `support_email`, `company_url`,
`logo_base_url`. В `ModulesTab.vue` — только master-переключатель `enabled`.

### 6.6. i18n
UI-строки — `t('signature.*')` (+ `admin.modules.signature.*`); ключи в
`./frontend/src/i18n/ru.json` (мастер) и `en.json`.

> ⚠️ Символ `@` в i18n-значениях экранируется как `{'@'}` (vue-i18n трактует `@`
> как linked-message). Контент самой подписи (суффиксы городов и т.п.) — данные
> конфига, не i18n-ключи.

---

## 7. Безопасность

- Генерация — любой авторизованный; правка конфига/флага — `admin`.
- **Stateless**: ПДн не сохраняются на диск (исправляет утечку `./sign/web/trash/`).
- HTML-экранирование всех подстановок через `html.escape` (прямой эквивалент
  `htmlspecialchars` оригинала).
- Email валидируется вручную на домен `@mage.ru` (НЕ `EmailStr` — DNS-проверка
  ломается на корпоративных доменах, см. `../AGENTS.md`); длины полей и
  `extension` (`^[0-9]{3}$`) как в оригинале.
- Preview рендерится в изолированном `iframe srcdoc`, не `v-html`.

---

## 8. События аудита

Эмиттер `make_audit_emitter("signature")` (`./backend/app/services/audit.py`).
- **`signature.settings_updated`**: при сохранении настроек admin'ом
  (`PUT /signature/admin/settings`).

Содержимое подписей (ПДн) не логируется.

---

## 9. Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Backend) | `./backend/tests/unit/test_signature.py` | Рендер: комбинации `язык×устройство×моб.`, выбор логотипа, суффиксы городов, телефонная строка, имена файлов, HTML-экранирование, валидация схемы (домен `@mage.ru`/добавочный/длины) |
| Unit (Backend) | `./backend/tests/unit/test_signature_api.py` | Эндпоинты (`dependency_overrides` + httpx, без БД): `404` при выкл. модуле, `GET /config`, `POST /generate`, заголовки `POST /download` (RFC 5987 + `Cache-Control`), admin settings GET/PUT (`admin` 200 / non-admin 403), событие аудита `signature.settings_updated` |
| Unit (Backend) | `./backend/tests/unit/test_signature_settings.py` | Хранилище `signature.json`: дефолты при отсутствии файла, save→read round-trip, `None`/дефолты при битом JSON |
| Unit (Frontend) | `./frontend/tests/unit/signature-phone-mask.spec.ts` | Маска телефона `formatRuPhone` |
| Unit (Frontend) | `./frontend/tests/unit/signature-api.spec.ts` | API-клиент signature |
| Unit (Frontend) | `./frontend/tests/unit/signature-form.spec.ts` | Композабла `useSignatureForm`: предзаполнение из профиля (split ФИО / язык / маска), дефолт города и телефона, `isValid` (ветки + домен), `onExtensionInput`/`onMobileInput`, `generate` (happy / invalid) |

**DoD-команды.** Backend: `ruff check . && mypy app && pytest tests/unit`.
Frontend: `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check`.

---

## 10. Как включить и открыть модуль

1. **Включить модуль**: Admin → «Модули» (`ModulesTab`) → переключатель
   «Генератор подписей» (`PUT /admin/modules/signature`).
2. **Открыть**: прямой URL `/signature` (после включения роут доступен любому
   авторизованному).
3. **Добавить ярлык** (рекомендуется): Admin → «Ярлыки сервисов» → создать
   `ServiceLink` с полным URL портала, напр. `https://<хост-портала>/signature`
   (URL ярлыка валидируется на `http/https` + host, относительный путь не
   подойдёт). После этого модуль доступен с главной плитки сервисов.
4. *(Опционально)* Admin → шестерёнка на `/signature` → задать города, телефоны,
   email техподдержки, `company_url`, `logo_base_url`.
