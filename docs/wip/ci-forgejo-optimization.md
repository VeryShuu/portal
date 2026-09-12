# Фича: CI-оптимизации после миграции GitHub → Forgejo

## Цель
Доработать CI под Forgejo Actions после переезда (commit `7f7ebe0`):
ускорить пайплайн и убрать избыточные rebuild. Стек: `.forgejo/workflows/ci.yml`
(+ `nightly-flakes.yml`, `nightly-security.yml`).

## Статус (сессия 2026-08-11, миграция добита)

**8 слоёв миграционного долга сняты (PR #2–#8 смёржены):**
| PR | что | итог |
|---|---|---|
| #2 | xdist backend-unit (17→~4мин) | ✅ merged |
| #3 | gitleaks+trivy под docker-in-dind (create+cp) | ✅ merged |
| #4 | publish-images `success()`→`!failure()` | ✅ merged (недостаточно — см. #6) |
| #5 | vitest testTimeout 15с (flaky page-mount) | ✅ merged |
| #6 | validate-release-tag не-skipped (Forgejo auto-skip на skipped need) | ✅ merged — publish СТАЛ запускаться |
| #7 | permissions:packages:write | ✅ merged (Forgejo не honoured — см. #8) |
| #8 | REGISTRY_TOKEN (PAT write:package) для push | ✅ merged — **5/6 образов публикуются** |
| #9 | **Tier 2a**: postgres pull из registry вместо rebuild | ⏳ CI-green (run #105), **ждёт мёрджа** |

**publish-images**: 5/6 образов идут в `forgejo.mage.ru/mage/*` (backend/frontend/nginx/nginx-config/**postgres**). `portal-screenshot` падал на `413 Request Entity Too Large` (образ Chromium > nginx `client_max_body_size`) — **оператор увеличил буфер**, ждём проверки на ближайшем push:main.

**Tier 2a (PR #9)** валидирован на CI: `build-postgres` → `✓ Pulled portal-postgres:16 from registry (skipped build)` (~2с вместо ~2-3мин rebuild). Job-id сохранён → потребители не меняются.

### ⚠️ Нерешённое: branch protection блокирует API-мёрджи
PR #5-#8 мёрджились оператором через UI (по всей видимости, admin-override).
API-мёрдж (`POST /pulls/{n}/merge`) возвращает 405 «Not all required status checks
successful» — хотя фактически все 17 required-чеков `status=success`.
**✅ РЕШЕНО (2026-08-11).** Корневая причина: Forgejo branch-protection `status_check_contexts`
использует **exact-string match**, а суффикс события ` (pull_request)` — часть строки.
Исходные 17 шаблонов хранились БЕЗ суффикса → ни один не матчится → API-мёрдж 405
(но UI-мёрдж работал, т.к. `apply_to_admins: false` → админ обходит защиту).
Дополнительно 2 ошибочных имени:
  - `CI / secrets / gitleaks` → реально `security / secrets / gitleaks` (workflow security.yml);
  - `CI / coverage / diff-coverage gate` → реально `CI / coverage / diff-coverage gate (≥80% new code)`.
Фикс: PATCH `status_check_contexts` = ровно 17 строк дословно из
`GET /commits/{sha}/status` (head зелёного PR) — все с суффиксом ` (pull_request)` +
2 исправленных имени. Cross-check: все 17 == green actual contexts ✅.
Эмпирический способ для будущих правок required-checks см. в memory
`forgejo-status-check-suffix.md`. Рантайм-подтверждение: следующий PR с API-мёрджем.

### Tier 2 — что осталось
- **2c path-фильтры**: ❌ ОТКАТАНО. Реализован был (PR #13 + фикс #16) подход «no-op success»
  (detect-changes job + relevance-guard в 9 тяжёлых job'ах). Реверт в PR `revert/path-filters-keep-quoting`
  (ci.yml восстановлен к состоянию #15). Причина: act (forgejo-runner) нестабильно handling'ает
  шаги с **явным** `working-directory:` в пропущенных (if-gated) job'ах — backend-integration падал
  на `chdir to backend failed` (хотя guard отрабатывал). Линт/unit/coverage/quality no-op'или ОК,
  но service-jobs (integration/e2e/compose) с их mixed working-directories — нет. Решение оператора:
  стабильность > оптимизация → реверт. Оставлен #15 (quoting DATABASE_URL — реально починил
  `5432:portal` flake) + его debug-step. Вернуться к path-filter'ам можно позже через
  checkout-перед-guard (чтобы backend/ существовал до chdir) — отдельной задачей.
- **2b layer-cache**: НЕ начат. Опционально, отложено.

## Решения по ходу
- 2026-08-14: **безопасное сокращение critical path** — `build-postgres` перенесён
  на последовательный `ci-services`, `backend-integration` зависит только от него,
  затем последовательно идут E2E и compose smoke. Lint/unit/coverage/contract jobs
  выполняются параллельной веткой и остаются обязательными gates для merge и
  `publish-images`. В frontend-lint устранены повторные gen:types/vue-tsc через
  единый `npm run build`; из E2E удалён gen:types, который уже выполняет `predev`;
  tests-generated больше не поднимает неиспользуемый Node toolchain.
- 2026-08-11: **Phase 1 (xdist)** — отдельным PR `ci/backend-unit-xdist`.
  Проблема была НЕ в xdist, а в коллекции coverage-файла на forgejo-раннере.
  Фикс: `coverage combine || true` в staging-шаге + dotfile→visible. Провалидировано
  end-to-end в `.venv-ci` на реальном app. TODO(perf) из ci.yml:95 снят.
- 2026-08-11: **path-фильтры → подход «no-op success»** (решение пользователя):
  каждый джоб стартует, но если релевантные пути не менялись — exit 0 (success).
  Обязательные чеки всегда зелёные → мёрдж не блокируется. True-skip (`if:`) отвергнут
  из-за риска со skipped required checks на Forgejo (branch protection ещё не доделана).
- 2026-08-11: Phase 1 = standalone PR, Tier 2 = следующий PR (после решения по path-фильтрам).

## Чеклист (DoD)

### Phase 1 — xdist для backend-unit ✅ (PR `ci/backend-unit-xdist`, ждёт мёрджа)
- [x] `-n auto` в pytest unit+security
- [x] COVERAGE_FILE на уровень job
- [x] staging: `coverage combine || true` + dotfile→visible
- [x] validate локально (.venv-ci, реальные тесты)
- [x] YAML парсится, SHA-pins 40 символов
- [ ] первый зелёный прогон на CI → подтвердить ~4мин
- [ ] после зелёного: снять `timeout-minutes: 30` → ужать до ~10–12

### Tier 2

#### 2a. portal-postgres из registry (без rebuild каждый прогон)
- [ ] переименовать `build-postgres` → `postgres-image`, логика:
      detect changes `postgres/**` + `backend/migrations/init.sql` (всё, что COPY'ит
      `postgres/Dockerfile`);
- [ ] если не изменилось (и event != push:main): `docker login` (GITHUB_TOKEN,
      package:read) + `docker pull forgejo.mage.ru/mage/portal-postgres:16`, retag →
      `portal-postgres:16`;
- [ ] fallback на `docker build` если pull упал (404/нет образа — образ публикуется
      только на push:main через `publish-images`, на самом первом PR после миграции
      его может ещё не быть);
- [ ] если изменилось ИЛИ push:main: `docker build` (с layer-cache из 2b);
- [ ] `docker save` → artifact (потребители `backend-integration`, `frontend-e2e` НЕ меняются);
- [ ] проверить: registry-reachable на раннере, есть ли уже `portal-postgres:16` в registry.

#### 2b. docker layer-cache
- [ ] buildx docker-container driver + `type=local` cache (через `actions/cache`,
      работает на PR без прав на запись в registry; `type=gha` в Forgejo НЕТ);
- [ ] сначала под postgres (гоняется каждый прогон → макс. выигрыш);
- [ ] потом publish-images (app-образы: backend pip / frontend npm) — больший объём,
      но publish только на push:main.

#### 2c. path-фильтры (no-op success)
- [ ] первый джоб `detect-changes`: `git diff --name-only origin/main...HEAD` →
      outputs: `backend`, `frontend`, `postgres`, `infra`, `docs` (booleans);
- [ ] каждый джоб: early-exit 0 если свой флаг false (но чек остаётся зелёным);
- [ ] НЕ использовать `paths:` на trigger-уровне и `if:`-skip (блокирует required checks);
- [ ] группы путей (черновик):
      backend → `backend/**`, `scripts/` (python), `pyproject.toml`;
      frontend → `frontend/**`;
      postgres → `postgres/**`, `backend/migrations/init.sql`;
      docs-only → `docs/**`, `*.md` → можно вообще skip без риска (не required);
- [ ] после внедрения — проверить что ВСЕ 17 required checks остаются зелёными на
      «чужом» PR (e.g. docs-only).

## Грабли / контекст
- **publish-images** пушит `forgejo.mage.ru/mage/portal-postgres:16` ТОЛЬКО на
  `push: main` (и теги v*) — на PR registry содержит образ последнего main.
  → для PR с правкой postgres нужен локальный build (выше в 2a).
- **branch protection настроена** (2026-08-11): 17 required checks с суффиксом
  `(pull_request)` + exact-string match (см. memory `forgejo-status-check-suffix.md`).
  True-skip path-фильтры заблокируют мёрдж, когда required checks включат → поэтому
  для 2c выбрали no-op success.
- **docker-compose.yml** уже поддерживает registry-pull через `IMAGE_PREFIX`
  (line 14: `image: ${IMAGE_PREFIX:-}portal-postgres:16`) — это prod-флоу (ADR-045);
  CI-флоу (2a) ортогонален, идёт через `docker pull` + retag.
- **shellcheck-джоб** гоняет только `git ls-files '*.sh'` — inline `run:`-блоки в YAML
  НЕ проверяются (важно при правках bash в workflow).
- **upload-artifact@v3** (НЕ v4+) на forgejo-раннере: игнорирует dotfiles — поэтому
  `.coverage.unit` всегда копируется в видимое `coverage-unit.data`.
- При правках SHA-pins actions — проверять `length==40` (я в Phase 1 случайно
  сократил SHA setup-python, отловил проверкой).
