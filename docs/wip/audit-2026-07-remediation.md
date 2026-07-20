# Фича: Remediation аудита 2026-07-20 (D-сложность + email-signature + гигиена)

> **Когда читать:** возобновляешь работу по свежему аудиту от 2026-07-20 —
> этот план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> **Источник аудита:** paste-attachment (диагностика; оригинал не закоммичен).

## Цель

Устранить точечный техдолг, выявленный аудитом 2026-07-20, и поставить
«прививку» против повторения сложностной регрессии (3 функции класса D в
новом helpdesk/MAX-коде). Крупного рефакторинга не требуется — работа
точечная, по принципу «сначала тест — потом правка» (AGENTS.md).

## Контекст (что и почему)

Свежий аудит сверил фактические gates с заявленными и нашёл:
- 🟠 **N1 — сложностная регрессия:** 3 функции ранга D в новом коде
  (раньше была планка «0 D/E, макс. C/18»). radon cc -n D:
  - `app/worker/tasks/email_outbox.py:428` — `_build_helpdesk_mime` — D (26)
  - `app/services/helpdesk/ingress.py:459` — `_ingest_message` — D (21)
  - `app/services/helpdesk/notifications.py:596` — `notify_ticket_created_max` — D (21)
- 🟡 **N2 — хрупкая эвристика `email_signature.py`:** срез по «первому паттерну
  по приоритету», а не по минимальной позиции — риск отрезать легитимный текст
  тела заявки, если фирменный цвет встретится раньше подписи.
- 🟢 **N3 — дрейф `docs/code-audit.md`:** устаревшие числа тестов и утверждение
  «0 функций D/E».
- 🟢 **N4 — гигиена тестов:** 76 eslint-warnings (преимущественно в тестах),
  `PytestUnraisableExceptionWarning: coroutine ... was never awaited` в
  `test_news_routes.py`.

**Позитив:** MAX-messenger (`_client.py`, `messenger_outbox.py`) написан аккуратно —
зеркало `email_outbox` (outbox-инвариант, distributed-lock, watchdog stale-SENDING,
DLQ, TLS через системный trust store для `*.max.ru`). Претензий нет.

## Решения по ходу

- **2026-07-20:** порядок работ внутри П1 — сначала декомпозиция 3 D-функций,
  потом снижение порога CI-gate F→D. Обратный порядок сразу ломает CI (3
  D-функции делают гейт красным). Это уточнение формулировки аудита: «добавить
  CI-gate radon» → фактически «снизить порог с F до D в существующем job'е
  `quality-gates`».
- **2026-07-20:** для `_build_helpdesk_mime` и `_ingest_message` характеризующие
  тесты уже есть (`test_helpdesk_inline_images_email.py`, `test_helpdesk_outbound_mime.py`,
  `test_helpdesk_ingress_tx.py`, `test_helpdesk_attachment_images_email.py`) —
  декомпозиция по принципу 1:1-контракта относительно безопасна. Для
  `notify_ticket_created_max` тестов в grep'е не видно → перед разбивкой
  дописать характеризующие тесты (happy path + MAX-failure + email-fallback).
- **2026-07-20:** `code-audit.md` лежит в `docs/` (не в `docs/wip/`). Отдельный
  `docs/wip/code-audit.md` — это старый remediation-чеклист от 2026-07-11,
  другой документ; при обновлении не перепутать.

## Чеклист (DoD)

### Приоритет 1 — вернуть планку качества (0.5–1 день)

- [ ] **P1.1 Декомпозиция `_build_helpdesk_mime` (D=26 → ≤ C).**
      Вынести в отдельные хелперы: построение заголовков (From/To/Subject/References),
      чтение вложений с диска (aiofiles), cid-инлайнинг (multipart/related).
      Контракт 1:1, characterize-тесты уже есть — прогнать до и после.
- [ ] **P1.2 Декомпозиция `_ingest_message` (D=21 → ≤ C).**
      Вынести: извлечение bodies/attachments, lookup/guest-creation заявителя,
      notify-dispatch. Контракт 1:1 (тесты: `test_helpdesk_ingress_tx.py`).
- [ ] **P1.3 Характеризующие тесты на `notify_ticket_created_max`** (до декомпозиции).
      Happy path (MAX-уведомление отправлено), MAX-failure (transient/permanent
      классификация → DLQ, email не страдает), email-fallback. Цель — func-cov ≥ 70%.
- [ ] **P1.4 Декомпозиция `notify_ticket_created_max` (D=21 → ≤ C).**
      После P1.3, контракт 1:1.
- [ ] **P1.5 Снизить порог CI-gate `quality-gates` с F → D.**
      `.github/workflows/ci.yml`: `radon cc app -n F` → `-n D`. После P1.1–P1.4
      репозиторий проходит новый порог; проверка `radon cc -n D app` локально = 0 строк.
      Это и есть «прививка» от повторения N1.
- [ ] **P1.6 DoD:** `ruff check . && mypy app && pytest tests/unit` зелёные;
      `radon cc -n D app` = 0; CI `quality-gates` зелёный.

### Приоритет 2 — устойчивость (0.5 дня)

- [ ] **P2.1 `email_signature.py`: срез по минимальной позиции.** Сейчас
      `strip_email_signature` возвращает срез по первому совпавшему паттерну из
      списка приоритета. Изменить: искать все маркеры, срезать по `min(pos)`.
      Тест-кейс: тело с фирменным цветом раньше подписи → тело сохраняется.
- [ ] **P2.2 Company-маркеры (`Mage_Ru.png`, `#7B92AE`, `#00479D`, `@mage.ru`)
      в именованный модуль-конфиг** с явным комментарием-владельцем про ребрендинг.
      Не в `system.json` (это продуктовая эвристика, не runtime-настройка) —
      константы в начале файла с TODO-владельцем.
- [ ] **P2.3 Обновить `docs/code-audit.md`:** актуальные числа тестов (3669 backend /
      2111 frontend), отметить N1 (после P1 закрыта) и N2 (после P2.1 закрыта).
      Цель — doc-as-memory не вводит следующую сессию в заблуждение.
- [ ] **P2.4 DoD:** тесты `test_helpdesk_email_signature.py` расширены (min-pos кейс);
      `ruff && mypy && pytest tests/unit` зелёные.

### Приоритет 3 — гигиена (фоном, 1–2 дня; можно частями)

- [ ] **P3.1 `PytestUnraisableExceptionWarning` в `test_news_routes.py`:**
      незамоканная async-заглушка (`coroutine ... was never awaited`). Починить
      mock-настройку.
- [ ] **P3.2 eslint-warnings в тестах (76 шт.):** преимущественно
      `vue/one-component-per-file` и `vue/require-prop-types`. Механическая
      чистка; убрать 2 неиспользуемых `eslint-disable`.
- [ ] **P3.3 (опционально, если остаётся время)** — пункты из прежнего аудита:
      FE-5 (`LinksTab.vue` → `useLinksAdmin.ts`), func-coverage hotspots
      (PhotosIndexPage, RoomGrid, GlobalSearch, NewsFormPage), декомпозиция
      длинных функций (`import_scan_run` 202, `oidc.callback` 171, `bulk_move_files` 125).
      Эти перенесены из прежнего техдолга и не относятся к свежему аудиту —
      брать только если П1+П2 закрыты и сессия не закончена.

## Грабли / контекст

- **Порядок P1:** декомпозиция (P1.1–P1.4) → снижение порога (P1.5). Обратный
  порядок ломает CI.
- **CI-gate уже есть** в `.github/workflows/ci.yml::quality-gates` — блок на F
  + jscpd (4%) + knip (информационно). Меняем только порог radon, не добавляем
  job. Прежний план (remediation-plan.md, item 16) заявлял radon-ratchet с
  CC>40 — фактически это и есть текущий F-порог.
- **`from __future__ import annotations` — НЕ добавлять** в `app/core/limiter.py`
  (ломает FastAPI-интроспекцию после monkey-patch, ADR-043). Если правки
  заденут limiter — не вставлять.
- **Образ backend вкомпилирован** (target `production`): после правок кода —
  `docker compose build backend`. CI проверяет на свежем build, но локально
  restart не подхватит.
- **MAX-messenger TLS:** сертификат `*.max.ru` подписан Russian Trusted Root CA
  (Минцифры), в образе через `backend/certs/russian_trusted_root_ca.crt` +
  `update-ca-certificates`. При правках httpx-клиентов MAX — использовать
  `ssl.create_default_context()` (системный trust store), не `certifi.where()`.
- **`notify_ticket_created_max` тестов в grep'е не видно** — это индикатор, что
  перед декомпозицией (P1.4) обязательно P1.3. Не пропускать.
- **Дека `docs/code-audit.md` ≠ `docs/wip/code-audit.md`:** первый — куративный
  аудиторский отчёт (43 КБ, актуализируем в P2.3), второй — старый remediation-чеклист
  от 2026-07-11 (можно не трогать).

## Handoff (заполняется в конце каждой сессии)

```
СДЕЛАНО: все 11 пунктов P1+P2+P3 закрыты в одной сессии.
  - P1.1 _build_helpdesk_mime D(26) → B(10)
  - P1.2 _ingest_message D(21) → C(11)
  - P1.3 +5 characterize-тестов на notify_ticket_created_max
  - P1.4 notify_ticket_created_max D(21) → B(6)
  - P1.5 CI-gate quality-gates: порог radon F→D
  - P1.6 DoD зелёный (ruff/mypy/3674 backend tests/radon -n D пусто)
  - P2.1 email_signature: срез по min(pos), +2 characterize-теста
  - P2.2 Company-маркеры → константы + TODO(owner: IT/branding)
  - P2.3 docs/code-audit.md актуализирован (тесты 3669/2111, сложность, CI-gate)
  - P3.1 PytestUnraisableExceptionWarning в test_news_routes.py (мок is_liked_by)
  - P3.2 eslint-warnings 76 → 10 (остаток — реальные a11y в src/, вне scope аудита)
В РАБОТЕ: —
ДАЛЕЕ: пользователь коммитит; всё готово к мёржу.
ОТКРЫТЫЕ ВОПРОСЫ:
  - Оставшиеся 10 eslint-warnings — a11y в production-компонентах
    (NewsCoverUpload, KbArticleFormPage, NewsFormPage). Не относятся к аудиту,
    отдельная задача P3 при желании.
КОММИТ: см. ниже
```
