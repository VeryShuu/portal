# Модуль «Обучение» (LMS)

> **Когда читать:** любая задача по обучению (курсы, тесты, участники, сертификаты,
> внешние учётки, learn-домен) — до правок кода модуля.
> **Ключевой код:** `./backend/app/api/learning/`, `./backend/app/services/learning/`,
> `./backend/app/models/learning.py`, `./frontend/src/pages/learning/`,
> `./frontend/src/learn/` (отдельная learn-сборка).
> **ADR:** 051. **См. также:** `wip/learning.md` (полное ТЗ и журнал решений),
> `db-schema.md` §«Модуль обучения», `api-contracts.md` §«Модуль обучения».

> Корпоративное обучение: курсы (материалы PDF/ссылки + тесты), назначаемые
> методистом. Две категории обучаемых — сотрудники портала (SSO как обычно) и
> внешние учётки вне Keycloak (публичный контур `learn.<домен>`, отдельная
> сборка фронтенда). Уникальные для портала механизмы: отдельная DB-роль
> `learning_app` с грантами только на `learning_*`, вторая сессия Redis
> (`learning_session:*`), типизированные принципалы.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/learning/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 (`./frontend/src/pages/learning/`); learn-контур — отдельная сборка `dist-learn` (`vite.config.learn.ts`, entry `learn.html`) |
| Воркер | ARQ: `learning_deadlines.py` (напоминания о дедлайне, 07:15), `learning_cleanup.py` (ретеншен кодов входа и реликтов токенов восстановления, 07:45) |
| Хранилище | Локальная ФС `/data/learning/` (материалы, обложки, сертификаты) — исключение «контент модуля» по образцу photos/helpdesk |
| Префикс API | `/api/v1/learning`, `/api/v1/auth/learning` |
| Сессии learner | Redis `learning_session:{id}` + индекс `learning_sessions:{account_id}`; cookie `learning_session` (host-only learn-домена, TTL 8ч sliding) |
| Мастер-флаг | `modules.json → learning`; выключен → 404 на весь контур, включая auth/learning |

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/learning/` | `auth_routes` (вход по коду: login/verify/logout), `me_routes` (прохождение), `meta_routes`, `admin_courses` (курсы/элементы/участники/прогресс/сертификаты), `admin_tests` (вопросы/настройки/импорт), `admin_routes` (внешние учётки, ручная выдача кода), `admin_categories` (справочник категорий), `methodists` |
| Service | `./backend/app/services/learning/` | `courses_service` (CRUD, зачисление, прогресс), `tests_service` (замок/попытки), `accounts_service`, `account_import` (xlsx), `sessions` (learner-Redis), `categories_service`, `emails` (все письма модуля), `certificates`, `covers`, `question_import`, `progress_export`, `for_all_staff`, `participant` |
| Model | `./backend/app/models/learning.py` | 13 таблиц `learning_*` (см. `db-schema.md`) |
| Schema | `./backend/app/schemas/learning.py` | Pydantic-схемы |
| Frontend | `./frontend/src/pages/learning/`, `./frontend/src/components/learning/` | `LearningPage` (реюз в обоих контурах), `LearnerCoursePage`, админка `LearningAdminPage` (вкладки Курсы/Учётки/Категории/Методисты) |
| Queries | `./frontend/src/queries/learning.ts`, api-клиент `./frontend/src/api/learning.ts` | TanStack Query |

## 3. Модель данных

Полная схема — `db-schema.md` §«Модуль обучения» (миграции 101–114). Ключевое:

- XOR-участник во всём: `user_id` XOR `learning_account_id` (participants,
  progress, attempts, certificates) — CHECK «ровно один».
- Passwordless (миграции 113–114): паролей у внешних учёток нет — вход по
  одноразовому коду из письма; `learning_login_codes` — коды (SHA-256 хэш,
  TTL, attempts, used_at). Парольные колонки и таблица
  `learning_password_resets` дропнуты миграцией 114 (на проде внешних учёток
  до этого не создавали, переходное окно не понадобилось).
- Soft-delete везде; исключение участника — soft (история попыток сохраняется);
  попытки — факты без soft-delete (сброс = физическое удаление).
- Курсы: `deadline_at` (+`deadline_notified_at` на зачислении), `category_id`
  (ссылка на справочник `learning_course_categories`), `for_all_staff`
  (обязательный курс «для всех сотрудников»).
- Элементы курса `type ∈ (material, test, section)`; `description` — rich-text
  (Markdown, sanitize на записи). Разделы не участвуют в прогрессе.
- Тесты: `time_limit_minutes` (таймер попытки, серверный контроль submit).

## 4. Модель прав

- **Методист** (= админ модуля): таблица `learning_admins` (паттерн
  `helpdesk_agents`), зависимость `require_learning_admin`; права на все курсы.
  Глобальный `admin` — суперсет. Назначение — только глобальным админом
  (`GET/POST/DELETE /learning/admins`).
- **Участник**: сотрудник (портальная сессия) или learner-cookie; принципалы
  типизированы — `CurrentPortalUser` / `CurrentLearner` /
  `CurrentLearningParticipant`. Learner-cookie на портал-эндпоинтах → 401 и
  наоборот (юнит-тест изоляции).
- Доступ к курсу = зачисление (или `for_all_staff` для сотрудников); не участник /
  черновик / чужая попытка — одинаковый 404 (анти-перечисление).

## 5. REST API

Полные контракты — `api-contracts.md` §«Модуль обучения». Группы:
`auth/learning/*` (публичные, жёсткие rate-limits), `learning/meta`,
`learning/me/*` (прохождение, оба типа участников), `learning/admin/*`
(методист: курсы/элементы/тесты/участники/прогресс/экспорт/учётки/категории),
`learning/admins` (только глобальный админ).

## 6. Специфика и грабли

- **DB-изоляция (§10.8):** learning-роуты ходят через отдельный пул
  `LearningSessionLocal` при заданном `LEARNING_DB_PASSWORD` (обязателен на
  проде). Роль `learning_app` имеет гранты только на `learning_*` + INSERT и
  SELECT(id) `email_outbox`.
  **ГЛАВНЫЙ ГРАБЛЬ:** гранты миграции 102 — табличные, на **новые** таблицы не
  действуют. Каждая новая `learning_*`-таблица обязана GRANT-ить роль в своей же
  миграции. Инцидент 2026-09-03: миграция 109 дала на `learning_course_categories`
  только SELECT → POST /learning/admin/categories падал 500 на контуре с
  паролем роли; исправлено миграцией 112. Резолв личности сотрудника
  (`get_staff_identity`) — только на основном движке, на границе роутера.
- **Письма** (`emails.py`, outbox `kind=learning`, в транзакции операции):
  строители возвращают `(subject, body_text, body_html)` и **обязаны заполнять
  HTML-часть** — SMTP-отправитель кладёт её в multipart/alternative всегда, и
  клиенты, предпочитающие HTML (Outlook), показывают пустое письмо (прод-кейс
  2026-09-03; гард `if body_html` в отправителе — страховка). Код входа и
  одноразовые токены живут только в письме — не в логах/аудите/API.
- **Passwordless-вход (миграция 113):** внешние учётки без паролей. Шаг 1 —
  `POST /auth/learning/login {email}` (всегда `{"ok": true}` — анти-enumeration,
  письмо только существующей активной учётке), шаг 2 —
  `POST /auth/learning/verify {email, code}` → сессия. Код: 6 цифр, TTL
  `learning_code_ttl_minutes` (10 мин), максимум `learning_code_max_attempts`
  (5) неверных вводов, одноразовый (FOR UPDATE + re-check, паттерн старых
  токенов), в БД только SHA-256; новый запрос гасит предыдущий код. Запасной
  путь «письмо не дошло» — `POST /learning/admin/accounts/{id}/login-code`
  (ручная выдача, plaintext только в ответе админского API, аудит
  `learning.login_code_issued`). Block учётки гасит неиспользованные коды.
- **Publish-gate:** опубликовать курс можно, только если у каждого материала есть
  ссылка или PDF и у каждого теста ≥1 вопрос с вариантами; инвариант держится и
  после публикации (row-lock курса; пустая заготовка в опубликованный курс — 409).
- **Замок теста (§15):** тест с попытками (в т.ч. начатыми) не правится и не
  удаляется — только копией; сериализация правки и старта попытки —
  `SELECT … FOR UPDATE` строки `learning_tests`.
- **Попытки:** лимит по отправленным; брошенные клеймятся abandoned лениво
  (24ч или истечение таймера); правильные ответы не покидают сервис; результат —
  «последний», не «лучший».
- **for_all_staff:** доступ виртуальный (проверяется на лету), строки участников
  материализуются при включении флага и после каждого Keycloak-синка
  (`worker/tasks/news.py`); письма при массовом покрытии не шлются
  (`enroll_participant(..., notify=False)`).
- **Категории:** плоский упорядоченный справочник, управляет методист; soft-delete
  отвязывает курсы в той же транзакции.
- **Сертификаты:** ленивая выдача при первом запросе за пройденный курс
  (screenshot-service `render_pdf`, недоступен → 503); методист может выпустить
  сам; повторные запросы отдают сохранённый PDF.
- **Learn-контур:** отдельная сборка `dist-learn` (`check:learn-static` в CI —
  в статике нет портал-чанков/tiptap); nginx-allowlist публичного контура —
  только `auth/learning`, `learning/me`, `= learning/meta`; CSP/видео-origin'ы
  learn берёт из `GET /learning/meta`, портал — из bootstrap.
- **Видео-плеер:** iframe разрешённых origin'ов (`system.json →
  video_iframe_origins`, ADR-052) рендерится сразу; конвертация ссылок
  (PeerTube/YouTube/RuTube/VK/Vimeo) — `utils/videoEmbed.ts`.

## Безопасность

Passwordless: паролей у внешних учёток нет (миграции 113–114, парольные
колонки и таблица токенов дропнуты). Rate-limits: login/verify — IP 5/15м +
email-хэш 10/15м + nginx-зона `learning_auth`; перебор кода закрыт лимитом
попыток (5 неверных вводов убивают код); анти-enumeration — одинаковый ответ
login (всегда ok) и verify (единый 400) независимо от существования учётки;
коды — только SHA-256 хэш, TTL 10 мин, одноразовые (FOR UPDATE + re-check);
block учётки инвалидирует все сессии и неиспользованные коды. Логи —
structlog c redact-процессорами, без PII/секретов.

## События аудита

Все admin-мутации — `push_audit_event(...)` с `resource_type` `learning_*`:
`learning.category_{created,updated,deleted}`, `learning.categories_reordered`,
`learning.certificate_issued`, `learning.attempts_reset`,
`learning.questions_imported`, `learning.participants_bulk_enrolled`,
`learning.login`, `learning.login_code_issued`,
назначение/снятие методиста и др.
(реестр — `app/services/audit_events.py`).

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_learning_*.py` | письма, категории, таймер, дедлайны, обложки, сертификаты, импорт вопросов, сессии |
| Integration | `./backend/tests/integration/test_learning_*.py` | флоу попыток, db-role изоляция (`test_learning_db_role.py`, testcontainers), bulk-enroll, дедлайны, сертификат, участник-детализация |
| Frontend | `./frontend/tests/unit/learning-*.spec.ts`, `learn-*.spec.ts` | страницы learner/админки, api-мэппинг, реактивность queries |
| E2E | `./frontend/tests/e2e/learn-visual.spec.ts`, проект `learn` (E2E_LEARN=1) | визуальные 28 сценариев learn-сборки; флоу внешнего обучаемого |

## Связанные документы

- `wip/learning.md` — полное ТЗ, журнал решений, прод-чеклист ввода
- `db-schema.md`, `api-contracts.md`, `roles-matrix.md`
- `email.md` (outbox-паттерн), `adr.md` (ADR-051, ADR-052)
