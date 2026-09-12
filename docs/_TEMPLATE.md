# Модуль «<Название>»

> **Когда читать:** <1 строка: при каких задачах открывать этот док>.
> **Ключевой код:** `app/api/<module>/`, `app/services/<module>.py`, `app/models/<module>.py`, `frontend/src/pages/<Module>*.vue`.
> **ADR:** <номера через запятую или «—»>. **См. также:** `<related>.md`.

> <1 абзац: что это за модуль и зачем он нужен — суть в 2–4 предложениях.>

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/<module>/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/<Module>*.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/<module>.py`) — если есть |
| Хранилище | <Nextcloud / локальная ФС `/data/...` / только БД> |
| Префикс API | `/api/v1/<module>` |
| ACL-кэш | Redis, ключи `<...>` (TTL `<...>`) — если есть |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/<module>/` | <…> |
| Service | `./backend/app/services/<module>.py` | <бизнес-логика> |
| Model | `./backend/app/models/<module>.py` | <SQLAlchemy-модели> |
| Schema | `./backend/app/schemas/<module>.py` | <Pydantic-схемы> |
| Frontend | `./frontend/src/pages/<Module>*.vue` | <страницы/компоненты> |

---

## 3. Модель данных

<Таблицы, ключевые поля, FK, soft-delete, индексы. Ссылка на `db-schema.md`.>

---

## 4. Модель прав (ACL)

<Кто что видит/редактирует. Ссылка на `roles-matrix.md`. Уровни доступа, проверки `require_*`.>

---

## 5. REST API

<Список endpoint'ов с методами, правами, идемпотентностью. Ссылка на `api-contracts.md`.>

---

## 6..N. <Разделы, специфичные для модуля>

<Загрузка, sync, воркер, realtime/SSE, экспорт, конфигурация модуля и т.п.>

---

## Безопасность

<Санитизация, rate-limit, валидация, что НЕ логируется.>

---

## События аудита

<Какие `push_audit_event(...)` пишутся, `resource_type`, метаданные.>

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_<module>*.py` | <…> |
| Integration | `./backend/tests/integration/test_<module>*.py` | <…> |
| Frontend | `./frontend/tests/unit/<module>*.spec.ts` | <…> |
| E2E | `./frontend/tests/e2e/<module>*.spec.ts` | <…> |

---

## Связанные документы

- `db-schema.md`, `api-contracts.md`, `roles-matrix.md`, `adr.md`
- `<другие модульные доки>`

<!--
КАНОН ФОРМАТА (Фаза 0 ревью документации):
1. Agent-заголовок ОБЯЗАТЕЛЕН: blockquote с «Когда читать / Ключевой код / ADR (+ См. также)».
2. Затем 1 абзац-описание сути модуля (blockquote).
3. Секции в фиксированном порядке: Обзор → Структура кода → Модель данных →
   Модель прав → REST API → <специфика модуля> → Безопасность → События аудита →
   Тесты → Связанные документы.
4. Нумерация ## разделов сквозная (1..N) до «специфики»; служебные хвостовые
   секции (Безопасность/Аудит/Тесты/Связанные) можно нумеровать или нет, но
   порядок сохранять.
5. Все ссылки на код — относительные с префиксом `./` (`./backend/app/...`),
   при необходимости с `:line`.
6. Язык — русский; термины стека (FastAPI, SQLAlchemy, ARQ, ACL) латиницей.
7. Не дублировать содержимое `*.generated.md` — ссылаться на curated-доки.
-->
