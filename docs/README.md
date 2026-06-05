# Документация Portal

Оглавление каталога `./docs/`. Каждый `*.md` начинается с agent-заголовка
(**Когда читать / Ключевой код / ADR**) — он даёт «прицел» без чтения всего файла.

## Роутер: тип задачи → что читать

| Задача | Сначала читай |
|---|---|
| Новая таблица / поле / миграция | `db-schema.md` |
| Новый / изменённый REST endpoint | `api-contracts.md` |
| Изменение прав доступа («кто что видит») | `roles-matrix.md` |
| Спорное / новое архитектурное решение | `adr.md` |
| Модуль Файлы / Nextcloud | `files.md` (+ `sharing.md`) |
| Модуль База знаний | `knowledge-base.md` |
| Модуль Фотогалерея | `photos.md` |
| Модуль Переговорные | `meetings.md` |
| Новости (лента, категории) | `news.md` |
| Опросы в новостях | `polls.md` |
| Ссылки и закладки | `links-bookmarks.md` |
| Глобальный поиск (Cmd+K) | `search.md` |
| Уведомления (in-app, SSE) | `notifications.md` |
| Аналитика (admin-дашборд) | `analytics.md` |
| Атрибуты пользователя (карточка /staff, источник ФИО) | `user-attributes.md` |
| Health-пробы / метрики / логи / Sentry | `monitoring.md` |
| Главная страница и виджеты | `home-widgets.md` |
| Брендинг / оформление | `branding.md` |
| Вёрстка: брейкпоинты, ширины, адаптив | `ui-layout.md` |
| Журнал аудита | `audit.md` |
| Справочник сотрудников | `staff-directory-spec.md` |
| Справочники объектов (Флот/Склады/…) | `directories.md` |
| Обратная связь | `feedback.md` |
| Экскурс по порталу | `onboarding.md` |
| Отправка email | `email.md` |
| Аутентификация (Keycloak/SSO) | `adr.md` (017/035/036) + `integration-keycloak-nextcloud.md` |
| Runtime-настройка Keycloak + синк пользователей (Admin UI) | `integration-keycloak-nextcloud.md` (§2.5) |
| Локальный запуск / окружение | `dev-onboarding.md` |
| Production-деплой / TLS / секреты | `deploy.md` |
| Тесты, команды, покрытие | `testing.md` |
| Незавершённая многосессионная задача | `wip/<feature>.md` (план) |

> `*.generated.md` — **авто-генерация, руками не править** (баннер указан в самих файлах);
> перегенерировать соответствующим скриптом.

## Стратегия и архитектура

- [`adr.md`](./adr.md) — активные ADR (001–041)
- [`adr-archive.md`](./adr-archive.md) — архив устаревших / отменённых ADR
- [`roles-matrix.md`](./roles-matrix.md) — матрица ролей и прав по модулям

## API и схема данных

- [`api-contracts.md`](./api-contracts.md) — curated-описание REST-контрактов
- [`api-contracts.generated.md`](./api-contracts.generated.md) — авто-генерация
  из OpenAPI (`backend/scripts/generate_api_contracts_doc.py`)
- [`db-schema.md`](./db-schema.md) — curated-описание схемы БД
- [`db-schema.generated.md`](./db-schema.generated.md) — авто-генерация
  из SQLAlchemy-моделей (`backend/scripts/generate_db_schema_doc.py`)
- [`../openapi.json`](../openapi.json) — экспорт FastAPI OpenAPI 3.1

> Все `*.generated.md` и `openapi.json` пересобираются скриптами
> `backend/scripts/export_openapi.py`, `generate_api_contracts_doc.py`,
> `generate_db_schema_doc.py`. Запускать перед PR, если менялись
> модели/роуты/схемы.

## Модули

- [`staff-directory-spec.md`](./staff-directory-spec.md) — справочник сотрудников
- [`user-attributes.md`](./user-attributes.md) — маппинг атрибутов пользователя
  (произвольные `users.attributes` из Keycloak → поля карточки /staff, discover
  незамапленных ключей, назначение атрибута источником `users.full_name`)
- [`directories.md`](./directories.md) — справочники объектов (вкладки в /staff)
  (универсальный движок Флот/Склады/…: 3 таблицы, конструктор полей/каналов,
  аватары, экспорт CSV/XLSX/PDF, двухуровневый гейтинг, поиск Cmd+K)
- [`feedback.md`](./feedback.md) — модуль обратной связи
- [`integration-keycloak-nextcloud.md`](./integration-keycloak-nextcloud.md) —
  настройка Keycloak realm и Nextcloud service account
- [`email.md`](./email.md) — общая для портала email-инфраструктура
  (outbox-таблица, классификация ошибок, диспетчер, админ-UI)
- [`onboarding.md`](./onboarding.md) — модуль «Экскурс по порталу»
  (системные настройки, admin API, дельта-режим `is_new`, операционные процедуры)
- [`polls.md`](./polls.md) — модуль опросов для новостей
  (схема БД, жизненный цикл, Backend API, управление правами, голосование, фронтенд-компоненты)
- [`knowledge-base.md`](./knowledge-base.md) — модуль «База знаний»
  (структура кода, модель данных, ACL, REST API, хранилище файлов, безопасность, аудит, тесты)
- [`meetings.md`](./meetings.md) — модуль «Переговорные»
  (бронирование комнат, серии, iCal-уведомления, конфликт-чек, фронтенд)
- [`photos.md`](./photos.md) — модуль «Фотогалерея»
  (иерархия папок, per-folder ACL, миниатюры WebP/AVIF, ARQ-воркер, SSE)
- [`files.md`](./files.md) — модуль «Файлы»
  (витрина над Nextcloud, service account, теневое дерево папок, per-folder ACL,
  загрузка/превью, bulk-операции, согласованность БД↔NC, sync)
- [`sharing.md`](./sharing.md) — пофайловый шеринг (ADR-032)
  (таблица `file_shares`, уровни viewer/editor, drift-реконсиляция, admin-реестр)
- [`news.md`](./news.md) — модуль «Новости»
  (лента, категории, обложки, галерея, вложения, inline-медиа, версии, экспорт, корзина)
- [`links-bookmarks.md`](./links-bookmarks.md) — сервисные ярлыки + личные закладки
  (SSO-редирект, reorder, favicon-кэш)
- [`search.md`](./search.md) — глобальный поиск
  (FTS hunspell + pg_trgm, Cmd+K палитра, поиск по KB/новостям/ссылкам/пользователям)
- [`notifications.md`](./notifications.md) — in-app уведомления
  (SSE-стрим, продюсеры news/kb/meetings, отметка прочтения)
- [`analytics.md`](./analytics.md) — admin-аналитика (read-only)
  (дашборд, топ статей/новостей/файлов, активность отделов)
- [`home-widgets.md`](./home-widgets.md) — главная страница и виджеты
  (HeroBlock, виджеты meetings/photos, «Время в городах» + Open-Meteo, ADR-038)
- [`branding.md`](./branding.md) — оформление портала
  (логотип, favicon, фон логина, email-настройки; `/data/branding/`, ADR-037)
- [`ui-layout.md`](./ui-layout.md) — вёрстка и адаптив
  (шкала брейкпоинтов, три класса ширины контента, `.u-page-wrap`, intrinsic-сетки,
  `useBreakpoints`)
- [`audit.md`](./audit.md) — журнал аудита
  (audit_log с партициями по месяцам, Redis-очередь + ARQ-воркер, CSV-экспорт)

## Эксплуатация и тесты

- [`dev-onboarding.md`](./dev-onboarding.md) — quickstart для разработчика
  (локальный запуск, минимальные env, создание тестового пользователя)
- [`monitoring.md`](./monitoring.md) — мониторинг и наблюдаемость
  (health/ready-пробы, `/metrics` с токен-защитой и кросс-процессным снапшотом
  кастомных гейджей, heartbeat воркера, уровень логов, Sentry, вкладка «Мониторинг»)
- [`deploy.md`](./deploy.md) — production-чеклист, TLS, бэкапы, ротация секретов
- [`testing.md`](./testing.md) — стратегия тестов, команды, CI
- [`tests.generated.md`](./tests.generated.md) — авто-генерация списка тестов
  (`scripts/list_tests.sh`)
- [`../SECURITY.md`](../SECURITY.md) — политика disclosure

## Работа между сессиями

- [`wip/`](./wip/) — планы активных многосессионных фич (handoff). Один файл на фичу,
  удаляется после завершения. Шаблон — [`wip/_TEMPLATE.md`](./wip/_TEMPLATE.md).
  Правила — раздел «Работа между сессиями» в [`../AGENTS.md`](../AGENTS.md).
