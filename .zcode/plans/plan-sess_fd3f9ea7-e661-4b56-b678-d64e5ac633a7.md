# Inline-картинки в ответах helpdesk (агент + инициатор)

## Цель
Агент и инициатор могут вставлять картинки **прямо в текст** сообщения (форматированный редактор вместо plain-textarea). В портале картинка рендерится через `/api/v1/helpdesk/attachments/{id}`; в **письме заявителю** встраивается в само письмо как `cid:`-attach (`multipart/related`), как в OTRS/Zammad — корректно видно везде, включая гостей без аккаунта.

## Ключевая развилка (почему так много слоёв)
1. `RichEditor.vue` сейчас отдаёт **Markdown** (`getMarkdown()`), а helpdesk хранит **HTML** (`body_html`). Нужно параметризовать редактор режимом вывода.
2. Для CID-embed в email нужен **маркер «inline»** на `HelpdeskAttachment` (сейчас все вложения одинаковые) + поддержка `multipart/related` в helpdesk-билдере (инфраструктура уже есть в news-билдере — переносим).
3. Картинку нельзя загрузить, пока не создано сообщение (нужен `message_id` для привязки). Для **ответов** сообщение уже есть (draft-upload к сообщению); для **создания заявки** — курица-яйца: решаем через draft-attachments (`message_id=NULL`), которые backfill'ятся в момент создания сообщения и чистятся cron'ом.

---

## Этап 1 — Backend: модель + миграция (маркер inline)

**`backend/app/models/helpdesk.py`** — в `HelpdeskAttachment` добавить колонки:
- `is_inline: bool` (default `False`, server_default `false`)
- `content_id: str | None` (VARCHAR(320), nullable) — CID без угловых скобок, для inline-картинок

**Миграция `077_add_helpdesk_attachment_inline.py`** — `ALTER TABLE helpdesk_attachments ADD COLUMN is_inline BOOLEAN NOT NULL DEFAULT false`, `ADD COLUMN content_id VARCHAR(320)`. Zero-downtime (nullable/has-default). Индекс на `message_id WHERE is_inline` (опц.).

Тесты: `tests/unit/test_helpdesk_models.py` — поля дефолтятся правильно.

---

## Этап 2 — Backend: inline-media эндпоинт (загрузка картинки в тело)

**Новый роутер `backend/app/api/helpdesk/inline_media.py`** (регистрация в `__init__.py`):
- `POST /tickets/{ticket_id}/messages/{message_id}/inline-media` (агент, к существующему сообщению) и `POST /tickets/{ticket_id}/inline-media` (агент, без message — для draft-ответа перед отправкой).
- Принимает `file: UploadFile` (Form), MIME ∈ image/{png,jpeg,gif,webp}, лимит `HELPDESK_MAX_ATTACHMENT_MB` (текущий 25 — для картинок многовато, но оставлю общий конст для единообразия; опц. ввести `HELPDESK_INLINE_IMAGE_MAX_MB=10`).
- Сохраняет через `attachments.save_inline_image(...)` (новый метод — создаёт `HelpdeskAttachment(is_inline=True, content_id=gen)`, `message_id` передаётся опционально), возвращает `{ "url": "/api/v1/helpdesk/attachments/{id}", "filename": ... }` (формат как у news/kb-media — переиспользуем `useEditorImageUpload` как есть).
- Для инициатора — `POST /tickets/my/{ticket_id}/inline-media` (draft, без message): аналогично, но запись от текущего пользователя; message_id проставляется при отправке ответа/создании заявки (backfill).
- Раздача — **существующий** `GET /attachments/{id}` (`StreamingResponse`, ACL владелец/агент/админ). Для портала этого достаточно (пользователь аутентифицирован). **Отдельного публичного эндпоинта не нужно** — в письме картинка едет как CID, а не ссылкой.

**`backend/app/services/helpdesk/attachments.py`** — добавить `save_inline_image(db, *, ticket, uploaded_by, data, original_name, message_id=None) -> HelpdeskAttachment` (по образцу `save_image_bytes`, но ставит `is_inline=True`, генерирует `content_id`).

Тесты: `tests/unit/test_helpdesk_attachments.py` + `tests/integration/test_helpdesk_inline_media.py` (загрузка, ACL, возврат url).

---

## Этап 3 — Backend: backfill draft-attachments при отправке

В сервисах/роутерах, где создаётся сообщение с `body_html`, после `db.flush()` (есть `message.id`):
- `create_ticket` (`services/helpdesk/tickets.py`): при наличии переданных draft-attachment-id → `UPDATE helpdesk_attachments SET message_id = :new WHERE id IN (...) AND ticket_id IS NULL AND uploaded_by = :user`.
- `add_my_message` / `add_agent_message` — то же самое.

Сессия формы передаёт `inline_attachment_ids: list[uuid]` (Form, optional) вместе с `body_html`. Draft-attachments — это те же строки `HelpdeskAttachment` с `message_id=NULL`, привязанные к `uploaded_by_user_id`.

---

## Этап 4 — Backend: MIME-билдер (CID-embed в письме)

**`backend/app/worker/tasks/email_outbox.py::_build_helpdesk_mime`** — новая логика структуры:
- Читать из payload новое поле `inline_images: [{cid, filename, content_type}]` (метаданные; байты читаются с диска как у обычных вложений — НЕ base64 в payload, т.к. helpdesk-файлы уже на диске).
- При наличии inline-картинок: `multipart/mixed` (если есть обычные вложения) → `multipart/related` → `multipart/alternative`(plain+html) + inline-части с `Content-ID: <{cid}>`, `Content-Disposition: inline` (переиспользуем паттерн `_attach_inline_image`, но читаем с диска через aiofiles вместо base64).
- Без inline — текущая логика без изменений.

**`backend/app/services/helpdesk/outbound.py::enqueue_reply_outbound`**:
- При выборке `HelpdeskAttachment` разделить на `inline_images` (is_inline=True, с content_id) и обычные `attachments`. В payload класть `inline_images: [{cid, filename, content_type}]` отдельным списком.

**`backend/app/services/helpdesk/email_template.py`** — добавить `_inline_src_to_cid(html, inline_map)`:
- Перед рендером письма: для inline-attachment'ов сообщения переписать в HTML их `src="/api/v1/helpdesk/attachments/{id}"` → `src="cid:{content_id}"` (по карте id→cid). Вызывается **до** `_absolutize_img_src` (который не трогает `cid:` — подтверждено). Обычные `/api/...`-ссылки на не-inline вложения остаются абсолютными (или вообще не появятся, т.к. они не в теле).

Тесты: `tests/unit/test_helpdesk_outbound_mime.py` (структура related, заголовки Content-ID), `test_helpdesk_outbound_enqueue.py` (разделение inline/attachment в payload), `test_helpdesk_email_template.py` (src→cid).

---

## Этап 5 — Frontend: параметризация RichEditor (outputFormat)

**`frontend/src/components/RichEditor.vue`**:
- Новый prop `outputFormat?: 'markdown' | 'html'` (default `'markdown'` — backward-compatible для news/kb).
- В `onUpdate`: при `'html'` отдаём `editor.getHTML()`, иначе `getMarkdown()`. В `watch(modelValue)`: при html-режиме сравниваем через `getHTML()` и `setContent` HTML.
- Все остальные возможности (тулбар, link/video/details) переиспользуются.

Тесты: `RichEditor.spec.ts` — emit markdown по умолчанию, emit html при `outputFormat="html"`.

---

## Этап 6 — Frontend: формы helpdesk (агент + инициатор)

**`frontend/src/components/helpdesk/TicketReplyForm.vue`** — заменить `n-input textarea` на `RichEditor outputFormat="html" uploadEndpoint=...`:
- `uploadEndpoint` зависит от режима: агент → `/api/v1/helpdesk/tickets/{ticketId}/messages/{messageId}/inline-media` (но messageId ещё нет у нового ответа) → **новый draft-эндпоинт** `/api/v1/helpdesk/tickets/{ticketId}/inline-media` (без message, создаёт draft-attachment, возвращает url+id). При отправке формы передаём собранные `inline_attachment_ids`.
- Эмитит `{ bodyHtml, bodyText(опц. fallback), visibility, files, inlineAttachmentIds }` (bodyText = тривиальная деривация из html через strip-тегов, либо оставляем требование «текст обязателен» — уточню поExisting-коду; вероятнее body_text = plain-derivation).
- Переключатель visibility остаётся.

**`frontend/src/pages/helpdesk/HelpdeskMyTicketDetailPage.vue`** + **`HelpdeskAgentTicketDetailPage.vue`** — прокинуть `ticketId` в форму, обработать новый payload (передать `body_html` + `inline_attachment_ids` в API-вызовы).

**`frontend/src/components/helpdesk/TicketCreateModal.vue`** — `description`-поле → RichEditor (html). Draft-upload через `/tickets/my/{ticketId}/inline-media` — но при создании заявки ещё нет ticketId. **Решение:** отдельный draft-эндпоинт `POST /helpdesk/draft-inline-media` (без ticket/message), backfill по `inline_attachment_ids` в `create_ticket`. Чистится cron'ом.

**`frontend/src/api/helpdesk.ts`** — добавить `uploadInlineMedia(...)`, обновить `createTicket`/`addAgentMessage`/`addMyMessage` сигнатуры (`body_html`, `inline_attachment_ids`), `helpdeskAttachmentUrl`.

**i18n** (`ru.json` мастер + `en.json`) — `helpdesk.replyPlaceholder` обновить, ключи для кнопок редактора (переиспользовать `editor.*` где есть).

Тесты: компонентные тесты формы, проверка `i18n:check`.

---

## Этап 7 — Backend: санитизация HTML на приёме

В роутерах `create_ticket`/`add_my_message`/`add_agent_message` при наличии `body_html` (или `description_html`):
- Прогон через `sanitize_html(...)` (nh3, как в ingress) — защита от XSS (вставки агентов/инициаторов идут в БД и в письмо). `body_text` = деривация из sanitized html (strip тегов) если не передан отдельно.
- `create_ticket`: добавить optional `description_html: str | None` Form-поле (в `TicketCreateIn`), сохранять sanitized.

---

## Этап 8 — Cron: очистка orphan draft-attachments

**`backend/app/worker/tasks/helpdesk.py`** — новая cron-задача `cleanup_orphan_inline_drafts` (раз в час): удалять `HelpdeskAttachment WHERE message_id IS NULL AND created_at < NOW() - 1h` (файлы + записи). Регистрация в cron-таблице. Это закрывает утечку disk-space от брошенных форм.

---

## Этап 9 — Документация

**`docs/helpdesk.md`**:
- §6 Вложения — подраздел «Inline-картинки в теле» (маркер is_inline/content_id, draft-attachments, backfill, cron-очистка).
- §8 Email — обновить описание outbound: `multipart/related` + CID-embed.
- §4 API — новые эндпоинты inline-media + новые поля (body_html, inline_attachment_ids).
- Модель `helpdesk_attachments` — новые колонки.

**`docs/db-schema.md`** (curated) — колонки `is_inline`/`content_id`.
**`docs/api-contracts.md`** — новые эндпоинты (или пометка «regenerate» — `python -m scripts.generate_api_contracts_doc`).

---

## DoD / проверки
- `ruff check . && mypy app && pytest tests/unit` (backend)
- `pytest tests/integration -m integration` (helpdesk inline-media + mime)
- `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check` (frontend)
- Ручная проверка (Playwright): агент вставляет скриншот в ответ → в портале видна inline → в письме заявителю картинка встроена (cid), не битая; инициатор то же в создании заявки.

---

## Риски / грабли (фиксирую в плане фичи)
- **Outlook/Gmail inline-CID**: некоторые клиенты не рендерят `multipart/related` без `Content-Location`; добавим оба заголовка (`Content-ID` + опц. `Content-Location`) для совместимости.
- **Размер письма**: CID-embed увеличивает размер письма → возможно ограничить суммарный размер inline-картинок (конст `HELPDESK_MAX_TOTAL_INLINE_MB`).
- **sanitize_html vs FigureImage**: убедиться, что `<figure data-type="figure-image">`/`<figcaption>` проходит nh3-санитайзер helpdesk (может потребоваться allowlist тегов — проверить `app/core/sanitize.py::sanitize_html`, при необходимости расширить).
- **Draft-orphan при закрытии вкладки**: cron-очистка закрывает, но в первые часы файл существует без сообщения — допустимо (ACL по uploaded_by).
- **initiator plain-text fallback**: body_text должен быть осмысленным для email-клиентов без HTML и для превью уведомлений — деривация через html→plain.

## Что НЕ делаем
- Не меняем формат хранения news/kb (они остаются Markdown).
- Не делаем публичную раздачу вложений (CID решает проблему email без публичного URL).
- Не внедряем SVG inline (блокируется почтовыми клиентами) — svg-filter на inline-upload.

## Создам план фичи
Так как задача многосессионная — в начале реализации создам `docs/wip/helpdesk-inline-images.md` (handoff-план по AGENTS.md).