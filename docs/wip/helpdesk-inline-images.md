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

## Чеклист (DoD)
- [ ] **Этап 1**: модель HelpdeskAttachment (`is_inline`, `content_id`) + миграция 077
- [ ] **Этап 2**: backend inline-media эндпоинт + `save_inline_image`
- [ ] **Этап 3**: backfill draft-attachments при отправке (create_ticket / add_my_message / add_agent_message)
- [ ] **Этап 4**: MIME-билдер CID-embed (`multipart/related`) + outbound payload + email_template src→cid
- [ ] **Этап 7**: санитизация HTML на приёме (sanitize_html в роутерах)
- [ ] **Этап 5**: параметризация RichEditor (`outputFormat: 'markdown'|'html'`)
- [ ] **Этап 6**: фронтенд-формы (TicketReplyForm, CreateModal, pages, api-client, i18n)
- [ ] **Этап 8**: cron очистка orphan draft-attachments
- [ ] **Этап 9**: документация (helpdesk.md, db-schema.md, api-contracts)
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
