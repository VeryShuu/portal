# Architecture Decision Records — Архив

> Корпоративный интранет-портал

Этот файл содержит ADR со статусом «Заменено», «Superseded» или «зарезервирован/удалён».  
Активные ADR находятся в [`./docs/adr.md`](./adr.md).

---

## Индекс архивных ADR

- [ADR-002: Nextcloud — impersonation через Bearer JWT (Вариант B)](#adr-002-nextcloud-impersonation-через-bearer-jwt-вариант-b)
- [ADR-013: CSRF — SameSite=Strict + Origin/Referer (не Double Submit Cookie)](#adr-013-csrf-samesitestrict-originreferer-не-double-submit-cookie)
- [ADR-026: (зарезервирован/удалён)](#adr-026-зарезервированудалён)
- [ADR-029: (зарезервирован/удалён)](#adr-029-зарезервированудалён)

---

## ADR-002: Nextcloud — impersonation через Bearer JWT (Вариант B)

**Статус:** ~~Принято~~ → **Заменено ADR-032** (апрель 2026)

Исходный Вариант B (impersonation per-user JWT) отклонён после анализа требований: файловый модуль портала хранит **общие корпоративные файлы**, а не личные файлы пользователей. Impersonation не применим — нет смысла проксировать файлы от имени конкретного пользователя, если все работают с единым деревом. См. ADR-032.

---

## ADR-013: CSRF — SameSite=Strict + Origin/Referer (не Double Submit Cookie)

**Статус:** Superseded by ADR-025

> Дополнен ADR-025 (Double Submit Cookie добавлен)

**Контекст:**
Токены хранятся в HTTPOnly cookies, SPA делает запросы через `fetch`.

**Решение:** `SameSite=Strict` на всех cookies + проверка `Origin`/`Referer` заголовков на бэкенде.

**Альтернатива:**
- Double Submit Cookie → отклонено: требует не-HttpOnly CSRF-cookie, которую JS читает и шлёт в заголовке. Усложняет код без значимого прироста безопасности при `SameSite=Strict`.

**Покрытие:** `SameSite=Strict` закрывает 99% CSRF. Origin/Referer check — дополнительный слой.

---

## ADR-026: (зарезервирован/удалён)

> Этот номер ADR не используется. Зарезервирован или удалён в ходе истории документа.

---

## ADR-029: (зарезервирован/удалён)

> Этот номер ADR не используется. Зарезервирован или удалён в ходе истории документа.

---

