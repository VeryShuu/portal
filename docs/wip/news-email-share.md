# Фича: Рассылка новости на email из справочника получателей

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Создаётся, как только ясно, что задача не закроется за одну сессию; удаляется
> после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Дать пользователю с правами `editor`/`admin` возможность из карточки
**опубликованной** новости нажать «Сделать рассылку», выбрать одного или
нескольких получателей **из справочника адресов** (ad-hoc-ввод запрещён) и
отправить им письмо с кратким текстом новости (автоген + правка). Отправка —
через существующий transactional outbox (`enqueue_outbox_email`), новый
SMTP-код не пишем.

## Объём

1. **Справочник получателей** `mailing_recipients` — новая таблица + CRUD
   (управление: `editor`/`admin`), UI через manage-drawer на странице новостей.
2. **Endpoint рассылки** `POST /news/{news_id}/share-email` — мульти-адрес,
   строго из справочника, только для `status="published"`.
3. **Frontend**: кнопка в `NewsDetailPage` + модалка с мульти-select из
   справочника и редактируемым кратким текстом; manage-drawer справочника.

## Зафиксированные решения

- **Источник адресов:** строго справочник `mailing_recipients`. Ad-hoc-ввод
  адреса в модалке **запрещён** (анти-спам/анти-фишинг от имени портала).
  Backend дополнительно валидирует, что каждый `recipient_id` существует и не
  удалён — клиенту не доверяем.
- **Адресация:** запрос принимает `recipient_ids: list[UUID]` (не сырые
  email), backend сам резолвит email из справочника. Это исключает подмену
  адреса в обход справочника.
- **Права справочника:** `editor`/`admin` (логично — рассылку делает редактор).
  Зафиксировать в `../roles-matrix.md`.
- **Только published:** для черновика/архива — `409` (ссылка вела бы на
  недоступную получателю новость).
- **Краткий текст:** дефолт — автоген из `body` (strip Markdown + обрезка
  ~300 симв.), редактор может переопределить (`message`, max 2000).
- **Транспорт:** `enqueue_outbox_email(kind=KIND_NEWS, ...)`, по одной строке
  outbox на получателя, каждая — в `session.begin_nested()` (изоляция сбоя,
  как в `notify_news_published`). Caller делает `db.commit()`.
- **Без переиспользования** движка `object_directories` — он про /staff-объекты
  с контактами, семантически не подходит. Заводим отдельную лёгкую таблицу.
- **Лимит получателей:** `max_length=100` на список (по аналогии с
  `invited_users` в meetings).
- **Rate limit:** `Depends(RateLimiter(times=10, minutes=1))` на send-endpoint.
- **Idempotency-Key:** опционально на send-endpoint (паттерн как в `POST /news`).

## План реализации

### Backend — справочник

- [ ] Миграция `migrations/versions/071_mailing_recipients.py`:
      таблица `mailing_recipients` (`id` UUID PK, `name` varchar(255),
      `email` varchar(320), `label` varchar(100) NULL,
      `created_by_user_id` UUID NULL → `ON DELETE SET NULL`,
      `created_at`/`updated_at`/`deleted_at` TIMESTAMPTZ).
      Частичный уникальный индекс `LOWER(email) WHERE deleted_at IS NULL`
      (как `idx_users_email_ci_active`).
- [ ] Модель `app/models/mailing_recipient.py`.
- [ ] Схемы `app/schemas/mailing_recipient.py`:
      `MailingRecipientCreate/Update/Public`, list-ответ
      `{items, total, limit, offset}`.
- [ ] Сервис `app/services/mailing_recipients.py`: CRUD + проверка уникальности
      по `func.lower(email)`, soft-delete, резолв `ids → email` для рассылки.
- [ ] Router `app/api/mailing_recipients.py` (+ регистрация в
      `app/api/__init__.py`): `GET` (list, любой авторизованный? — для дропдауна
      нужен `editor`+), `POST/PUT/DELETE` — `EditorDep`. На мутациях —
      `push_audit_event(...)` после commit.

### Backend — рассылка

- [ ] Схема `NewsShareEmailRequest` в `app/schemas/news.py`:
      `recipient_ids: list[UUID]` (`min_length=1`, `max_length=100`),
      `message: str | None` (max 2000).
- [ ] Сервис `app/services/news/email_share.py`:
      `build_news_excerpt(body, limit=300)` (strip Markdown) +
      `share_news_by_email(session, *, news, recipients, message, actor)` —
      собирает HTML+text (расширить `_build_news_email_html` блоком краткого
      текста), enqueue по получателю в `begin_nested`.
- [ ] Endpoint `POST /news/{news_id}/share-email` в `app/api/news/routes.py`:
      `EditorDep` + `RateLimiter(10/min)` + опц. `Idempotency-Key`; 404 если
      нет, 409 если не `published`; резолв `recipient_ids` (404/422 если есть
      неизвестные/удалённые id); `db.commit()` → `emit_news_audit(
      "news.email_shared", metadata={recipients_count})`.

### Frontend

- [ ] API-клиенты: `api/mailingRecipients.ts`, метод share в `api/news.ts`.
- [ ] Queries: `queries/mailingRecipients.ts` (list + CRUD-мутации),
      `useShareNewsEmailMutation` в `queries/news.ts`; ключи в `queries/keys.ts`.
- [ ] Компонент `components/news/NewsShareEmailModal.vue`:
      Naive UI `NModal` + `NSelect multiple filterable` (опции из справочника,
      без `tag`-режима) + `NInput textarea` (предзаполнен excerpt) + превью.
- [ ] Кнопка «Сделать рассылку» в `pages/NewsDetailPage.vue` (`.article__actions`,
      `v-if="auth.isEditor && news.status === 'published'"`).
- [ ] Manage-drawer справочника `?manage=mailingRecipients` на
      `pages/NewsListPage.vue` через `composables/useManageDrawer.ts` +
      `components/admin/MailingRecipientsSettings.vue`. Добавить команду в
      `composables/useGlobalSearchCommands.ts` (Cmd+K, admin/editor).
- [ ] i18n: ключи `news.share.*` + `mailingRecipients.*` в `i18n/ru.json`
      (мастер) и `en.json`; `npm run i18n:check`.

### Тесты

- [ ] Backend unit: сервис справочника (CRUD, уникальность email, soft-delete),
      сервис рассылки (N строк в outbox, изоляция сбойного получателя),
      endpoint (200/403 viewer/404/409 draft/валидация ids/лимит 100).
- [ ] Frontend unit: `NewsShareEmailModal.spec.ts` (мульти-select, правка
      текста, submit/ошибки) + тест manage-drawer справочника.

### Документация

- [x] `../db-schema.md` — таблица `mailing_recipients`.
- [x] `../api-contracts.md` — `/mailing-recipients/*` + `/news/{id}/share-email`.
- [x] `../roles-matrix.md` — права на справочник и рассылку (`editor`/`admin`).
- [ ] ADR — не нужен (решение зафиксировано здесь и в db-schema/api-contracts).

## Чеклист (DoD)

- [x] миграция / модель / схема
- [x] сервис (бизнес-логика)
- [x] API endpoint + регистрация
- [x] unit-тесты
- [x] frontend (api-клиент / query / компонент)
- [x] i18n (ru + en)
- [x] lint + typecheck + tests pass
- [x] обновлены `../` docs (если менялись БД/API/права/архитектура)

## Грабли / контекст

- **Outbox-инвариант:** строки `email_outbox` коммитятся в **той же**
  транзакции, что и бизнес-операция; caller обязан вызвать `db.commit()`.
- **`begin_nested()` на получателя:** без SAVEPOINT ошибка одного INSERT
  переводит сессию в PendingRollback и валит весь батч (см. комментарий E5 в
  `app/worker/tasks/notifications.py::notify_news_published`).
- **EmailStr нельзя** (DNS-проверка ломается на `.local`) — `email` хранить и
  валидировать как `str`. Но в рассылке клиент шлёт `recipient_ids`, а не email.
- **MIME header injection** уже закрыт `_sanitize_header` в воркере, но `email`
  в справочнике всё равно валидировать при создании.
- **HTML-escape** заголовка новости и `message` в шаблоне через `_esc`.
- **Уникальность email** — по `LOWER(email)` среди не удалённых (частичный
  индекс), lookups через `func.lower()`.
- Последняя миграция в репозитории — `070`, следующая свободная — `071`.
