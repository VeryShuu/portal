# Code audit remediation — P0+P1+P2(частично) + fix входа (2026-07-11)

> Статус — в `docs/code-audit.md` §9.1–§9.4. Этот план оставлен до удаления (после коммита fix входа).

## ✅ Закрыто полностью
### P0 (4) — commit `6e2648b`+
- FE-1 room.link XSS, H-3 OOM, H-1 SSRF, H-2 DB-tx

### P1 (4) — commit `e663d5e`
- FE-2 dead code, H-4 CRLF, H-5 orphan files, FE-3 data-fetch

### P2 (частично) — commit `e1ddcfc`
- #14 bandit clean (0 High+0 Medium)
- #16 мелочи §8 (H-6 фикс + 6 устаревших)
- #10 partial (11/52 silent залогированы)

### fix входа — незакоммичено (ждёт пользователя)
- L1 monkey-patch `fastapi-limiter` для starlette 1.x
- L2 `portal_base_url` нормализация (validator + system.json)
- L3 убран `from __future__ import annotations` из limiter.py
- Тест `test_rate_limiter_skips_routes_without_path`

## Открыто (для следующих сессий)
- **P1 #9** Frontend func-cov на hotspots — цель ≥ 70%
- **P2 #10 остаток** 41 silent swallow (health-check/diagnostic + graceful-degradation) — низкий приоритет
- **P2 #11** FE-4: 119 мест `t('errors.generic')` → `parseApiError` (механическая, ~30 файлов)
- **P2 #12** FE-5: LinksTab.vue → composable (script setup 274 LOC)
- **P2 #13** inline-SQL из api/kb/* в repo/service-слой
- **P2 #15** Декомпозиция: import_scan_run (202 LOC), oidc.callback (171), bulk_move_files (125) — нужен характеризующие тесты перед рефакторингом
- **P3 #17** CI gates: radon cc, knip, jscpd, function-coverage threshold

## Грабли (важно для будущих сессий)
- **limiter.py**: НЕ добавлять `from __future__ import annotations` — ломает FastAPI-интроспекцию `Request`/`Response` после monkey-patch `RateLimiter.__call__` (→ 422). Подробно в `docs/code-audit.md` §9.4.
- **fastapi-limiter** 0.2.0 не решает проблему (та же ошибка + breaking API). Monkey-patch — единственный путь.
- **Образ backend**: код вкомпилирован (target `production`), volume только `/data/*`. После правок — `docker compose build backend`.
- **portal_base_url**: должен включать scheme (`https://...`). Валидатор `_schemas.py` добавляет автоматически, но при ручном редактировании `system.json` — указывать явно.
