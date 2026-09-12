<!--
  Шаблон описания PR. Заполните секции под ▸ перед отправкой.
  Тело PR + статус checks увидят ревьюеры; текст между <!-- → не рендерится.
  См. AGENTS.md §«Работа между сессиями» — main защищена, 17 обязательных чеков.
-->

## Что и зачем

▸ <!-- 1–3 предложения: что меняется и почему. Для рефакторинга — какая проблема
     (code smell / архитектура / перф). Для бага — симптомы + корень. Ссылка на
     audit.md / ADR / docs при наличии. -->

## Тип изменений

Отметь одно (или несколько):

- [ ] 🐛 fix (bugfix)
- [ ] ✨ feat (новый функционал)
- [ ] ♻️ refactor (без изменения поведения)
- [ ] 🚀 perf
- [ ] ♿ a11y
- [ ] 📚 docs / chore / ci

**Breaking change?** [ ] да / [x] нет
<!-- Если да — опиши миграцию потребителей (API contract / DB schema / openapi.json). -->

---

## Чек-лист ревьюера (автор проходит сам перед requesting review)

### Качество
- [ ] Код следует соглашениям (AGENTS.md §«Coding Conventions»)
- [ ] Тесты добавлены/обновлены (unit обязательно; integration если затронут API/БД)
- [ ] Существующие тесты зелёные
- [ ] No `console.log` / debug-кода / закомментированных блоков

### Backend (если затронут `backend/`)
- [ ] `./scripts/ci_lint.sh` зелёный (ruff + mypy **в CI-окружении**, не локально)
- [ ] `pytest tests/unit` зелёный
- [ ] Бизнес-логика — в `app/services/`, роутеры — тонкий wiring
- [ ] Логи не содержат токенов/паролей/PII (`redact_secrets_processor` / `mask_pii_processor`)
- [ ] SQL — bind-параметры (нет интерполяции user-controlled данных)
- [ ] admin-mutating endpoints вызывают `push_audit_event(...)`

### Frontend (если затронут `frontend/`)
- [ ] `npm run lint:check && typecheck && test:unit && i18n:check` зелёные
- [ ] Все user-facing строки — через `t('key')`, ключи в `ru.json` + `en.json`
- [ ] 0 `: any` / `@ts-ignore`

### Контракты и артефакты (если что-то менялось)
- [ ] API-контракт не менялся без подтверждения (см. `docs/api-contracts.md`)
- [ ] `openapi.json` / `types.gen.d.ts` / `tests.generated.md` регенерированы
      → единый скрипт: `./scripts/check-drift.sh --fix`

---

### ⚠️ Миграции БД — zero-downtime чекпоинт

Если PR содержит Alembic-миграцию (`backend/migrations/versions/`), **обязательно**:

- [ ] **Добавление колонки NOT NULL** — через три шага, НЕ одним `ADD COLUMN ... NOT NULL`:
      1. `ADD COLUMN ... NULL` (или `NOT NULL DEFAULT` — только если DEFAULT backfill'ит
         существующие строки атомарно, как в миграции **077**)
      2. backfill данных (`UPDATE ... WHERE col IS NULL`)
      3. `ALTER COLUMN ... SET NOT NULL` отдельной миграцией (после deploy)
      Канонический пример — миграция **058**
      (`UPDATE ... SET col = '' WHERE col IS NULL` → `alter_column(nullable=False)`).
- [ ] **Индексы на большой таблице** — `CREATE INDEX CONCURRENTLY` (не блокирует writes).
      В Alembic — `op.execute("CREATE INDEX CONCURRENTLY ...")` + `op.execute("DROP INDEX CONCURRENTLY ...")`.
- [ ] **Rename колонки/таблиц** — expand→ писать в оба → читать новое → удалить старое (≥ 2 миграции).
- [ ] **Миграция идемпотентна** там, где это возможно (`IF [NOT] EXISTS`), и имеет корректный `downgrade()`.
- [ ] Если миграция НЕ zero-downtime (одноразовый админ-скрипт / маленькая таблица) —
      явно отметить причину в описании миграции.

> Полное правило — `AGENTS.md` §«Миграции (zero-downtime)». Отклонение от конвенции —
> блокирует мёрдж до обсуждения в комментарии.

---

## Ссылки

- audit.md: <!-- ID карточки, например [M9], если закрывает задачу аудита -->
- ADR: <!-- ADR-0XX, если затронуто архитектурное решение -->
- docs: <!-- docs/<module>.md, если затронут модульный док -->

<!-- Закрывает issue/задачу — раскомментировать:
Closes #NNN
-->
