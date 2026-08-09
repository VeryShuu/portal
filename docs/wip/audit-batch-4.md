# Фича: Audit Batch 4 — L1 + M6 + M9

> План работ по `audit.md` Вариант A («надёжный рефакторинг»).
> Предыдущие пакеты: batch-3 (M8+M3+M2+M12+M14) — закрыт. Здесь остались M6 и M9 из Этапа 2, + L1.
>
> **Контекст из batch-3 (важно):** M9 была отложена именно как «2-3 PR»: двойное чтение JSON
> двумя модулями с разными типами (`KeycloakSettings` admin-model vs `_KCSettings` runtime-cache),
> SSRF-параметризация затронет bookmarks/email_images. Этот пакет берёт M9 scoped — без попытки
> объединить два settings-модуля в один.

## Цель
Закрыть 3 задачи аудита: L1 (zero-downtime конвенция в review-чеклист), M6 (декомпозиция
`_ingest_message`), M9 (refactor `keycloak_admin.py` God Module → тонкий роутер + сервисы).

## Корректировки к плану аудита (сверка с актуальным кодом 2026-08-09)
- **L1:** правило zero-downtime уже в AGENTS.md (`:321`, `:479-480`). PR-template отсутствует
  (`.github/PULL_REQUEST_TEMPLATE.md` нет). Реальный объём = создать PR-template с zero-downtime
  чекпоинтом + ссылку на пример миграции 058 (хороший) vs 077/084 (нарушение).
- **M6:** characterization-подушка уже частично есть — 5 ingress-тестов на хелперы
  (`test_helpdesk_ingress_{tx,search,match,extract,localize}.py`) + 1 integration. Нужен snapshot
  именно оркестратора `_ingest_message` (621–767), если integration-тест его end-to-end не покрывает.
- **M9:** `net_guard.py` уже создан (H1 закрыт `[x]`) — НЕ создаём заново, а подключаем
  `keycloak_admin._validate_keycloak_url`/`_is_unsafe_ip` к нему. В `services/keycloak/` уже есть
  `settings.py` (read-only runtime-cache `_KCSettings`) — НЕ трогаем, новый persistence-стор
  называем `admin_store.py`, чтобы не плодить два «settings» рядом.

## Чеклист (DoD)

### L1 — zero-downtime миграции в review-чеклисте
- [x] `.github/PULL_REQUEST_TEMPLATE.md` создан с zero-downtime чекпоинтом
- [x] Чекпоинт ссылается на AGENTS.md `:479` + примеры (миграция 058 ок, 077/084 — нарушение)
- [x] audit.md: L1 → `[x]`

### M6 — декомпозиция `_ingest_message` (~146 LOC → ~30 wiring)
- [x] Characterization: проверка показала, что `test_helpdesk_ingress_tx.py` (12 тестов на
      инварианты оркестратора) уже покрывает оркестратор end-to-end — новый snapshot не нужен
- [x] `_parse_and_match(db, msg, settings_row) -> _IngestMatch` (headers + ticket + requester + bodies)
- [x] `_persist_ticket_and_message(db, msg, match, message_id) -> _IngestPersist`
- [x] `_finalize_ingest(...) -> None` (commit + post-commit + notify) — единственное место `db.commit()`
- [x] `_ingest_message` ≤ 40 LOC wiring (фактически ~19 LOC)
- [x] Все 46 ingress unit-тестов зелёные до и после (1:1)
- [x] audit.md: M6 → `[x]`

### M9 — `keycloak_admin.py` God Module → тонкий роутер
- [x] `app/services/keycloak/admin_store.py` — `load_settings`/`save_settings`/`migrate_legacy` + модели
- [x] `app/services/keycloak/probe.py` — `test_oidc_connection`/`test_sync_connection`/`require_configured`
- [x] `net_guard` расширен: `is_unsafe_internal_ip`/`is_safe_internal_url` (allow-private для Keycloak)
- [x] Роутер использует `net_guard` (через admin_store) вместо локального `_is_unsafe_ip`/`_validate_keycloak_url`
- [x] Роутер — тонкий wiring (deps → service → response), 394→181 LOC (−54%)
- [x] −~213 LOC из роутера (DoD просил −150)
- [x] Тесты на test-endpoints с моком Keycloak (probe + роутерные 400-кейсы)
- [x] audit.md: M9 → `[x]`

### Общее
- [x] `backend/scripts/ci_lint.sh` зелёный (ruff + format + mypy, 759 файлов)
- [x] `pytest tests/unit` зелёный (4344 passed, 5 skipped)
- [x] `tests.generated.md` регенерирован (−9 test_is_unsafe_ip, +24 net_guard allow-private)
- [x] drift openapi/types — синхронны (контракты не менялись)
- [x] audit.md: 3 карточки `[x]`

## Решения по ходу
- 2026-08-09: старт. Порядок L1 → M6 → M9. Корректировки к аудиту — выше.

## Грабли / контекст
- AGENTS.md: проверять через `backend/scripts/ci_lint.sh`, не локальными ruff/mypy.
- M6: критический путь email-ingress. Регрессии тут уже были (20.07.2026). Только пошагово,
  каждый коммит — зелёный тест. Инвариант: `db.commit()` только в `_finalize_ingest`.
- M9: НЕ объединять `admin_store.py` (persistence, Admin UI, `KeycloakSettings`) с существующим
  `settings.py` (read-only runtime-cache `_KCSettings`) — разные модели, разные потребители.
- M9: при подключении `net_guard` проверить, что SSRF-семантика для Keycloak (`_BLOCKED_HOSTNAMES`)
  покрывается net_guard API, иначе расширить net_guard аккуратно.
- main защищена — только PR + 16 обязательных чеков. Коммитит/мёрджит пользователь.
