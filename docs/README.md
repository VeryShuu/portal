# Документация Portal

Оглавление каталога `./docs/`.

## Стратегия и архитектура

- [`adr.md`](./adr.md) — активные ADR (001–038)
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
- [`files-readonly-plan.md`](./files-readonly-plan.md) — read-only режим файлов
- [`trash-plan.md`](./trash-plan.md) — план корзины
- [`integration-keycloak-nextcloud.md`](./integration-keycloak-nextcloud.md) —
  настройка Keycloak realm и Nextcloud service account

## Эксплуатация и тесты

- [`dev-onboarding.md`](./dev-onboarding.md) — quickstart для разработчика
  (локальный запуск, минимальные env, создание тестового пользователя)
- [`deploy.md`](./deploy.md) — production-чеклист, TLS, бэкапы, ротация секретов
- [`testing.md`](./testing.md) — стратегия тестов, команды, CI
- [`../SECURITY.md`](../SECURITY.md) — политика disclosure

## Внутренние материалы

- [`internal/`](./internal/) — рабочие документы команды (ревью, заметки,
  тикеты). Не часть пользовательской документации.
