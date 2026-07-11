# Code audit remediation — P0+P1+P2(частично) (2026-07-11)

> Статус — в `docs/code-audit.md` §9.1–§9.3. Этот план оставлен до коммита; после — удалить.

## Закрыто
### P0 (4) — первая сессия
- ✅ FE-1 room.link XSS, H-3 OOM, H-1 SSRF, H-2 DB-tx

### P1 (4) — вторая сессия
- ✅ FE-2 dead code, H-4 CRLF, H-5 orphan files, FE-3 data-fetch

### P2 (частично) — третья сессия
- ✅ #14 bandit clean (0 High+0 Medium): B324 `usedforsecurity=False` + 8 `# nosec B608/B104`
- ✅ #16 мелочи §8: H-6 фикс (body_text escape в `<pre>`); E4/E5/E7/B2/B3/F6 — уже исправлены (audit устарел)
- ✅ #10 partial: классифицированы все 171 swallowing except (119 logged, 52 silent); 11/52 silent `pass` покрыты `logger.debug`

## Финальная проверка
- Backend: ruff + mypy — 0 ошибок; bandit — 0 High + 0 Medium; pytest tests/unit — **3291 passed**

## Открыто (для следующих сессий)
- **P1 #9** Frontend func-cov на hotspots — цель ≥ 70%
- **P2 #10 остаток** 41 silent swallow (health-check/diagnostic + graceful-degradation) — низкий приоритет
- **P2 #11** FE-4: 119 мест `t('errors.generic')` → `parseApiError` (механическая, ~30 файлов)
- **P2 #12** FE-5: LinksTab.vue → composable (script setup 274 LOC)
- **P2 #13** inline-SQL из api/kb/* в repo/service-слой
- **P2 #15** Декомпозиция: import_scan_run (202 LOC), oidc.callback (171), bulk_move_files (125) — нужен характеризующие тесты перед рефакторингом
- **P3 #17** CI gates: radon cc, knip, jscpd, function-coverage threshold
