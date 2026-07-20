# Фикс: обрезка email-подписи в MAX-уведомлениях helpdesk

## Корень бага (диагноз подтверждён кодом)

`_extract_bodies` (`backend/app/services/helpdesk/ingress.py:814-862`) режет подпись **только из HTML**:
```python
if html is not None:
    html = strip_email_signature(html)          # ← чисто
if plain is None and html:                       # ← баг: только если plain пустой
    plain = strip_quoted_reply(html_to_plain(sanitize_html(html)))
```
Для `multipart/alternative` (доминирующий формат Outlook — plain+html копии в одном письме) `plain` не пустой → в БД уходит оригинальный plain **с подписью**. Дальше каскад: `HelpdeskMessage.body_text` / `HelpdeskTicket.description` содержат подпись → `notify_ticket_created_max:718` → `_truncate_preview(body_text)` → подпись в MAX. Браузер работает, т.к. рендерит `body_html` (он почищен).

Эталон уже есть в коде: `normalize_message_bodies` (`messages.py:34`) использует паттерн «HTML = источник истины, plain = дериват». Баг = расхождение с собственным эталоном в одном месте.

## Подход: два слоя (как выбрал пользователь)

### Слой 1 — корень в `_extract_bodies` (ingress.py)

Привести к эталону `normalize_message_bodies`: если `html` есть — `plain` **всегда** деривируется из очищенного HTML (подпись уже снята). Минимальный diff:

```python
if html is not None:
    html = strip_email_signature(html)

# HTML — источник истины: если html есть, plain всегда деривируется из него
# (как normalize_message_bodies). Подпись уже снята выше → в деривате plain
# её тоже не будет — единый инвариант для всех даунстримов (MAX/email/web).
# Раньше для multipart/alternative plain уходил в БД с подписью → MAX (баг 20.07).
if html is not None:
    html = sanitize_html(html)
    # strip_quoted_reply повторно: html-цитата могла оставить «On … wrote:» после снятия тегов
    plain = strip_quoted_reply(html_to_plain(html))
return (plain or "").strip() or "(пустое сообщение)", html
```

Поведенческое изменение (осознанное): для новых email-тикетов `body_text`/`description` становятся без подписи. Это желаемое — раньше подпись была артефактом. **Миграция не нужна**: старые записи не трогаем.

### Слой 2 — defence-in-depth в `notify_ticket_created_max` (notifications.py:715-718)

Даже если `body_text` в БД содержит подпись (legacy-записи до фикса, или edge-кейсы), превью берётся из `body_html` (если есть), который пере-чистится идемпотентной `strip_email_signature`:

```python
raw_html = getattr(first_message, "body_html", None)
if raw_html:
    # html уже без подписи после ingress-фикса; strip_email_signature идемпотентен
    body_text = html_to_plain(sanitize_html(strip_email_signature(raw_html)))
else:
    body_text = getattr(first_message, "body_text", None) or ""
body_preview = _truncate_preview(body_text)
```

Импорты `strip_email_signature`/`sanitize_html`/`html_to_plain` добавить в шапку `notifications.py`. fallback на `body_text` — для legacy без html и для web-сабмита без TipTap.

## Тесты (характеризация ПЕРЕД фиксом, по AGENTS.md)

Текущее покрытие: `_extract_bodies` — **0 тестов**, `multipart/alternative` — не конструируется, MAX (22 теста) ни разу не подаёт подпись.

**Порядок:** сначала пишу тесты (FAIL на текущем коде → докажут баг) → фикс → PASS.

### A. `backend/tests/unit/test_helpdesk_ingress_extract.py` (+новые кейсы)
- `test_extract_bodies_multipart_alternative_strips_signature_from_plain` — multipart/alternative (plain+html с подписью) → оба тела без подписи. **FAIL сейчас.**
- `test_extract_bodies_multipart_alternative_without_signature_preserved` — контроль: без подписи оба тела сохраняются.
- `test_extract_bodies_html_only_with_signature` — html-only (как сейчас, smoke).
- `test_extract_bodies_plain_only_no_html` — plain-only без html-маркеров → без изменений.
- `test_extract_bodies_empty_both` — оба пусты → `("(пустое сообщение)", None)`.

### B. `backend/tests/unit/test_helpdesk_notifications.py` → `TestNotifyTicketCreatedMax` (+новые)
- `test_signature_excluded_from_preview_when_html_present` — `first_message(body_text="...подпись...", body_html="<...Mage_Ru.png...>")` → текст MAX без подписи. **FAIL сейчас.**
- `test_preview_falls_back_to_body_text_when_no_html` — `html=None, body_text="..."` → превью из body_text (контроль: существующие 22 теста остаются зелёными).

### C. Регрессионный — реальный кейс из баг-репорта
Использует `REAL_OUTLOOK_HTML` из `test_helpdesk_email_signature.py` (можно вынести в общий хелпер или дублировать inline), упакованный в multipart/alternative RFC822-письмо → end-to-end через `_extract_bodies` → ассерты отсутствия подписи в обоих полях.

## DoD (Definition of Done)

- [ ] Слой 1: `_extract_bodies` фикс + обновлённый docstring/комментарии
- [ ] Слой 2: `notify_ticket_created_max` defence-in-depth + импорты в notifications.py
- [ ] Тесты A (5 новых в ingress_extract)
- [ ] Тесты B (2 новых в MAX) + проверка что 22 существующих зелёные
- [ ] Тест C (регрессионный)
- [ ] `pytest tests/unit/test_helpdesk_email_signature.py tests/unit/test_helpdesk_notifications.py tests/unit/test_helpdesk_ingress_extract.py tests/unit/test_helpdesk_message_normalize.py` — зелёные
- [ ] `ruff check . && mypy app` — чисто
- [ ] Handoff в `docs/wip/` (если есть активный helpdesk-план — обновить)

## Скоуп / что НЕ трогаем

- ❌ Миграции (нулевые — старые записи в БД не правим)
- ❌ API-контракты (не меняются)
- ❌ `normalize_message_bodies` (эталон, не объединяем с `_extract_bodies` — разные входы: web TipTap vs email)
- ❌ `_truncate_preview` (вне скоупа)
- ❌ Web-сабмит path (он уже идёт через `normalize_message_bodies` — подписи там нет)
- ❌ Email-нотификации агентам (`_message_body_html` уже режет подпись — не страдают)

## Риски (осознанные)

1. **Для multipart/alternative теряем plain-специфичное содержимое**, если html менее информативен. Для Outlook — несвойственно (клиент генерит обе копии из одного текста). Trade-off за консистентность.
2. **Существующие 22 теста MAX** подают `_first_message(text=..., html=None)` → при defence-in-depth fallback на `body_text` → остаются зелёными. Проверю прогоном.
3. **Email-нотификации** (`notify_ticket_created_email`) уже работали корректно (через `_message_body_html`) — слой 1 только укрепляет (description теперь тоже чистый).