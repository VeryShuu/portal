# Фича: Inline-картинки в ответах helpdesk (агент + инициатор)

## Цель
Агент и инициатор могут вставлять картинки прямо в текст сообщения (форматированный
редактор вместо plain-textarea). В портале картинка рендерится через
`/api/v1/helpdesk/attachments/{id}`; в письме заявителю встраивается в само письмо
как `cid:`-attach (`multipart/related`), как в OTRS/Zammad — корректно видно везде,
включая гостей без аккаунта.

## Решения по ходу
- 2026-07-14: подход — полное решение с CID-embed (не «только портал»), объём — агент + инициатор.
- 2026-07-14: RichEditor параметризовать `outputFormat` (default markdown — backward-compat для news/kb; html для helpdesk).
- 2026-07-14: курица-яйца для создания заявки (нет ticket_id) — draft-attachments (`message_id=NULL`), backfill в момент создания, cron-очистка.
- 2026-07-22: Этап 5 (`outputFormat`) НЕ реализован — вместо параметризации RichEditor используется альтернативный подход: `tiptap-markdown` отдаёт markdown, фронт рендерит в HTML через `mdUnsafe.render()` на submit (как KB/news). Результат идентичен, код проще. Чекбокс Этапа 5 оставлен открытым как «неактуальный подход».
- 2026-07-22 (Этап 3): реализован draft-attachments. Решения: (1) хранение в **БД-таблице** `helpdesk_draft_attachments` (не FS-only) — детерминированная ACL через `uploaded_by_user_id`, audit-след, проще дебажить; (2) постоянное хранилище — `TKT-{number}/inline/` (унификация с `media.py` ответов, не корень через `save_image_bytes`), URL после backfill `/tickets/{id}/inline-media/{name}`; (3) TTL 24ч + лимит 20 draft/юзер (баланс: покрывает обед/ночь/выходные, не копит мусор).

## Чеклист (DoD)
- [x] **Этап 1**: модель HelpdeskAttachment (`is_inline`, `content_id`) + миграция 077 — выполнено (`backend/app/models/helpdesk.py:257-260`).
- [x] **Этап 2**: backend inline-media эндпоинт + `save_inline_image` — выполнено (`backend/app/api/helpdesk/media.py`, streaming upload).
- [x] **Этап 3**: backfill draft-attachments при `create_ticket` — выполнено (`backend/app/services/helpdesk/drafts.py::backfill_draft_images`, миграция 082, модель `HelpdeskDraftAttachment`, `POST/GET /draft-attachments`). Перенос draft-файлов в `TKT-{number}/inline/`, rewrite `src` на inline-media URL, удаление draft-строк (атомарно в транзакции создания тикета). Backfill для ответов НЕ нужен — у них уже есть `ticket_id` → `inline-media`.
- [x] **Этап 4**: MIME-билдер CID-embed (`multipart/related`) + outbound payload + email_template src→cid — выполнено (`backend/app/worker/tasks/email_outbox.py::_embed_helpdesk_inline_images`). Сработает и на backfill'нутые URL `/tickets/{id}/inline-media/{name}` (читает файлы из `TKT-{number}/inline/`).
- [x] **Этап 7**: санитизация HTML на приёме (sanitize_html в роутерах) — выполнено (`normalize_message_bodies` → nh3 в `tickets.py` create/my-reply/agent-reply).
- [ ] **Этап 5**: параметризация RichEditor (`outputFormat: 'markdown'|'html'`) — заменён альтернативным подходом (`mdUnsafe.render` на фронте), см. «Решения по ходу» 2026-07-22.
- [x] **Этап 6**: фронтенд-формы (TicketReplyForm, CreateModal, pages, api-client, i18n) — выполнено: `TicketReplyForm` (inline-images через `/tickets/{id}/inline-media`) + `TicketCreateModal` (inline-images через `/draft-attachments` → backfill).
- [x] **Этап 8**: cron очистка orphan draft-attachments — выполнено (`backend/app/worker/tasks/helpdesk.py::cleanup_expired_drafts_task`, cron 5:00 ежедневно, TTL `HELPDESK_DRAFT_TTL_HOURS`=24ч).
- [x] **Этап 9**: документация (helpdesk.md, api-contracts, api-contracts.generated) — обновлены под draft-attachments (2026-07-22).
- [ ] проверки: ruff/mypy/pytest, frontend lint/typecheck/test/i18n

## Грабли / контекст
- `sanitize_html` (nh3): `figure`/`figcaption`/`img` ∈ ALLOWED_TAGS, `img.src` разрешён; `data-type` на figure снимается (ok для display). Относительные `/api/...` URL проходят (доказано ingress).
- `_absolutize_img_src` НЕ трогает `cid:` — src→cid надо делать ДО него (cid пройдёт неизменным).
- news-билдер уже имеет `multipart/related` + `_attach_inline_image` (base64) — переиспользуем паттерн, но helpdesk читает файлы с диска через aiofiles (как обычные вложения).
- `HELPDESK_ATTACHMENT_ALLOWED_MIMES` уже включает png/jpeg/gif/webp (svg проблемен для email — не inline).
- Все мьютирующие endpoints helpdesk коммитят в роутере (outbox-инвариант) — `save_inline_image` только flush.
- Draft-attachment ACL: `uploaded_by_user_id = actor.id`, `message_id IS NULL` → только владелец видит до backfill.

## Архитектура MIME (Этап 4)
```
без inline, без attach:  multipart/alternative (plain, html)           [текущее]
только attach:            multipart/mixed { alt(plain,html), attach... } [текущее]
только inline:            multipart/related { alt(plain,html), cid... }
inline + attach:          multipart/mixed { related{alt,cid...}, attach... }
```
