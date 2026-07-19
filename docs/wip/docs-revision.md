# Фича: Ревизия и синхронизация документации (июль 2026)

> **Когда читать:** возобновляешь работу по наведению порядка в `docs/` —
> этот план хранит контекст между сессиями.
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.

## Цель

Дока не обновлялась ~3 недели (52 коммита). Кураторские файлы (`db-schema.md`,
`api-contracts.md`, `roles-matrix.md`) остановились на апреле-июне 2026 —
не отражают helpdesk (075–080), messenger/MAX (081), service_links.kb_url (074),
last_auth_method в `/auth/config`. Сгенерированная дока и `openapi.json` тоже
устарели. Часть `wip/`-планов помечена «реализовано», но не удалена.

## Состояние (на старте)

- ✅ Граф codebase-memory переиндексирован (moderate, 21436 узлов / 106807 рёбер,
  артефакт `.codebase-memory/graph.db.zst` обновлён).
- ✅ `docs/db-schema.generated.md` регенерирован (60KB → 80KB, +helpdesk/messenger).
- ✅ `docs/api-contracts.generated.md` регенерирован (196KB → 220KB, +helpdesk/MAX).
- ✅ `openapi.json` регенерирован (959KB, 292 paths, 326 schemas).

## Решения по ходу

- **2026-07-19:** Регенерация доков в контейнере — docs/ не смонтирован с хостом.
  `db-schema` умеет в stdout (работает `> ../docs/...md`), а `api-contracts`/`openapi`
  пишут в файл внутри контейнера. Решение: `--output /tmp/...` → `docker compose cp`.
  `openapi.json` экспорт пишет лог в stdout, JSON — в `/openapi.json` (тоже cp).

## Чеклист (DoD)

### Регенерация артефактов
- [x] Переиндексация графа (moderate)
- [x] `docs/db-schema.generated.md` — регенерирован (Docker → stdout redirect)
- [x] `docs/api-contracts.generated.md` — регенерирован (Docker → /tmp → cp)
- [x] `openapi.json` — регенерирован (Docker → cp)

### Кураторская дока
- [ ] `docs/db-schema.md`: обновить шапку (v1.12 → миграции 001..081), дополнить
      оглавление и шапку с упоминанием helpdesk/messenger, добавить перекрёстные
      ссылки на `helpdesk.md` (таблицы 075-081 детально описаны там)
- [ ] `docs/api-contracts.md`: обновить шапку (v1.5 → июль 2026), добавить секцию
      Helpdesk (краткую, со ссылкой на helpdesk.md §4), упомянуть `last_auth_method`
      в `/auth/config`, `service_links.kb_url`
- [ ] `docs/roles-matrix.md`: обновить шапку, добавить полную матрицу Helpdesk
      (агенты/module-gate/claim/assign/take/status/reopen + admin settings:
      mailbox/digest/max-bot + agents CRUD)

### Ревизия модульных доков
- [ ] `docs/helpdesk.md` — проверить актуальность (свежий, 19.07; сверить с кодом)
- [ ] `docs/email.md` — сверить с email_outbox текущим состоянием
- [ ] `docs/news.md`, `docs/meetings.md`, `docs/files.md`, `docs/photos.md`,
      `docs/feedback.md`, `docs/analytics.md` — беглая сверка со статусом

### Ревизия infra/ops доков
- [ ] `docs/deploy.md` — сверить (тома, certs/russian_trusted, версия стека)
- [ ] `docs/monitoring.md` — готовность/метрики
- [ ] `docs/testing.md` — команды, покрытие
- [ ] `docs/code-audit.md` — статус P0/P1/P2
- [ ] `docs/dev-onboarding.md` — окружение

### Индекс и операционка
- [x] `docs/README.md` — сверить роутер и индекс (добавил MAX в описание helpdesk)
- [x] `AGENTS.md` — сверить стек/команды/gotchas (обновил статус-машину helpdesk,
      добавил MAX-messenger, Russian Trusted CA, структуру репо с `backend/certs/`,
      `services/max_messenger/`, `messenger_outbox`)
- [x] `docs/code-audit.md` — обновил шапку (81 миграция, июль 2026)
- [~] `docs/deploy.md` — добавил §«Russian Trusted Root CA»
- [~] `docs/search.md` — поправил битую ссылку kb_acl.py → kb_acl/

### Очистка `docs/wip/` — ОТКРЫТЫЙ ВОПРОС для пользователя

Файлы под git, удаление = потеря исторического контекста. Оставляю как есть.
Пользователь решает: удалить реализованные (по правилу AGENTS.md «wip удаляется
при завершении фичи») или оставить как архив. Кандидаты на удаление:
- `news-reactions-comments.md` (✅ DoD закрыт 23/0)
- `directories.md` (явно помечен «реализовано»)
- `analytics-expansion.md` (✅ 10/0)
- `auth.md` (✅ 9/0, но auth постоянно дорабатывается — может быть актуален)
- `code-audit.md`, `remediation-plan.md` (исторические, спутники `code-audit.md`)

Кандидаты на **оставление** (DoD не закрыт или фича в активной разработке):
- `news-cover-focal-xy.md` ([ ]=23 — но фича реализована в миграциях 072/073)
- `news-email-share.md` ([ ]=17 — но фича реализована, `POST /news/{id}/share-email` в проде)
- `helpdesk-inline-images.md` ([ ]=10 — но фича реализована)
- `helpdesk-max-messenger.md` ([ ]=1 — последний пункт «ручная проверка с реальным ботом»)
- `helpdesk.md` (историческое ТЗ на 1507 строк, явно помечен «НЕ отражает текущее состояние»)
- `test-coverage-hardening.md` ([ ]=3 — ongoing работа)

## СДЕЛАНО (итог сессии)

Все кураторские и сгенерированные доки синхронизированы с актуальным кодом
(миграции 001..081, в частности helpdesk 075-081 + MAX-messenger). Модульные и
infra-доки проверены — устаревших ссылок нет (поправлена одна битая в `search.md`).
Граф codebase-memory переиндексирован, артефакт закоммичен.

См. финальный commit message в чате с пользователем.

## Грабли / контекст

- **Docker volume `docs/` не смонтирован:** `generate_*_doc.py` в контейнере пишет
  в `/app/docs/...` (parents[2] от /app/scripts = /), но этого пути в контейнере нет.
  Решение: явный `--output /tmp/...` + `docker compose cp backend:/tmp/... docs/...`.
  То же для `openapi.json` (лог в stdout, файл в `/openapi.json`).
- **Helpdesk детально описан в `helpdesk.md`** (свои таблицы, эндпоинты, статус-машина).
  В `db-schema.md`/`api-contracts.md`/`roles-matrix.md` не дублируем — даём краткую
  выжимку + перекрёстную ссылку. Принцип единственного источника истины.
- **`docs/wip/helpdesk.md`** — историческое ТЗ (1507 строк), явно помечено
  «НЕ отражает текущее состояние кода». Удалять или оставлять как архив? —
  оставить как есть (там есть пометка), но не удалять (историческая ценность).
