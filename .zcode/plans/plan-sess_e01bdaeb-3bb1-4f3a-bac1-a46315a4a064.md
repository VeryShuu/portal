## Контекст

Дашборд Overview → панели «Synthetic: login+load» и «Synthetic: длительность».

После задания `PROBE_ADMIN_EMAIL/PASSWORD` (раньше = No data) проба стала запускаться, но возвращает `ok=0` — падает на шаге `login_status_403`. Корневая причина — **архитектурный недочёт, допущенный в коммите `c15ddbb`**: synthetic-проба делает service-to-service login через внутреннее DNS-имя (`frontend:80` на проде / `frontend:5173` в dev), а CSRF-middleware проверяет `Origin` против внешнего `portal_base_url` (`http://portal-test.mage.ru`). Внутреннее имя ≠ внешний домен → 403. **Сломано и на проде тоже** (проверено анализом: дефолт `PROBE_FRONTEND_URL=http://frontend:80` ≠ `portal_base_url`; плюс внешний домен не резолвится из docker-сети).

### Дополнительная локальная находка (не требует кода)
Dev-стек поднят через `docker-compose.dev.yml`, где frontend — Vite на `:5173`, а не nginx на `:80`. Дефолт `PROBE_FRONTEND_URL=http://frontend:80` здесь нерабочий. В `.env` (gitignored, локальный) уже прописано `PROBE_FRONTEND_URL=http://frontend:5173` (временная правка для локальной отладки, не коммитится).

## Решение: Spoof-Origin (вариант A)

Probe получает `portal_base_url` и проставляет его как заголовок `Origin` на login-запросе, проходя CSRF как «настоящий» браузер с правильным доменом. Безопасно: probe уже аутентифицирован shared-секретом (`SCREENSHOT_SERVICE_SECRET`) и живёт в доверенной сети. Cookie остаются host-scoped (подтверждено: все 4 `set_cookie` без `domain=`), а т.к. `page.request` шарит cookie-jar с BrowserContext (документация Playwright), шаг reload автоматически отправит сессию → проба проходит end-to-end.

## Изменения

### 1. `backend/app/worker/tasks/synthetic_probe.py` (worker)
- Импортировать `load_system_settings` (паттерн из `helpdesk.py:314`).
- В payload запроса к `/probe` добавить поле `portal_base_url`: `json={"flow": "login_and_load", "portal_base_url": load_system_settings().portal_base_url}`. Обёрнуто в try/except (fallback — пустая строка), как в других worker-тасках — никогда не ломать cron.
- Обновить docstring (поправить устаревшее имя метрики `portal_synthetic_probe_ok` → `portal_synthetic_probe_up`).

### 2. `screenshot-service/main.py` — `run_probe` (probe handler)
- Извлечь `portal_base_url = body.get("portal_base_url", "")` из JSON-payload.
- На login-POST (строка ~345) добавить `headers={"Origin": portal_base_url}` (только если `portal_base_url` непуст), иначе Playwright синтезирует Origin сам (текущее поведение).
- Логировать отсутствие `portal_base_url` warn-уровнем (диагностика: «worker не передал portal_base_url → login упадёт на CSRF»).
- Файл скомпилирован в образ `screenshot-service` → потребуется `docker compose build --no-cache screenshot-service` + recreate.

### 3. `backend/tests/unit/test_synthetic_probe.py` (тесты)
- В мок-проверках `client.post` обновить ожидаемый payload: добавить `portal_base_url` поле. Мокнуть `load_system_settings` через патч (как сделано для других зависимостей).
- Добавить 1 новый кейс: `portal_base_url` передаётся в payload, asserting the spoofed Origin reaches screenshot-service.
- Существующие 6 тестов остаются зелёными (логика записи в Redis не меняется).

### 4. Документация (пробел из коммита `c15ddbb`)
- `docs/monitoring.md`: добавить секцию про synthetic-мониторинг — что измеряет, env-вары (`PROBE_ADMIN_EMAIL/PASSWORD`, `PROBE_FRONTEND_URL`), что значит No data / ok=0 / ok=1.
- `monitoring/README.md`: краткая ссылка на эту секцию + упомянуть dev-нюанс `PROBE_FRONTEND_URL=http://frontend:5173` для dev-стека.
- `.env.example` (строки 57-64): уточнить комментарий про `PROBE_FRONTEND_URL` — прод `http://frontend:80`, dev `http://frontend:5173`.

## Что НЕ меняется
- CSRF-middleware (`backend/app/middleware/csrf.py`) — без правок. Защита не ослабляется, никакой allowlist доверённых origin'ов не добавляется.
- Имена метрик (`portal_synthetic_probe_up`, `portal_synthetic_probe_duration_seconds`) — без изменений, дашборд уже корректен.
- Контракт `/probe` endpoint расширяется обратно-совместимо (новое опциональное поле `portal_base_url` в payload).

## DoD / Проверка
1. `cd backend && ruff check . && mypy app && pytest tests/unit/test_synthetic_probe.py` — зелёно.
2. `docker compose build --no-cache screenshot-service` + recreate.
3. Прямой вызов `/probe` → `{"ok": true, ...}` (локальный dev-стек).
4. Через ~5 мин (cron): `portal_synthetic_probe_up=1` в Prometheus, панели Grafana показывают `1` (зелёный) и длительность.
5. JSON дашбордов валиден (не трогаются, но проверю).
6. Документация обновлена.

## Замечание для проды
После деплоя: `PROBE_FRONTEND_URL=http://frontend:80` (дефолт верен для prod-compose), `PROBE_ADMIN_EMAIL/PASSWORD` — любой admin-аккаунт local-auth. Код-фикс (spoof Origin через `portal_base_url`) сделает пробу рабочей и на проде без доп. настроек.