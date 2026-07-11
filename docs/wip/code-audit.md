# Code audit remediation — P0+P1 ЗАВЕРШЕНЫ (2026-07-11)

> Все P0 (4) и P1 (4) закрыты. Статус — в `docs/code-audit.md` §9.1 + §9.2.
> Этот план оставлен до коммита; после — удалить.

## P0 (закрыты в первой сессии)
- ✅ **FE-1** room.link XSS — `safeRoomLink()` + валидация формы
- ✅ **H-3** OOM remote-fetch — стриминг + счётчик байт
- ✅ **H-1** SSRF DNS-rebinding — двойной резолв с пиннингом IP
- ✅ **H-2** DB-tx при HTTP — remote-fetch post-commit в отдельной сессии, max-count=50

## P1 (закрыты во второй сессии)
- ✅ **FE-2** Удалены 5 осиротевших .vue (OnboardingPreview, OnboardingRolesPicker, KbPlaceholderPage, PhotosTab, LoginPage) + очищены smoke-тесты
- ✅ **H-4** Header injection CRLF — `_sanitize_header_field()` в outbound.py (оба продюсера), 3 теста
- ✅ **H-5** Orphaned files при rollback — `_TotalTracker.record()` + `cleanup_recorded_files()`, try/rollback/cleanup в _ingest_message и upload_attachments, 3 теста
- ✅ **FE-3** Data-fetch в SystemTab/LinksTab — 9 mutations в queries/admin.ts, перевод на mutations + parseApiError

## Финальная проверка
- Backend: ruff + mypy — 0 ошибок; pytest tests/unit — **3290 passed**
- Frontend: lint:check — 0 ошибок; typecheck — 0 ошибок; test:unit — **1922 passed**; i18n:check — OK

## Открыто (для следующих сессий — P1 остаток + P2)
- **P1 #9** Frontend func-cov на hotspots (PhotosIndexPage, RoomGrid, GlobalSearch) — цель ≥ 70%
- **P2 #10** 170 swallowing `except Exception` — классифицировать и сузить в топ-12 файлах
- **P2 #11** `parseApiError` вместо `t('errors.generic')` в 70+ местах (FE-3 частично закрыл LinksTab)
- **P2 #12** LinksTab.vue → composable (script setup 274 LOC)
- **P2 #13** inline-SQL из api/kb/* в repo/service-слой
- **P2 #14** `hashlib.sha1(usedforsecurity=False)` + `# nosec B608`
- **P2 #15** Декомпозиция длинных функций (import_scan_run, oidc.callback, bulk_move_files)
- **P2 #16** Мелочи §8 (H-6, E4/E5/E7/F6/B2/C4/C5)
- **P3 #17** CI gates: radon cc, knip, jscpd, function-coverage threshold
