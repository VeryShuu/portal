# Тестирование

> Последнее обновление: апрель 2026 (Phase 0)

---

## Стратегия

Проект использует трёхуровневую пирамиду тестирования:

```
         ┌─────────────┐
         │  E2E (Playwright) │  ← Phase 1+, покрытие ≥ 90% ключевых путей
         └─────────────┘
       ┌───────────────────┐
       │  Integration Tests  │  ← Testcontainers (PG, Redis), httpx mocks
       └───────────────────┘
    ┌─────────────────────────┐
    │      Unit Tests          │  ← pytest, без внешних зависимостей
    └─────────────────────────┘
```

**Правило:** unit-тесты пишутся **одновременно** с кодом модуля, не после. Каждый модуль обязан иметь тесты до того как считается готовым.

---

## Структура

```
backend/
└── tests/
    ├── conftest.py                      ← общие фикстуры, env vars для тестов
    ├── unit/                            ← быстрые, без Docker (~2–5 сек)
    │   ├── test_config.py               ← Phase 0: Pydantic Settings
    │   ├── test_health.py               ← Phase 0: /health и /ready endpoints
    │   └── test_audit_partitions.py     ← Phase 0: скрипт партиций audit_log
    └── integration/                     ← медленные, требуют Docker (~15–60 сек)
        └── test_migrations.py           ← Phase 0: Alembic migrate up/down

frontend/
└── tests/
    ├── unit/                            ← Vitest (~1–3 сек)
    └── e2e/                             ← Playwright (~60–120 сек)
```

---

## Запуск

### Backend — все тесты

```bash
cd backend
pip install -e ".[dev]"
pytest                                   # все тесты
pytest -v                                # с подробным выводом
pytest --tb=short                        # короткий traceback
```

### Backend — только unit (без Docker)

```bash
pytest tests/unit -v
```

### Backend — только integration (нужен Docker)

```bash
pytest tests/integration -v
```

### Backend — с покрытием

```bash
pytest --cov=app --cov-report=term-missing --cov-report=html
# HTML-отчёт: htmlcov/index.html
```

### Frontend — unit

```bash
cd frontend
npm run test:unit
npm run test:unit:watch                  # watch-режим при разработке
```

### Frontend — E2E (Phase 1+)

```bash
cd frontend
npm run test:e2e                         # нужен запущенный стек (docker compose up)
```

### Проверка i18n-ключей

```bash
cd frontend
npm run i18n:check                       # падает если ru.json ≠ en.json по ключам
```

---

## Переменные окружения для тестов

В `backend/tests/conftest.py` прописаны дефолтные значения через `os.environ.setdefault` — их не нужно указывать вручную при локальном запуске unit-тестов.

Для integration-тестов переменные подставляются автоматически через Testcontainers (строка подключения берётся из запущенного контейнера).

В CI (GitHub Actions) переменные прописаны в `env:` блоке workflow.

---

## Покрытие по фазам

### Phase 0 — Инфраструктура ✅

| Файл теста | Тип | Кейсов | Что покрывается |
|-----------|-----|--------|-----------------|
| `unit/test_config.py` | unit | 7 | — |
| `unit/test_health.py` | unit | 6 | — |
| `unit/test_audit_partitions.py` | unit | 9 | — |
| `integration/test_migrations.py` | integration | 7 | — |
| **Итого Phase 0** | | **29** | |

#### `unit/test_config.py` — Pydantic Settings

| Кейс | Описание |
|------|---------|
| `test_valid_config` | Корректные env vars → Settings создаётся без ошибок |
| `test_production_flag` | `ENVIRONMENT=production` → `is_production=True` |
| `test_secret_key_too_short_raises` | `SECRET_KEY` < 32 символов → `ValidationError` |
| `test_invalid_database_url_driver` | URL без `+asyncpg` → `ValidationError` |
| `test_max_upload_size_bytes` | `MAX_UPLOAD_SIZE_MB=50` → `max_upload_size_bytes == 52428800` |
| `test_max_upload_size_zero_raises` | `MAX_UPLOAD_SIZE_MB=0` → `ValidationError` |
| `test_defaults` | realm, client_id, nc_user_id_field, smtp_port, arq_max_jobs — совпадают со спецификацией |

#### `unit/test_health.py` — Health endpoints

| Кейс | Описание |
|------|---------|
| `test_health_always_200` | `GET /health` → 200 `{"status": "ok"}` всегда |
| `test_health_no_auth_required` | Endpoint не требует авторизации |
| `test_ready_ok_when_db_and_redis_healthy` | DB и Redis доступны → 200, оба checks=ok |
| `test_ready_503_when_db_fails` | DB бросает Exception → 503, postgres=error, redis=ok |
| `test_ready_503_when_redis_fails` | Redis бросает Exception → 503, postgres=ok, redis=error |
| `test_ready_503_when_both_fail` | Оба упали → 503, оба checks=error |
| `test_ready_response_has_checks_dict` | Ответ содержит поле `checks` с ключами `postgres` и `redis` |

> DB и Redis — мокируются через `unittest.mock.patch` и `AsyncMock`, Docker не нужен.

#### `unit/test_audit_partitions.py` — Скрипт партиций

| Кейс | Описание |
|------|---------|
| `test_partition_name_format_single_digit_month` | `2026, 4` → `audit_log_2026_04` (leading zero) |
| `test_partition_name_format_double_digit_month` | `2026, 11` → `audit_log_2026_11` |
| `test_partition_name_january` | `2027, 1` → `audit_log_2027_01` |
| `test_partition_name_december` | `2026, 12` → `audit_log_2026_12` |
| `test_creates_partitions_for_months_ahead` | `months_ahead=2` → 3 партиции (текущий + 2) |
| `test_skips_existing_partitions` | `fetchval=True` для первой → не вызывает `execute` для неё |
| `test_creates_correct_date_ranges` | Проверяет что `PARTITION FOR VALUES FROM/TO` получает правильные даты |
| `test_drops_partitions_older_than_retention` | `retention=12` мес, текущий `2026-04` → дропает `2025-01` и `2025-03` |
| `test_skips_non_audit_tables` | Таблицы `users`, `news_invalid_name` не дропаются |
| `test_nothing_dropped_if_all_within_retention` | Партиции `2026-03`, `2026-04` при `retention=12` → `dropped == []` |

> Все тесты мокируют `asyncpg.Connection` через `AsyncMock`, БД не нужна.

#### `integration/test_migrations.py` — Alembic migrations

Требует Docker. Testcontainers поднимает `postgres:16`, выполняет полный цикл.

| Кейс | Описание |
|------|---------|
| `test_upgrade_head_succeeds` | `alembic upgrade head` не падает |
| `test_users_table_exists` | Таблица `users` создана в схеме `public` |
| `test_users_table_has_required_columns` | Все 17 колонок из `db-schema.md` присутствуют |
| `test_idempotency_keys_table_exists` | Таблица `idempotency_keys` создана |
| `test_users_indexes_exist` | Индексы `idx_users_keycloak`, `idx_users_email`, `idx_users_dept` созданы |
| `test_downgrade_base_succeeds` | `alembic downgrade base` не падает |
| `test_users_table_removed_after_downgrade` | После downgrade таблица `users` отсутствует |
| `test_upgrade_again_after_downgrade` | Повторный `upgrade head` после downgrade работает (идемпотентность) |

---

### Phase 1 — Auth + Users + News (запланировано)

Тесты будут добавлены при реализации Phase 1. Планируемое покрытие:

| Тип | Что покрывается |
|-----|----------------|
| Unit | JWT parsing, claims mapping → User model, targeting logic для новостей, token refresh |
| Integration | Keycloak OIDC flow (mock-сервер), DB upsert при логине, ARQ publish task |
| E2E | Логин → главная с новостями → выход (SLO) |
| E2E | Создание новости с таргетом → отложенная публикация срабатывает |

---

## Инструменты

### Backend

| Инструмент | Версия | Назначение |
|-----------|--------|-----------|
| **pytest** | ≥8.2 | Test runner |
| **pytest-asyncio** | ≥0.23 | `async def` тест-функции |
| **pytest-cov** | ≥5.0 | Покрытие кода |
| **testcontainers[postgres,redis]** | ≥4.7 | Docker-контейнеры в integration-тестах |
| **httpx** | ≥0.27 | HTTP-клиент для тестирования FastAPI (через `AsyncClient`) |

### Frontend

| Инструмент | Версия | Назначение |
|-----------|--------|-----------|
| **vitest** | ≥1.6 | Unit test runner (Vite-native, быстрее Jest) |
| **@vue/test-utils** | ≥2.4 | Утилиты для тестирования Vue компонентов |
| **jsdom** | ≥24.0 | DOM-среда для vitest |
| **@playwright/test** | ≥1.44 | E2E тесты в реальном браузере (Chromium) |

---

## Критерии приёмки (из ТЗ)

- ✅ **Unit-тесты**: каждый модуль пишется с тестами одновременно
- ⏳ **Integration-тесты**: Keycloak OIDC, Nextcloud WebDAV/OCS, ARQ задачи — Phase 1+
- ⏳ **E2E ≥ 90%**: полные пользовательские сценарии — Phase 1+
- ⏳ **Security-тесты**: OWASP ZAP — Phase 11 (финальное тестирование)
- ⏳ **Load-тесты**: k6, 300 сессий, p95 < 2 сек — Phase 11

---

## Известные ограничения

1. **`test_audit_partitions.py`**: `datetime.now()` мокируется через `patch`, что требует `datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)` для сохранения конструктора. Если тест падает на `TypeError` — проверить мок.

2. **`test_migrations.py`**: Testcontainers использует `scope="module"` — все тесты в классе `TestMigrations` используют один контейнер. Порядок выполнения имеет значение (upgrade → verify → downgrade → upgrade again).

3. **`test_health.py`**: Использует синхронный `TestClient` для async endpoint. FastAPI TestClient корректно обрабатывает это через `anyio`, но при сложных async моках может потребоваться переход на `httpx.AsyncClient`.

4. **Integration-тесты в CI**: используют сервисы `postgres` и `redis` из `.github/workflows/ci.yml`, а не Testcontainers — это быстрее и надёжнее в GitHub Actions.
