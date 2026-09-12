# Фича: Устранение находок аудита тестирования (2026-08-21)

## Статус: этапы 1–2 завершены (PR #92–95 смержены в main 2026-08-21, CI зелёный)

Следующая фаза — модули по прод-риску (см. чеклист ниже).

## Цель

Аудит тестового контура (read-only, main@5de82f9) нашёл ложнозелёные проверки: тесты,
которые проходят, даже когда защищаемый код удалён или сломан. Цель — сделать тестовый
контур честным (сначала достоверность, потом проценты), затем закрыть критические
пробелы покрытия по прод-риску.

Согласованный порядок (аудитор + агент, 2026-08-21): PR 1–4 ниже, дальше модули по риску.

## Решения по ходу

- 2026-08-21: mutation testing отложен (дорого для одного разработчика).
- 2026-08-21: Firefox/WebKit — только после проверки реального браузерного парка орг (вопрос к Reydan).
- 2026-08-21: «любой skip = ошибка» НЕ вводим глобально: у integration-контуров есть
  легитимные skips → явный skip-бюджет; nightly-обязательный набор — ноль пропусков.
- 2026-08-21: Vue warnings — baseline + запрет роста; missing-props и некорректные watch
  чиним сразу, не заносим в вечный allowlist.
- 2026-08-21: diff-coverage ≥80% сохраняем; проблема пустышек не в гейте, а в отсутствии
  требования «тест вызывает production-код и проверяет наблюдаемый результат».

## Чеклист (DoD)

### PR 1 — ложнозелёные security и idempotency-тесты ✅ (PR #92)
- [x] security: канонические маршруты (реальный `/api/v1/users/admin/local`), точные
      статусы без разрешённого 404
- [x] editor-тест: GET /news → ровно 200
- [x] конкурентный idempotency-тест вызывает настоящий IdempotencyMiddleware
      ( fakeredis + fake ASGI app), контракт: ровно один origin-вызов
- [x] mutation-проверка: временно сломать защиту → тест падает → восстановить
      (3 мутации: lock nx=False / middleware bypass / require_role off — все ловятся)
- [x] ci_lint.sh + pytest tests/unit (4716 passed) + tests/security (79 passed)
- [x] регенерация docs/tests.generated.md (переименован 1 тест)

### PR 2 — настоящий integration-контур local auth ✅
- [x] login успех/ошибка (реальные HTTP + PostgreSQL + Redis, DSN-стек)
- [x] запрет local login для keycloak-аккаунта; LOCAL_AUTH_ENABLED=false → 403
- [x] bootstrap admin: создание + идемпотентность (не откатывает сменённый пароль)
- [x] сессия: /auth/me, logout → сессия мертва и на сервере (старый session_id → 401)
- [x] проверка внешнего поведения, не вручную собранных словарей
- [x] mutation: отключён отказ login → 3 теста падают; logout не удаляет сессию → падает
      (улучшили тест: изначально проверял только cookie клиента, а не Redis)
- [x] cleanup: тесты коммитят пользователей → явный hard-delete по email в teardown
- [x] test-integration.sh: добавлен INTEGRATION_REDIS=true (redis-тесты молча скипались локально)
- [x] run-testcontainers-tests.sh: test_local_auth убран из дефолта (теперь DSN-based)

### PR 3 — полная изоляция E2E в CI ✅
- [x] динамические порты backend (8000) И Vite (5173) — оба фиксированных убраны
- [x] fail-closed readiness: не поднялся за таймаут → шаг падает с логом
- [x] проверка принадлежности backend текущему прогону (PID жив + local-login 200
      с CI-кредами = БД нашего run'а)
- [x] `--strictPort` для vite dev: занятый порт → громкая ошибка (exit 1),
      а не молчаливый 5173→5174 и ожидание чужого сервера
- [x] валидация: YAML-парс, vite-смоук (порт передаётся/занятый падает), tsc конфига
- [ ] пробный параллельный запуск двух E2E-контуров на runner — по факту
      параллельных CI-run'ов после мёрджа (PR 92/93/94 сами создадут параллель)

### PR 4 — честный тестовый CI ✅
- [x] envsubst + jq ставятся в nightly-flakes.yml (apt, с чисткой битого git-lfs repo)
- [x] nightly: любой skip проваливает прогон (guard в tests/conftest.py, проверен
      на scratch-окружении: NIGHTLY=true + skip → exit 1)
- [x] `_skip_if_missing_tools` при NIGHTLY=true → pytest.fail (ошибка окружения)
- [x] tsconfig.e2e.json (строгий) + package.json `typecheck:e2e` + шаг в CI
- [x] ESLint больше не игнорирует tests/e2e (код оказался чист; 10 warnings —
      преждесуществующие a11y в src/, этап 6)
- [x] skip-бюджет задокументирован: docs/testing.md §«Skip-бюджет»
- [x] ПОЙМАЛИ РЕАЛЬНЫЙ DRIFT: ожившие nginx-тесты увидели listen 443 → 8443
      (0431cdc run-without-root) — ассерты обновлены на непривилегированные
      порты 8080/8443; http-only-тест больше не проходит «подстрокой»
- [x] NIGHTLY unit-прогон локально: 4722 passed / 0 skipped / exit 0;
      daily-режим не изменился (6 nightly-скипов допустимы)
- [ ] retries/flaky-отчёт в CI — отложено (junit-формат Playwright не даёт
      надёжного флага flaky; вернуться на этапе 6)

### Этап 6a — Vue-warnings baseline ✅ (2026-08-22, PR #102)
- [x] 109 → 0 предупреждений [Vue warn]: все 6 классов починены, не занесены
      в allowlist (моки с плейн-объектами вместо ref() → настоящие ref;
      композаблы с lifecycle вне setup → withSetup-обёртка; обязательные props
      в mount-опциях; size в стабах NInput; global.components для n-tooltip/
      n-switch; isError в моке useQuery) — 14 spec-файлов
- [x] ratchet-гейт: `frontend/scripts/check-vue-warnings.sh` (baseline 0 в
      `vue-warnings-baseline.txt`), CI-джоба vitest гоняет обёртку с
      --coverage, `npm run check:vue-warnings` локально; счётчик проверен в
      обе стороны; shellcheck чист
- [x] итог: 2474 unit-теста, 0 warnings; критерий аудита «ноль warnings»
      достигнут без allowlist

### Этап 6b — остальное (открыто)
- [ ] 2-3 пользовательских journey-E2E (helpdesk-заявка, файлы; согласовано
      вместо семи)
- [ ] e2e на production-preview вместо dev-сервера
- [ ] authenticated Axe + keyboard/focus сценарии
- [ ] Firefox/WebKit nightly — только после ответа Reydan о браузерном парке
- [ ] retries/flaky-отчёт (см. выше)

### Дальше — модули по прод-риску (отдельные PR)
1. **email outbox** ✅ (2026-08-21, ветка `test/email-outbox-lifecycle-db`):
   `tests/integration/test_email_outbox_lifecycle_db.py` — 21 тест на реальных PG+Redis:
   транзакционность enqueue (rollback), claim-изоляция SKIP LOCKED (конкурентные
   воркеры не пересекаются), FIFO/limit, backoff transient (окно 30с+джиттер),
   DLQ по permanent/exhausted, watchdog (только старые SENDING), админ-переходы
   (retry reset/keep, cancel-стейт-машина), cleanup (только старые SENT), полный
   цикл диспетчера (happy+watchdog, 4xx transient, 5xx DLQ, SMTP не настроен →
   transient ConfigurationError). Мутации: убранный lock / игнор исчерпания /
   watchdog без age-фильтра — все ловятся.
1a. **messenger outbox** ✅ (2026-08-21, ветка `test/messenger-outbox-lifecycle-db`,
   стековая на email-ветке): `tests/integration/test_messenger_outbox_lifecycle_db.py`
   — 20 тестов, зеркало email-файла (тот же паттерн): транзакционность, claim-изоляция,
   backoff/DLQ, watchdog, админ-переходы, cleanup, диспетчер (happy+watchdog,
   ненастроенный MAX → transient). Бонус-находка: unknown-provider тестируется
   через CHECK-констейнт `ck_messenger_outbox_provider` (миграции 081→097) —
   unknown-провайдер физически не может попасть в таблицу; ветка в воркере —
   defense-in-depth.
2. **meetings — конкурентное бронирование** ✅ (2026-08-21, ветка
   `test/meetings-concurrent-booking`): `test_meetings_concurrent_booking_db.py`
   — 3 теста: гонка 5 брони на один слот (EXCLUDE GIST + SAVEPOINT → ровно один
   победитель, в БД слот занят один раз), один слот в разных комнатах (обе
   проходят), гонка create-vs-move (ровно один занимает слот). Мутация:
   проглоченный IntegrityError в _flush_or_conflict — ловится.
3. **files shares** ✅ (2026-08-21, ветка `test/files-shares-acl-db`, стековая):
   `test_files_shares_acl_db.py` — 11 тестов: активная/истёкшая/отозванная/чужая
   шера, группы Keycloak, __all_users__, лучшая из шер, доступ без folder-ACL,
   отзыв + инвалидация кэша (не через TTL), CHECK: manager на файл не выдаётся.
   Мутация: убран фильтр revoked_at — ловится.
4. **helpdesk — конкурентный take** ✅ (2026-08-21, ветка
   `test/helpdesk-concurrent-take-db`, стековая): `test_helpdesk_concurrent_take_db.py`
   — головной инвариант модуля: два агента одновременно берут заявку (FOR UPDATE)
   → ровно один take, проигравший conflict, new→open. Мутация: отключён
   with_for_update — ловится. Статус-машина уже покрыта unit-тестами
   (test_helpdesk_lifecycle.py), assignee-lock — integration (assignee_lock).
Цель — бизнес-инварианты, не процент покрытия.

## Грабли / контекст

- Readiness-цикл uvicorn в ci.yml (~995) без exit 1 — шаг «зелёный», даже если backend
  не поднялся; Playwright может попасть на чужой процесс порта 8000.
- Postgres/Redis в CI уже на динамических портах (паттерн `-p 127.0.0.1::5432` готов),
  backend/Vite — последние фиксированные.
- Прошлые e2e-флаки (память сессий): порт 5173 и files-bulk 429 — подтверждение, что
  оба порта надо динамизировать.
- `docs/tests.generated.md` регенерируется `bash scripts/list_tests.sh` — при изменении
  состава тестов обязательно, иначе drift-check заблокирует мёрдж.
- Forgejo token в ~/.git-credentials (не env), PR через REST API.
- Пустышечные тесты — следствие diff-coverage гейта: при ревью первый вопрос
  «вызывает ли тест production-код вообще».
