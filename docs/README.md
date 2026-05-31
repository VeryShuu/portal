# Документация Portal

Оглавление каталога `./docs/`.

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

## Эксплуатация и тесты

- [`dev-onboarding.md`](./dev-onboarding.md) — quickstart для разработчика
  (локальный запуск, минимальные env, создание тестового пользователя)
- [`deploy.md`](./deploy.md) — production-чеклист, TLS, бэкапы, ротация секретов
- [`testing.md`](./testing.md) — стратегия тестов, команды, CI
- [`tests.generated.md`](./tests.generated.md) — авто-генерация списка тестов
  (`scripts/list_tests.sh`)
- [`../SECURITY.md`](../SECURITY.md) — политика disclosure
