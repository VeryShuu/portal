# Фича: Email Cc в helpdesk — «ответить всем»

## Цель
Заявитель присылает заявку по почте и ставит в копию (Cc) других сотрудников. Поддержка
должна видеть всех адресатов заявки и уметь ответить всем сразу (Cc в исходящем письме
агента). В веб-версии создания заявки Cc нет (как и сказал заказчик) — флоу только
email-inbound → email-outbound.

## Решения по ходу
- 2026-07-22: Cc хранится на уровне **сообщения** (`helpdesk_messages.cc` JSONB), а не
  тикета. Каждое письмо имеет свой Cc — это точно отражает email-семантику и даёт
  историю «когда кого добавили». Денормализация в `helpdesk_tickets` была бы источником
  stale-данных → «ответили не тем».
- 2026-07-22: Участники тикета «в сборе» (`participants`) **не хранятся** в БД —
  собираются в рантайме агрегацией `requester_email ∪ cc(всех сообщений) ∪
  author_email(всех сообщений)` в сериализаторе карточки. По образцу
  `build_thread_history`.
- 2026-07-22: Cc-скоп — только агент при ответе. Заявитель через веб-форму Cc не
  указывает (веб-flow без Cc, как постановка задачи).
- 2026-07-22: Reply-all UX — чекбокс «Ответить всем» + редактируемый список Cc
  (pre-fill из участников, можно убрать/добавить). Не жёсткое «всем», чтобы можно было
  исключить уволенного/неуместного получателя.
- 2026-07-22: Отдельной таблицы участников (как Zammad `ticket_watchers`) НЕТ —
  за рамками постановки задачи.

## Чеклист (DoD)
- [x] миграция 083 (zero-downtime, nullable колонка)
- [x] модель: колонка `cc` в `HelpdeskMessage`
- [x] threading: `extract_cc(msg)` helper
- [x] ingress: парсинг Cc в `_parse_inbound_headers` + проброс в message
- [x] messages service: `cc` параметр в `add_agent_reply`
- [x] outbound: `cc` параметр в `enqueue_reply_outbound` → payload
- [x] worker email_outbox: заголовок `Cc` в `_apply_helpdesk_headers`
- [x] schemas: `ParticipantOut`, поля в `MessageOut`/`TicketAgentOut`
- [x] serializer `_common.py`: participants-агрегация + cc в message_to_out
- [x] router tickets.py: Form-поле `cc` в `add_agent_message`
- [x] тесты backend (35 новых + 777 helpdesk-regression): extract_cc, outbound
      Cc-header + CRLF-sanitization, participants-агрегация, _normalize_cc_emails
- [x] frontend: api-типы + `TicketParticipantsCard` + чекбокс в `TicketReplyForm`
      + бейдж в ленте (19 frontend-тестов pass, всего 2124)
- [x] i18n (ru + en, 2142 ключа OK)
- [x] lint + typecheck + tests pass (backend ruff/mypy clean, frontend clean)
- [x] обновлены docs/ (helpdesk.md §1 возможности, §3 колонка, §4 API, §8 in/outbound, §15 миграция)
- [x] openapi.json перегенерирован (MessageOut.cc, TicketAgentOut.participants, ParticipantOut)

## Грабли / контекст
- Inbound Cc — attacker-controlled (любой внешний email): только храним и показываем.
  Отправка по ним идёт **исключительно** когда агент явным образом включил чекбокс
  «Ответить всем» и отправил форму — человек в петле подтверждает получателей.
- Outbound Cc проходит тот же `_sanitize_header_field`, что и `To`/`Subject`
  (`outbound.py:38`) — защита от CRLF/Bcc-injection уже есть, просто применяется к
  новому полю.
- Из inbound Cc выкидываем `support_address` (иначе петля: агент ответит всем,
  письмо вернётся в ящик поддержки → новый тикет/дубль).
- Threading не страдает: `In-Reply-To`/`References`/`Reply-To` без изменений; ответ
  Cc-получателя по Reply-All вернётся в тот же тикет по references.
- `participants` НЕ отдаём в requester-view (`TicketOut`) — PII-минимизация: заявителю
  чужие Cc-адреса показывать незачем. Только в `TicketAgentOut`.
- Бейдж Cc в ленте (`TicketMessageList`) — только в agent-mode (агент видит, кому ушёл
  конкретный ответ; заявителю свои же Cc видеть ни к чему).
