# Database Schema

> **Когда читать:** новая таблица/поле, миграция, изменение схемы.
> **Ключевой код:** `app/models/`, `backend/migrations/versions/`.
> **ADR:** 019, 030, 031, 032.

> **Auto-generated companion:** `./docs/db-schema.generated.md` — produced by `./backend/scripts/generate_db_schema_doc.py`.  
> Run `cd backend && python3 -m scripts.generate_db_schema_doc --output ../docs/db-schema.generated.md` to refresh.  
> This curated file contains narrative context and migration history; the generated file reflects the current model definitions.

## Оглавление

- [Инициализация расширений и FTS](#инициализация-расширений-и-fts)
- [Таблица: users](#таблица-users)
- [Таблица: user_attribute_mappings (миграция 026)](#таблица-user_attribute_mappings-миграция-026)
- [База знаний (KB)](#база-знаний-kb)
- [База знаний — ACL (миграция 009_kb_acl)](#база-знаний--acl-миграция-009_kb_acl)
- [База знаний — Медиа и вложения (миграция 010_kb_markdown)](#база-знаний--медиа-и-вложения-миграция-010_kb_markdown)
- [Новости](#новости)
- [Ярлыки сервисов](#ярлыки-сервисов)
- [Закладки](#закладки)
- [Уведомления](#уведомления)
- [Audit Log (партиционированная)](#audit-log-партиционированная)
- [Idempotency Keys](#idempotency-keys)
- [Email outbox](#email-outbox-миграция-051)
- [Схема связей (ERD)](#схема-связей-erd)
- [Файловое хранилище оформления (Branding — вне БД)](#файловое-хранилище-оформления-branding--вне-бд)
- [Фотогалерея (миграция 014_photos)](#фотогалерея-миграция-014_photos)
- [Справочники объектов (миграция 064_object_directories)](#справочники-объектов-миграция-064_object_directories)
- [Справочник получателей рассылки (миграция 071)](#справочник-получателей-рассылки-миграция-071_mailing_recipients)
- [Helpdesk (миграции 075–084)](#helpdesk-миграции-075084)
- [MAX-messenger / messenger_outbox (миграция 081)](#max-messenger--messenger_outbox-миграция-081)
- [Миграции (Alembic) — zero-downtime правила](#миграции-alembic--zero-downtime-правила)
- [§3.6 Файловый модуль (Phase 5 — миграция 020)](#36-файловый-модуль-phase-5--миграция-020)
- [Индексные миграции (021–024)](#индексные-миграции-021024)
- [Миграции 025–038 (май 2026)](#миграции-025038-май-2026)
- [Миграции 039–084 (июнь–июль 2026)](#миграции-039084-июньиюль-2026)

---

> Корпоративный интранет-портал
> PostgreSQL 16
> Последнее обновление: август 2026 (v1.17 — миграции 001..090: к v1.16 добавлены
> **090** `erp_sync_delete_after_fetch` (`erp_sync_settings.delete_after_fetch` —
> удаление писем из общего ящика после успешного импорта),
> **089** `move_erp_imap_to_email_settings` (вынос IMAP-приёмки во вкладку Email, ADR-048),
> **088** `erp_sync_mail_filter_and_poll` (`erp_sync_settings.poll_enabled` +
> 3 поля фильтрации писем: subject/sender/attachment — для общего ящика).
> Ранее — **085** `notifications_cleanup_index` (индекс для очистки старых уведомлений),
> **086** `helpdesk_smtp_settings` (собственный SMTP-контур helpdesk),
> **087** `users_birth_date_gender_erp_sync` (`users.birth_date`/`gender` + таблицы
> `erp_sync_runs`/`erp_sync_settings` для импорта дней рождения и пола из ERP).
> **082** `helpdesk_draft_attachments` (вложения в черновиках ответа),
> **083** `helpdesk_messages.cc` (JSONB, копия Cc), **084** drop `helpdesk_messages.visibility`,
> **helpdesk** (075–080: тикеты, сообщения, вложения, агенты, mailbox/digest-settings,
> FTS tsvector+GIN, marker-таблица `helpdesk_ticket_reads`), **messenger_outbox +
> helpdesk_max_bot_settings** (081, оповещения о заявках в MAX-messenger),
> **mailing_recipients** (071), service_links.show_on_home/kb_url (070/074),
> news cover_focal_x/y/zoom (072/073). Helpdesk/MAX-таблицы детально описаны в
> [`./helpdesk.md`](./helpdesk.md) §3 — здесь только краткая выжимка + перекрёстные
> ссылки, чтобы не дублировать источник истины. ERP-sync-таблицы — см. конец файла.)
> Соответствие миграциям: `001_initial_users` → `002_news` → `003_links_bookmarks` → `004_local_auth` → `005_news_cover_image` → `006_news_gallery_attachments` → `007_news_fts_consolidate` → `008_kb` → `009_kb_acl` → `010_kb_markdown` → `011_news_fts_hunspell` → `012_notifications` → `013_audit_log` → `014_photos` → `015_photo_share_tokens` → `016_photo_folders_fs_path` → `017_photo_zip_jobs` → `018_photo_tags` → `019_photo_folder_share_tokens` → `020_files` → `021_news_title_trgm` → `022_fk_indexes` → `023_keycloak_groups` → `024_trgm_indexes` → `025_user_attributes` → `026_user_attribute_mappings` → `027_news_cover_focal_point` → `028_users_soft_delete` → `029_news_categories_array` → `030_email_unique_lower` → `031_photo_folders_fk_restrict` → `032_fk_set_null_notifications_bookmarks` → `033_audit_log_metadata_gin_index` → `034_kb_articles_section_restrict` → `035_photo_folders_path_unique` → `036_kb_sections_soft_delete` → `037_users_email_partial_unique` → `038_file_items` → `039_news_cover_meta` → `040_add_feedback` → `041_add_feedback_attachments` → `042_file_folder_inherit_permissions` → `043_news_previous_status` → `044_staff_directory_order` → `045_soft_delete_partial_indexes` → `046_kb_users_partial_indexes` → `047_user_attribute_mapping_full_name_source` → `048_meetings` → `049_meeting_rooms_add_email` → `050_drop_meetings_audit_log` → `051_email_outbox` → `052_kb_section_inherit_permissions` → `053_add_news_polls` → `054_news_poll_multi_questions` → `055_meeting_rooms_add_kind` → `056_photo_folder_perm_unique_subject_type` → `057_photo_folder_storage_kind` → `058_kb_article_version_body_required` → `059_kb_sections_parent_slug_unique` → `060_photos_blurhash` → `061_kb_articles_list_index` → `062_backfill_users_directory_active_index` → `063_file_shares` → `064_object_directories` → `065_directory_entry_folder` → `066_file_items_unique_active_name` → `067_backfill_folder_creator_manager_perm` → `068_news_likes` → `069_news_comments` → `070_service_links_show_on_home` → `071_mailing_recipients` → `072_news_cover_focal_xy` → `073_news_cover_focal_zoom` → `074_add_kb_url_to_service_links` → `075_add_helpdesk` → `076_add_helpdesk_digest_settings` → `077_add_helpdesk_attachments_inline_columns` → `078_add_helpdesk_fts` → `079_drop_helpdesk_resolved` → `080_add_helpdesk_ticket_reads` → `081_add_messenger_outbox_and_max_bot_settings` → `082_add_helpdesk_draft_attachments` → `083_add_helpdesk_messages_cc` → `084_drop_helpdesk_message_visibility` → `085_notifications_cleanup_index` → `086_add_helpdesk_smtp_settings` → `087_add_users_birth_date_gender_erp_sync` → `088_add_erp_sync_mail_filter_and_poll` → `089_move_erp_imap_to_email_settings` → `090_add_erp_sync_delete_after_fetch`

Все таблицы с полными определениями, индексами и комментариями.

---

## Инициализация расширений и FTS

```sql
-- backend/migrations/init.sql
-- Выполняется при первом старте PostgreSQL контейнера

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- FTS с hunspell_ru (лемматизация лучше Snowball)
-- Требует: apt install postgresql-16-hunspell + словари в $SHAREDIR/tsearch_data/
CREATE TEXT SEARCH DICTIONARY russian_hunspell_dict (
    TEMPLATE  = ispell,
    DictFile  = russian,
    AffFile   = russian,
    StopWords = russian
);
CREATE TEXT SEARCH CONFIGURATION russian_hunspell (COPY = russian);
ALTER TEXT SEARCH CONFIGURATION russian_hunspell
    ALTER MAPPING FOR hword, hword_part, word
    TO russian_hunspell_dict, russian_stem;
```

---

## Таблица: users

```sql
CREATE TABLE users (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Источник аутентификации: 'keycloak' (по SSO) или 'local' (email + bcrypt).
    -- Для 'local' keycloak_id = NULL и password_hash NOT NULL.
    -- Для 'keycloak' password_hash = NULL и keycloak_id NOT NULL.
    auth_source      VARCHAR(20)  NOT NULL DEFAULT 'keycloak'
                         CHECK (auth_source IN ('keycloak', 'local')),
    keycloak_id      VARCHAR(36)  UNIQUE,            -- sub из Keycloak JWT (NULL для local)
    password_hash    VARCHAR(255),                   -- bcrypt (NULL для keycloak)
    email            VARCHAR(255) UNIQUE NOT NULL,
    full_name        VARCHAR(255) NOT NULL,
    department       VARCHAR(255),                   -- из JWT claim "department" (для keycloak)
    position         VARCHAR(255),                   -- из JWT claim "job_title"  (для keycloak)
    phone            VARCHAR(50),                    -- из JWT claim "phone"      (для keycloak)
    role             VARCHAR(20)  NOT NULL DEFAULT 'reader'
                         CHECK (role IN ('reader', 'editor', 'admin')),
    avatar_url       VARCHAR(512),                   -- /media/avatars/<user_id>.<ext>
    presence_status  VARCHAR(20)  NOT NULL DEFAULT 'office'
                         CHECK (presence_status IN ('office', 'remote', 'vacation')),
    notify_email     BOOLEAN      NOT NULL DEFAULT TRUE,
    notify_inapp     BOOLEAN      NOT NULL DEFAULT TRUE,
    lang             VARCHAR(5)   NOT NULL DEFAULT 'ru'
                         CHECK (lang IN ('ru', 'en')),
    -- Персональные настройки пользователя (скрытые ярлыки и т.п.)
    -- Структура: {"hidden_link_ids": ["uuid1", "uuid2"]}
    preferences      JSONB        NOT NULL DEFAULT '{}',
    -- Список Keycloak-групп пользователя (синхронизируется из JWT claim "groups")
    -- Используется KB ACL для subject_type='group'. Миграция 023.
    keycloak_groups  TEXT[]       NOT NULL DEFAULT '{}',
    -- Дополнительные атрибуты из Keycloak JWT claims (dept, phone и др.) — JSONB. Миграция 025.
    -- Пример: {"department": "IT", "phone": "+7 999 123-45-67"}
    attributes       JSONB        NOT NULL DEFAULT '{}',
    -- Soft-delete пользователей. NULL = активен. Миграция 028.
    deleted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at    TIMESTAMPTZ,
    -- ERP-синхронизация (миграция 087): дата рождения и пол из ERP-выгрузки.
    -- Источник истины — ERP (отчёт 1С), каждый импорт перетирает значения.
    -- Видны всем авторизованным в карточке /staff (аналогично position/phone).
    -- Admin может редактировать вручную до следующего импорта.
    birth_date       DATE,
    gender           VARCHAR(10)
                         CHECK (gender IS NULL OR gender IN ('male', 'female'))
);

CREATE INDEX idx_users_keycloak        ON users(keycloak_id) WHERE keycloak_id IS NOT NULL;
-- Миграции 030 + 037: case-insensitive уникальность email (LOWER(email)) + partial WHERE deleted_at IS NULL.
-- Миграция 037 переименовала индекс из idx_users_email_ci в idx_users_email_ci_active,
-- сохранив условие partial — это позволяет повторно использовать email после soft-delete.
CREATE UNIQUE INDEX idx_users_email_ci_active ON users (LOWER(email)) WHERE deleted_at IS NULL;
CREATE INDEX        idx_users_email_lower ON users (LOWER(email));
-- Partial index для быстрого поиска активных пользователей (миграция 028)
CREATE INDEX        idx_users_active      ON users (email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_dept            ON users(department);
CREATE INDEX idx_users_source          ON users(auth_source);
-- GIN-индексы для ILIKE / pg_trgm поиска (миграция 024)
CREATE INDEX idx_users_full_name_trgm  ON users USING GIN (full_name gin_trgm_ops);
CREATE INDEX idx_users_department_trgm ON users USING GIN (department gin_trgm_ops);
```

> Отдельная таблица `user_profiles` и `user_preferences` не создаются — все доп. поля слиты в `users`. Персональные настройки (скрытые ярлыки) хранятся в `preferences JSONB`.
>
> **Account-linking:** при логине через Keycloak пользователь с тем же `email`, у которого `keycloak_id IS NULL`, переводится с `auth_source = 'local'` на `'keycloak'` (см. `app/api/auth.py::_upsert_user`). Роль при этом сохраняется (важно для bootstrap-admin), событие пишется в логи как `auth.account_linked`.
>
> **Soft-delete (миграция 028):** пользователи удаляются через `deleted_at = NOW()` (не `DELETE`). FK-поля в других таблицах используют `ON DELETE SET NULL`. Уникальность email — по `LOWER(email) WHERE deleted_at IS NULL`, что позволяет переиспользовать адрес после удаления.
>
> **Атрибуты (миграция 025/026):** `attributes JSONB` хранит произвольные атрибуты пользователя (синхронизируются из Keycloak). Конфигурация отображаемых атрибутов — в таблице `user_attribute_mappings`.

---

## Таблица: user_attribute_mappings (миграция 026)

Справочник атрибутов профиля пользователя — определяет, какие ключи из `users.attributes` отображаются в UI и с какими метками.

```sql
CREATE TABLE user_attribute_mappings (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    attr_key            VARCHAR(255) NOT NULL UNIQUE,          -- ключ в users.attributes JSONB (например "phone")
    label_ru            VARCHAR(255) NOT NULL,                 -- метка на русском ("Телефон")
    label_en            VARCHAR(255),                          -- метка на английском (NULL = использовать ru)
    sort_order          INTEGER      NOT NULL DEFAULT 0,       -- порядок в профиле
    enabled             BOOLEAN      NOT NULL DEFAULT TRUE,    -- false = не показывать в UI
    -- Миграция 047: если TRUE — значение атрибута используется как users.full_name (только один активный)
    is_full_name_source BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_attribute_mappings_attr_key UNIQUE (attr_key)
);

CREATE INDEX idx_user_attribute_mappings_sort ON user_attribute_mappings(sort_order);
```

**Использование:** управляется через admin UI (`AdminPage → UsersTab`). При синхронизации из Keycloak все полученные JWT claims записываются в `attributes`; UI отображает только те, для которых `enabled = TRUE`.

---

## База знаний (KB)

> Реализовано в Phase 3 (миграция `008_kb`). Фронтенд: `KbListPage.vue`, `KbArticlePage.vue`, `KbArticleFormPage.vue`, `KbSectionTree.vue`.

### kb_sections

```sql
CREATE TABLE kb_sections (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id           UUID         REFERENCES kb_sections(id)
                            ON DELETE RESTRICT,            -- CASCADE опасен: снесёт всё дерево
    title               VARCHAR(255) NOT NULL,
    slug                VARCHAR(255) NOT NULL,
    description         TEXT,
    sort_order          INTEGER      NOT NULL DEFAULT 0,   -- P2-33: единое имя (sort_order, не order_index)
    -- Миграция 052: наследование прав KB-раздела от родителя (аналогично kb_articles)
    inherit_permissions BOOLEAN      NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,                       -- миграция 036: soft-delete, NULL = активен
    created_by          UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kb_sections_parent_slug UNIQUE (parent_id, slug)
);

CREATE INDEX idx_kb_sections_parent ON kb_sections(parent_id);
-- Partial index для быстрого обхода активного дерева (миграция 036)
CREATE INDEX idx_kb_sections_deleted ON kb_sections(deleted_at) WHERE deleted_at IS NULL;
```

> Дерево реализовано как adjacency list. Хлебные крошки строятся рекурсивным CTE.
> Удаление раздела с дочерними элементами запрещено на уровне БД.
> **Soft-delete (миграция 036):** обычное удаление выставляет `deleted_at = NOW()`; запросы по умолчанию фильтруют `WHERE deleted_at IS NULL`.
> Явное полное удаление со всем содержимым — только через `DELETE /kb/sections/{id}?force=true` (admin).

---

### kb_articles

```sql
CREATE TABLE kb_articles (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Миграция 034: ON DELETE RESTRICT (было SET NULL). Удаление раздела запрещено при наличии статей.
    -- Приложение перед удалением раздела: active articles → 409; soft-deleted → section_id = NULL.
    section_id     UUID         REFERENCES kb_sections(id) ON DELETE RESTRICT,
    title          VARCHAR(500) NOT NULL,
    body           TEXT         NOT NULL DEFAULT '',   -- Markdown (CommonMark + GFM)
    -- P2-32: поля draft_title/draft_body/draft_saved_at — ЗАПЛАНИРОВАНО v2,
    -- в текущих миграциях отсутствуют (черновики реализованы через status='draft').
    -- FTS: GENERATED ALWAYS — обновляется автоматически при изменении body/title
    body_tsvector  TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian_hunspell',
            coalesce(title, '') || ' ' || coalesce(body, ''))
    ) STORED,
    status         VARCHAR(20)  NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'published', 'archived')),
    created_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    updated_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    -- Оптимистичная блокировка: клиент отправляет version, UPDATE WHERE version=expected
    -- При несовпадении → 409 Conflict
    version        INTEGER      NOT NULL DEFAULT 1,
    published_at   TIMESTAMPTZ,
    view_count     INTEGER      NOT NULL DEFAULT 0,
    -- Soft delete: удалённые статьи не отображаются, admin может восстановить
    deleted_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kb_articles_fts     ON kb_articles USING GIN(body_tsvector);
CREATE INDEX idx_kb_articles_trgm    ON kb_articles USING GIN(title gin_trgm_ops);
CREATE INDEX idx_kb_articles_section ON kb_articles(section_id);
-- Partial index — исключает soft-deleted записи из большинства запросов
CREATE INDEX idx_kb_articles_active  ON kb_articles(section_id, deleted_at)
    WHERE deleted_at IS NULL;
```

---

### kb_article_versions

```sql
CREATE TABLE kb_article_versions (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id     UUID         NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    version        INTEGER      NOT NULL,    -- P2-40: единое имя поля 'version' (не version_number)
    title          VARCHAR(500),
    body           TEXT         NOT NULL,    -- KB-ref 1.5: обязательное, чтобы откат к версии с пустым телом не подставлял текущее
    changed_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    change_comment VARCHAR(500),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, version)
);

CREATE INDEX idx_kb_versions_article ON kb_article_versions(article_id, version DESC);
```

---

### kb_tags / kb_article_tags

```sql
CREATE TABLE kb_tags (
    id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name  VARCHAR(100) UNIQUE NOT NULL,
    slug  VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE kb_article_tags (
    article_id UUID NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    tag_id     UUID NOT NULL REFERENCES kb_tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);
```

---

### kb_article_comments

```sql
CREATE TABLE kb_article_comments (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID         NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    author_id  UUID         REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT         NOT NULL,
    -- Soft delete для комментариев (показываем "[удалено]" вместо удаления)
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kb_comments_article ON kb_article_comments(article_id, created_at);
```

---

### kb_suggestions

```sql
-- Предложения правок от readers/editors. Редактор рассматривает через POST /kb/suggestions/{id}/review
CREATE TABLE kb_suggestions (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id  UUID         NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    author_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
    body        TEXT         NOT NULL,     -- предлагаемый исправленный текст статьи
    comment     VARCHAR(500),             -- пояснение к правке
    status      VARCHAR(20)  NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by UUID         REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kb_suggestions_article ON kb_suggestions(article_id, status);
```

---

### kb_article_feedback

```sql
-- «Статья полезна?» — одна запись на пару (article, user). UPSERT меняет оценку.
CREATE TABLE kb_article_feedback (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID    NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    user_id    UUID    NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    is_helpful BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, user_id)
);

CREATE INDEX idx_kb_feedback_article ON kb_article_feedback(article_id);
```

> Обе таблицы добавлены миграцией `008_kb` (апрель 2026, Phase 3).

---

## База знаний — ACL (миграция 009_kb_acl)

> Реализовано в Phase 3.5. Отдельная от ролей портала система прав с наследованием по дереву разделов.

### kb_section_permissions

```sql
CREATE TABLE kb_section_permissions (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id   UUID         NOT NULL REFERENCES kb_sections(id) ON DELETE CASCADE,
    -- 'user' = конкретный пользователь по keycloak_id; 'group' = группа Keycloak по group_id
    subject_type VARCHAR(10)  NOT NULL CHECK (subject_type IN ('user', 'group')),
    subject_id   VARCHAR(255) NOT NULL,   -- keycloak_id пользователя или group_id
    subject_name VARCHAR(255) NOT NULL,   -- имя для отображения (денормализовано)
    permission   VARCHAR(20)  NOT NULL CHECK (permission IN ('viewer', 'editor', 'manager')),
    granted_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(section_id, subject_id)         -- один субъект — одно право на раздел
);

CREATE INDEX idx_kb_sec_perm_section ON kb_section_permissions(section_id, subject_id);
```

---

### kb_article_permissions

```sql
CREATE TABLE kb_article_permissions (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id   UUID         NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    subject_type VARCHAR(10)  NOT NULL CHECK (subject_type IN ('user', 'group')),
    subject_id   VARCHAR(255) NOT NULL,
    subject_name VARCHAR(255) NOT NULL,
    permission   VARCHAR(20)  NOT NULL CHECK (permission IN ('viewer', 'editor', 'manager')),
    granted_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, subject_id)
);

CREATE INDEX idx_kb_art_perm_article ON kb_article_permissions(article_id, subject_id);
```

> Эта же миграция (`009_kb_acl`) добавляет поле в `kb_articles`:
>
> ```sql
> ALTER TABLE kb_articles ADD COLUMN inherit_permissions BOOLEAN NOT NULL DEFAULT TRUE;
> ```
>
> `inherit_permissions = TRUE` (по умолчанию) — статья наследует права от раздела рекурсивно вверх.
> `inherit_permissions = FALSE` — используются только `kb_article_permissions` этой статьи.

**Алгоритм проверки (реализован в пакете `./backend/app/services/kb_acl/`):**

> Пакет разбит на модули: `_common.py` (константы, `_cache_key`, ранжирование), `resolve.py` (`resolve_section_permission`, `resolve_article_permission`), `visibility.py` (`filter_accessible_sections`, `filter_accessible_articles`), `invalidation.py` (`invalidate_section_cache` — рекурсивно по поддереву, `invalidate_article_cache`), `batch.py` (`batch_resolve_sections`).

```
Для статьи:
  1. portal admin (users.role = 'admin')  → полный доступ (manager)
  2. articles.created_by = текущий user  → manager
  3. inherit_permissions = FALSE          → смотрим kb_article_permissions
  4. inherit_permissions = TRUE           → рекурсивно вверх по kb_section_permissions
  5. Не найдено                           → 403

Для раздела:
  1. portal admin                         → manager
  2. sections.created_by = текущий user  → manager
  3. Смотрим kb_section_permissions       → best-match среди user + groups
  4. Рекурсия к parent_id               → вверх до root
  5. Не найдено                           → 403
```

**Кэш Redis:** ключ `kb_acl:{user_id}:section|article:{id}` — TTL 5 минут. Инвалидируется при изменении прав (паттерн `kb_acl:*:section:{id}` + все статьи).

---

## База знаний — Медиа и вложения (миграция 010_kb_markdown)

> Реализовано в Phase 3.5. Обеспечивает работу редактора в режиме Markdown + вставку изображений + прикрепление файлов.

### kb_article_files

```sql
CREATE TABLE kb_article_files (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id    UUID         NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    filename      VARCHAR(500) NOT NULL,   -- UUID-имя на диске (без расширения, чтобы не угадать тип)
    original_name VARCHAR(500) NOT NULL,   -- оригинальное имя файла для скачивания (RFC 5987)
    size_bytes    BIGINT,
    mime_type     VARCHAR(255),
    uploaded_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kb_article_files_article ON kb_article_files(article_id);
```

> Файлы хранятся в `/data/kb/files/{article_id}/{uuid}` (без расширения).
> Медиа-изображения (вставка в тело через `![alt](url)`) хранятся в `/data/kb/media/{article_id}/{uuid}.{ext}`.
> Ограничения размера: `KB_MEDIA_MAX_SIZE_MB` и `KB_ATTACHMENT_MAX_SIZE_MB` в `.env`.
> Скачивание: `GET /kb/files/{article_id}/{filename}` с `Content-Disposition: attachment; filename*=UTF-8''...` (RFC 5987).

---

## Новости

### news

```sql
CREATE TABLE news (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title              VARCHAR(500) NOT NULL,
    body               TEXT         NOT NULL DEFAULT '',   -- Markdown
    -- P2-32: draft_title/draft_body/draft_saved_at — ЗАПЛАНИРОВАНО v2,
    -- в текущих миграциях отсутствуют (черновики реализованы через status='draft' + PUT /news/{id}/draft).
    body_tsvector      TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian_hunspell',
            coalesce(title, '') || ' ' || coalesce(body, ''))
    ) STORED,
    -- Миграция 029: category (VARCHAR) заменён на categories (TEXT[]) для поддержки нескольких категорий
    categories         TEXT[]       NOT NULL DEFAULT '{}', -- ['company', 'it', 'hr', 'projects']
    status             VARCHAR(20)  NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'published', 'archived')),
    is_pinned          BOOLEAN      NOT NULL DEFAULT FALSE,
    -- Таргетирование: NULL = все; непустой массив = только указанные
    target_departments TEXT[],                             -- ['IT', 'HR']
    target_roles       TEXT[],                             -- ['editor', 'admin']
    cover_image           VARCHAR(500),                       -- /media/news/{filename} (local volume)
    -- Миграция 027 (enum top/center/bottom) → 072: точка фокуса обложки в процентах для CSS object-position
    cover_focal_x         SMALLINT,                           -- 0..100, NULL = 50 (центр)
    cover_focal_y         SMALLINT,                           -- 0..100, NULL = 50 (центр)
    -- Миграция 073: приближение обложки (CSS transform: scale вокруг точки фокуса)
    cover_focal_zoom      SMALLINT,                           -- 100..300, NULL = 100 (без приближения)
    -- Миграция 039: доминантный цвет обложки (hex, e.g. "#d8262c") и список доступных размеров (пикс.)
    cover_dominant_color  VARCHAR(7),
    cover_variants        INTEGER[],
    author_id             UUID         REFERENCES users(id) ON DELETE SET NULL,
    -- P2-32: updated_by — ЗАПЛАНИРОВАНО v2, в текущих миграциях не используется (см. updated_at + news_versions.editor_id).
    publish_at         TIMESTAMPTZ,                        -- отложенная публикация
    archive_at         TIMESTAMPTZ,                        -- автоархивация
    published_at       TIMESTAMPTZ,                        -- дата публикации (NULL = черновик)
    current_version    INTEGER      NOT NULL DEFAULT 1,    -- текущая версия контента
    view_count         INTEGER      NOT NULL DEFAULT 0,
    -- Миграция 068/069: денормализованные счётчики реакций/комментариев
    like_count         INTEGER      NOT NULL DEFAULT 0,    -- ♥ (news_likes, миграция 068)
    comment_count      INTEGER      NOT NULL DEFAULT 0,    -- 💬 (news_comments, миграция 069)
    -- Soft delete
    deleted_at         TIMESTAMPTZ,
    -- Миграция 043: статус до последней смены (для восстановления из архива/черновика)
    previous_status    VARCHAR(20),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_news_fts    ON news USING GIN(body_tsvector);
CREATE INDEX idx_news_trgm   ON news USING GIN(title gin_trgm_ops);
CREATE INDEX idx_news_active ON news(status, publish_at, deleted_at)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_news_pinned ON news(is_pinned, publish_at DESC)
    WHERE deleted_at IS NULL AND status = 'published';
```

---

### news_gallery_images (миграция 006)

```sql
CREATE TABLE news_gallery_images (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id       UUID         NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    filename      VARCHAR(500) NOT NULL,            -- <uuid>.<ext>, хранится в /data/news_media/<news_id>/gallery/
    original_name VARCHAR(500) NOT NULL,            -- оригинальное имя файла для скачивания
    sort_order    INTEGER      NOT NULL DEFAULT 0,  -- порядок в галерее (drag-and-drop)
    file_size     INTEGER,                           -- в байтах
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gallery_news_id_sort ON news_gallery_images(news_id, sort_order);
```

> Файлы хранятся локально в `/data/news_media/<news_id>/gallery/<uuid>.<ext>`.
> Ограничение размера — `NEWS_ATTACHMENT_MAX_SIZE_MB` (env, по умолчанию 50 MB).
> Допустимые MIME: `image/jpeg`, `image/png`, `image/webp`, `image/gif`.

---

### news_attachments (миграция 006)

```sql
CREATE TABLE news_attachments (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id       UUID         NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    filename      VARCHAR(500) NOT NULL,            -- UUID (без расширения), storage-имя
    original_name VARCHAR(500) NOT NULL,            -- имя для скачивания (RFC 5987)
    mime_type     VARCHAR(255),                     -- определённый при загрузке Content-Type
    file_size     INTEGER,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_attachments_news_id ON news_attachments(news_id);
```

> Файлы: `/data/news_media/<news_id>/attachments/<uuid>`.
> Ограничение — `NEWS_ATTACHMENT_MAX_SIZE_MB` (env, 50 MB).
> Скачивание идёт через `GET /news/{id}/attachments/{att_id}/download` с `Content-Disposition` RFC 5987 для кириллицы.

---

### news_versions

```sql
CREATE TABLE news_versions (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id    UUID         NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    version    INTEGER      NOT NULL,    -- P2-40: единое имя 'version' (не version_number)
    title      VARCHAR(500) NOT NULL,
    body       TEXT         NOT NULL DEFAULT '',
    editor_id  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(news_id, version)
);

CREATE INDEX idx_news_versions_news_id ON news_versions(news_id);
```

---

### news_likes (миграция 068)

```sql
CREATE TABLE news_likes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id    UUID        NOT NULL REFERENCES news(id)  ON DELETE CASCADE,
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_news_likes_news_user UNIQUE (news_id, user_id)
);

CREATE INDEX idx_news_likes_user ON news_likes(user_id);
```

> Реакция «лайк» (только ♥, без дизлайка). Уникальность `(news_id, user_id)` —
> один пользователь = один лайк. Денормализованный счётчик `news.like_count`
> поддерживается в той же транзакции (`GREATEST(0, count-1)` на unlike). Поле
> `liked_by_me` в выдаче — LEFT JOIN по `current_user.id`, без N+1.

---

### news_comments (миграция 069)

```sql
CREATE TABLE news_comments (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id    UUID        NOT NULL REFERENCES news(id)  ON DELETE CASCADE,
    author_id  UUID        REFERENCES users(id) ON DELETE SET NULL,  -- nullable
    body       TEXT        NOT NULL,
    deleted_at TIMESTAMPTZ,                                          -- soft delete
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_news_comments_news   ON news_comments(news_id, created_at);
CREATE INDEX idx_news_comments_active ON news_comments(news_id)
    WHERE deleted_at IS NULL;
```

> Плоские (без вложенности) комментарии — зеркало `kb_article_comments`, плюс
> inline-редактирование (`PATCH`) и денормализованный счётчик
> `news.comment_count`. Soft delete (`deleted_at`) — удалённый отдаётся как
> `is_deleted` без тела. Edit — только автор; delete — автор или admin.

---

## Ярлыки сервисов

### service_links

```sql
CREATE TABLE service_links (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(200) NOT NULL,
    url          VARCHAR(2048) NOT NULL,
    icon_url     VARCHAR(2048),
    description  VARCHAR(500),                     -- P2-37
    category     VARCHAR(100),                     -- 'dev', 'finance', 'hr', 'common', 'comm'
    sort_order   INTEGER      NOT NULL DEFAULT 0,  -- P2-33: единое имя (sort_order)
    supports_sso BOOLEAN      NOT NULL DEFAULT FALSE,  -- пробрасывать ли id_token_hint
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    show_on_home BOOLEAN      NOT NULL DEFAULT FALSE,  -- 070: показывать в виджете «Сервисы» на главной
    kb_url       VARCHAR(2048),                        -- 074: опциональная ссылка на KB-статью с инструкцией к сервису
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,  -- кто создал ссылку
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()  -- P2-37
);

CREATE INDEX idx_service_links_active ON service_links(category, sort_order)
    WHERE is_active = TRUE;
```

---

## Закладки

### bookmarks

```sql
CREATE TABLE bookmarks (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Миграция 032: ON DELETE SET NULL (было CASCADE) — закладки сохраняются после удаления пользователя
    user_id        UUID         REFERENCES users(id) ON DELETE SET NULL,
    title          VARCHAR(300) NOT NULL,
    url            VARCHAR(2048) NOT NULL,
    resource_type  VARCHAR(50),             -- 'article', 'news', 'file', 'link'
    resource_id    VARCHAR(100),            -- UUID или Nextcloud path
    group_name     VARCHAR(100),            -- пользовательская группа закладок
    sort_order     INTEGER      NOT NULL DEFAULT 0,  -- P2-33: единое имя (sort_order)
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bookmarks_user_id    ON bookmarks(user_id);
CREATE INDEX idx_bookmarks_user_sort  ON bookmarks(user_id, sort_order);
CREATE INDEX idx_bookmarks_resource   ON bookmarks(resource_type, resource_id);
```

---

## Уведомления

> ✅ **Статус на апрель 2026:** Миграция `012_notifications` применена, Phase 4 завершена.

### notifications

```sql
CREATE TABLE notifications (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Миграция 032: ON DELETE SET NULL (было CASCADE) — история уведомлений сохраняется после удаления пользователя
    user_id    UUID         REFERENCES users(id) ON DELETE SET NULL,
    type       VARCHAR(80)  NOT NULL,    -- 'new_news', 'article_updated', 'file_shared', 'suggest_approved'
    title      VARCHAR(500) NOT NULL,
    body       TEXT,
    link       VARCHAR(1000),
    is_read    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    read_at    TIMESTAMPTZ
);

CREATE INDEX idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
```

---

## Audit Log (партиционированная)

```sql
-- Партиционированная таблица — native PG16, без pg_partman
CREATE TABLE audit_log (
    id             BIGSERIAL,
    event_type     VARCHAR(50)  NOT NULL,
    user_id        UUID,    -- P2-39: НЕТ FK (партиция + retention 12 мес → допустимы "висячие" записи)
    user_email     VARCHAR(255),
    resource_type  VARCHAR(50),
    resource_id    VARCHAR(255),
    resource_title VARCHAR(500),
    ip_address     INET,
    user_agent     TEXT,
    metadata       JSONB        NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Партиции создаются скриптом backend/scripts/create_audit_partitions.py
-- Запускается при деплое и раз в месяц ARQ-задачей create_next_audit_partition
-- Пример:
CREATE TABLE audit_log_2026_04 PARTITION OF audit_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

-- Индексы создаются на каждой партиции (или на parent — PG16 наследует на children)
CREATE INDEX idx_audit_user_time        ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_event_time       ON audit_log(event_type, created_at DESC);
CREATE INDEX idx_audit_resource         ON audit_log(resource_type, resource_id);
-- Миграция 033: GIN на metadata для фильтрации по JSONB полям (metadata->>'resource_type' и т.п.)
-- CREATE INDEX CONCURRENTLY не поддерживается на партиционированных таблицах (PG ограничение)
CREATE INDEX idx_audit_log_metadata_gin ON audit_log USING gin(metadata jsonb_path_ops);
```

**Retention:** 12 месяцев онлайн. ARQ-задача `drop_old_audit_partition` ежемесячно удаляет партицию старше 12 месяцев (`DROP TABLE audit_log_YYYY_MM`).

**Запись:** fire-and-forget через `BackgroundTasks` → Redis list `audit_queue` → ARQ worker batch INSERT каждые 1–2 сек.

**Отслеживаемые `event_type`:**

| event_type | Описание |
|-----------|---------|
| `login` / `logout` | Вход/выход |
| `view_article` / `view_news` | Просмотр |
| `create_article` / `update_article` / `delete_article` | CRUD статей |
| `create_news` / `update_news` / `delete_news` | CRUD новостей |
| `open_file` / `download_file` / `edit_file` | Файловые операции |
| `upload_file` / `create_share_link` | Загрузка, шаринг |
| `search` | Поиск (запрос + количество результатов) |
| `admin_action` | Изменение ролей, управление ярлыками |
| `sync_users` | Ручная синхронизация пользователей (admin) |
| `kb.permission_grant` | Выдача права на раздел или статью KB |
| `kb.permission_revoke` | Отзыв права на раздел или статью KB |
| `kb.inherit_changed` | Изменение `inherit_permissions` на статье |
| `kb.media_upload` | Загрузка изображения в тело статьи |
| `kb.file_upload` | Загрузка вложения к статье |
| `kb.file_download` | Скачивание вложения статьи |
| `kb.export_md` | Экспорт статьи в Markdown |
| `kb.export_zip` | Экспорт раздела или всей KB в ZIP |
| `kb.import` | Импорт Markdown-файла или Obsidian vault |

---

## Idempotency Keys

```sql
CREATE TABLE idempotency_keys (
    key         VARCHAR(255) PRIMARY KEY,
    -- Хранится только {"id": "uuid"} — не полный response body (memory leak при StreamingResponse)
    response    JSONB        NOT NULL DEFAULT '{}',
    status_code INTEGER      NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- TTL: ARQ-задача cleanup_idempotency_keys удаляет записи старше 24 часов
CREATE INDEX idx_idempotency_created ON idempotency_keys(created_at);
```

---

## Email outbox (миграция 051)

> Полное описание инфраструктуры — в [`./email.md`](./email.md). Здесь — только
> схема таблицы. Producer'ы — meetings/news/kb/helpdesk (через `enqueue_outbox_email(...)`).

Transactional outbox для всех исходящих писем. Все producer'ы пишут в эту
таблицу **в той же транзакции**, что и бизнес-операция (AGENTS.md инвариант).
Отправка — cron `process_email_outbox` (claim `FOR UPDATE SKIP LOCKED`, retry/backoff/DLQ).

```sql
CREATE TABLE email_outbox (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kind                  VARCHAR(64)  NOT NULL,         -- 'generic' | 'news' | 'meeting' | 'kb' | 'helpdesk' | …
    to_email              VARCHAR(320) NOT NULL,
    subject               VARCHAR(998) NOT NULL,
    body_html             TEXT         NOT NULL DEFAULT '',
    body_text             TEXT,                          -- опциональный plain-text
    payload               JSONB        NOT NULL DEFAULT '{}',  -- структурированные доп-данные
    status                VARCHAR(16)  NOT NULL DEFAULT 'PENDING'
                              CHECK (status IN ('PENDING','SENDING','SENT','FAILED','DLQ','CANCELLED')),
    attempts              INTEGER      NOT NULL DEFAULT 0,
    max_attempts          INTEGER      NOT NULL DEFAULT 6,
    next_attempt_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_error            TEXT,
    last_error_type       VARCHAR(128),
    last_error_class      VARCHAR(16),                   -- 'transient' | 'permanent'
    related_resource_type VARCHAR(64),                   -- бизнес-сущность ('news', 'helpdesk_ticket', …)
    related_resource_id   UUID,
    created_by_user_id    UUID,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    sent_at               TIMESTAMPTZ
);

CREATE INDEX ix_email_outbox_pending ON email_outbox (next_attempt_at) WHERE status = 'PENDING';
CREATE INDEX ix_email_outbox_stale   ON email_outbox (updated_at)      WHERE status = 'SENDING';
```

`process_email_outbox` классифицирует SMTP-ошибки: 5xx → `permanent` (DLQ сразу),
4xx/transient → `transient` (retry с экспоненциальным backoff до `max_attempts`).

---

## Схема связей (ERD)

```
users ──────────────────────────────────────────────────────────────────────────┐
  │ 1                                                                            │
  │ ├─ n kb_articles (created_by)                                                │
  │ ├─ n news (created_by)                                                       │
  │ ├─ n bookmarks                                                               │
  │ ├─ n notifications                                                           │
  │ ├─ n kb_section_permissions (granted_by)   [mig 009]                         │
  │ ├─ n kb_article_permissions (granted_by)   [mig 009]                         │
  │ ├─ n kb_article_files (uploaded_by)        [mig 010]                         │
  │ └─ n audit_log (user_id — БЕЗ FK, см. P2-39)                                 │
                                                                                 │
kb_sections ──(self-ref parent_id, RESTRICT)──► kb_sections                      │
  │ 1                                                                            │
  ├─ n kb_section_permissions (CASCADE)  [mig 009]                               │
  └─ n kb_articles (SET NULL on section delete)                                  │
       │ 1                                                                       │
       ├─ n kb_article_versions   (CASCADE)                                      │
       ├─ n kb_article_tags       (CASCADE) ──► kb_tags                          │
       ├─ n kb_article_comments   (CASCADE)                                      │
       ├─ n kb_suggestions        (CASCADE)                                      │
       ├─ n kb_article_feedback   (CASCADE)                                      │
       ├─ n kb_article_permissions (CASCADE)  [mig 009]                          │
       └─ n kb_article_files      (CASCADE)  [mig 010]                           │
                                                                                 │
news ──┬─► n news_versions        (CASCADE)                                      │
       ├─► n news_gallery_images  (CASCADE)  [mig 006]                           │
       └─► n news_attachments     (CASCADE)  [mig 006]                           │
                                                                                 │
service_links (standalone)                                                        │
bookmarks → users (CASCADE), resource_* (no FK, polymorphic)                    │
notifications → users (CASCADE)                                                 │
audit_log (partitioned, user_id без FK для производительности)                   │
idempotency_keys (standalone, TTL 24h)                                           │
```

---

## Файловое хранилище оформления (Branding — вне БД)

> Настройки оформления **не хранятся в PostgreSQL** (ADR-019). Используется файловый store на Docker volume.

```
Volume: ./upload_data/branding:/data/branding  (backend + worker)

/data/branding/
├── settings.json        ← BrandingSettings (portal_name, accent_color, banner_*, ...)
├── logo.{png|jpg|svg|webp}    ← загружаемый логотип (только один файл, старый удаляется)
├── favicon.{ico|png|svg|...}  ← загружаемый favicon
└── login-bg.{png|jpg|svg|webp} ← фон страницы входа
```

**settings.json** (пример):
```json
{
  "portal_name": "Корпоративный портал",
  "portal_tagline": "",
  "accent_color": "#d8262c",
  "welcome_subtitle": "",
  "banner_enabled": false,
  "banner_text": "",
  "banner_type": "info",
  "banner_expires_at": null
}
```

**Бэкап:** `upload_data/branding/` должен входить в инфраструктурный backup-сценарий вместе с `base_data/postgres/` и остальным `upload_data/` (см. `docs/deploy.md` §7).

---

## Фотогалерея (миграция 014_photos)

> Собственный модуль фотогалереи — иерархия папок с per-folder ACL, локальное хранение оригиналов и WebP/AVIF-thumbnail'ов (200 / 400 / 600 / 1000 / 1600). Отдача файлов — Nginx `X-Accel-Redirect`. См. ADR-030 / ADR-031.

### Таблица: photo_folders

```sql
CREATE TABLE photo_folders (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Миграция 031: ON DELETE RESTRICT (было CASCADE) — физическое удаление родителя запрещено при наличии дочерних папок
    parent_id       UUID         REFERENCES photo_folders(id) ON DELETE RESTRICT,
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(255) NOT NULL,                  -- ASCII (NFKD), уникален в пределах parent_id
    path            VARCHAR(2000) NOT NULL DEFAULT '',      -- материализованный путь slug-ов через '/' (для URL)
    fs_path         VARCHAR(2000) NOT NULL DEFAULT '',      -- материализованный Unicode-путь для зеркала на ФС (миграция 016)
    description     TEXT,
    cover_photo_id  UUID,                                   -- FK добавляется позже (см. ниже)
    created_by      UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                            -- soft-delete
    -- Миграция 057: режим хранения папки
    storage_kind    VARCHAR(20)  NOT NULL DEFAULT 'originals',  -- 'originals' (обычные папки) | 'import' (drop-зона import_scan)
    storage_root    VARCHAR(500),                               -- альтернативный корень ФС для kind='import'
    CONSTRAINT uq_photo_folders_parent_slug UNIQUE (parent_id, slug),
    CONSTRAINT ck_photo_folders_storage_kind CHECK (storage_kind IN ('originals', 'import'))
);
CREATE INDEX idx_photo_folders_parent ON photo_folders(parent_id);
-- Миграция 035: UNIQUE partial index на path (WHERE deleted_at IS NULL) — заменяет обычный индекс
-- Предотвращает дублирование path при конкурентных rename-операциях
CREATE UNIQUE INDEX uq_photo_folders_path ON photo_folders(path) WHERE deleted_at IS NULL;

-- FK на photos добавляется после создания таблицы photos:
ALTER TABLE photo_folders
    ADD CONSTRAINT fk_photo_folders_cover
    FOREIGN KEY (cover_photo_id) REFERENCES photos(id) ON DELETE SET NULL;
```

**Поведение:**
- Корневые папки — только `admin` (см. roles-matrix). Дочерние — пользователь с `manager` на родителе.
- `created_by` автоматически считается `manager` (override в ACL-сервисе).
- Soft-delete на родителе скрывает поддерево из `GET /photos/folders/tree`, но FK `ON DELETE CASCADE` срабатывает только при жёстком удалении.

---

### Таблица: photo_folder_permissions

```sql
CREATE TABLE photo_folder_permissions (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id     UUID         NOT NULL REFERENCES photo_folders(id) ON DELETE CASCADE,
    subject_type  VARCHAR(10)  NOT NULL CHECK (subject_type IN ('user', 'group')),
    subject_id    VARCHAR(255) NOT NULL,                    -- Keycloak `sub` или group id
    subject_name  VARCHAR(255) NOT NULL,                    -- denormalized для отображения в UI
    permission    VARCHAR(20)  NOT NULL CHECK (permission IN ('viewer', 'uploader', 'manager')),
    granted_by    UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Миграция 056: в UNIQUE добавлен subject_type — один subject_id может иметь раздельные права как user и как group
    CONSTRAINT uq_photo_folder_perm_folder_subject UNIQUE (folder_id, subject_type, subject_id)
);
CREATE INDEX idx_photo_folder_perm_folder  ON photo_folder_permissions(folder_id);
CREATE INDEX idx_photo_folder_perm_subject ON photo_folder_permissions(subject_id);
```

**Алгоритм резолва (`services/photos_acl.py`):**
1. `user.role == 'admin'` → `manager`
2. `folder.created_by == user.id` → `manager`
3. Direct grant в `photo_folder_permissions` (subject_id ∈ {keycloak_id} ∪ keycloak_groups)
4. Рекурсия вверх по `parent_id` (max 20 уровней, max-permission win, ранний выход при `manager`)
5. None → 403

**Кэш:** Redis `photo_acl:{user_id}:{folder_id}:v{N}` TTL 300s (см. `services/acl_base.py:12`). Версия `N` берётся из счётчика `photo_acl_ver:{folder_id}`. Инвалидация — `INCR photo_acl_ver:{folder_id}` (плюс рекурсивный INCR по всем потомкам), старые ключи автоматически «протухают» по TTL. `SCAN+DELETE` используется только в `invalidate_user_cache(redis, user_id)` (вызывается при изменении состава групп пользователя).

---

### Таблица: photos

```sql
CREATE TABLE photos (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id            UUID         NOT NULL REFERENCES photo_folders(id) ON DELETE CASCADE,
    filename             VARCHAR(500) NOT NULL,             -- ASCII-санитированное имя на диске
    original_name        VARCHAR(500) NOT NULL,             -- исходное имя (для Content-Disposition)
    size_bytes           BIGINT       NOT NULL,
    mime_type            VARCHAR(100),
    width                INTEGER,                           -- заполняется ARQ
    height               INTEGER,                           -- заполняется ARQ
    taken_at             TIMESTAMPTZ,                       -- EXIF DateTimeOriginal
    exif                 JSONB,                             -- GPS strip-нут по умолчанию (модуль strip_gps=true)
    description          TEXT,
    inherit_permissions  BOOLEAN      NOT NULL DEFAULT TRUE, -- зарезервировано (per-photo override на будущее)
    processed            BOOLEAN      NOT NULL DEFAULT FALSE, -- true после ARQ-обработки
    -- Миграция 060: blurhash для skeleton-preview до загрузки полного изображения
    blurhash             VARCHAR(64),
    uploaded_by          UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at           TIMESTAMPTZ                        -- soft-delete
);
CREATE INDEX idx_photos_folder_created ON photos(folder_id, created_at DESC);
CREATE INDEX idx_photos_taken_at       ON photos(taken_at DESC NULLS LAST);
```

**Pipeline загрузки:**
1. `POST /photos/folders/{id}/upload` (multipart)
2. Валидация MIME + размера (по настройкам модуля)
3. Сохранение оригинала на ФС → INSERT `photos` (`processed=false`)
4. ARQ enqueue `process_photo_upload(photo_id)`
5. ARQ: Pillow + pillow-heif → WebP q=85 (опционально AVIF) размеры 200/400/600/1000/1600 → парсинг EXIF (strip GPS если включено) → UPDATE `width/height/taken_at/exif/processed=true`
6. `processed=false` фото скрыты из `GET /photos/recent` (виджет)

**Файловая структура:**
```
/data/photos/
├── originals/{fs_path}/{sanitized_filename}              ← оригиналы (X-Accel: /internal/photos-originals/, fs_path = Unicode-зеркало портальных папок)
└── thumbs/{photo_id}/{200|400|600|1000|1600}.{webp|avif}  ← thumbnail'ы (X-Accel: /internal/photos-thumbs/)
```

`fs_path` собирается из `name`'ов всей цепочки папок через `sanitize_folder_name` (NFC + удаление OS-reserved символов `<>:"/\\|?*` и control-байтов; кириллица/пробелы сохраняются). При rename папки на портале выполняется `shutil.move` каталога и каскадный UPDATE `fs_path` всех потомков. X-Accel-Redirect использует `urllib.parse.quote(fs_path, safe='/')` для корректной отдачи Unicode-путей.

**Volumes:**
- `./upload_data/photos/originals` — rw в `backend`/`worker`, `ro` в `nginx`
- `./upload_data/photos/thumbs` — rw в `backend`/`worker`, `ro` в `nginx`

**Бэкап:** `upload_data/photos/originals/` включается в инфраструктурный backup (см. `docs/deploy.md` §7); `upload_data/photos/thumbs/` бэкапить не требуется — регенерируется из оригиналов.

---

### Таблица: photo_share_tokens (миграция 015)

```sql
CREATE TABLE photo_share_tokens (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    photo_id     UUID         NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    token        VARCHAR(64)  NOT NULL UNIQUE,           -- secrets.token_urlsafe(32)
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ,                            -- NULL = бессрочно
    revoked_at   TIMESTAMPTZ                             -- NULL = активен
);
CREATE UNIQUE INDEX idx_photo_share_tokens_token ON photo_share_tokens(token);
CREATE INDEX        idx_photo_share_tokens_photo ON photo_share_tokens(photo_id);
```

**Поведение:**
- Создаётся через `POST /photos/{id}/share` пользователем с правом `uploader+` на папке фото.
- Public endpoints (`GET /photos/public/{token}/...`) возвращают `410 Gone` при `expires_at < now()` и `404 Not Found` при `revoked_at IS NOT NULL` или несуществующем токене.
- Каскад `ON DELETE CASCADE` чистит токены при жёстком удалении фото; soft-delete (`photos.deleted_at`) приводит к `404` от `_resolve_token` (где WHERE `deleted_at IS NULL`).

---

### Таблица: photo_zip_jobs (миграция 017)

```sql
CREATE TABLE photo_zip_jobs (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id    UUID         NOT NULL REFERENCES photo_folders(id) ON DELETE CASCADE,
    user_id      UUID         REFERENCES users(id) ON DELETE SET NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    file_path    VARCHAR(500),                              -- путь к ZIP на диске (временный)
    error        TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ                               -- NULL = не истекает автоматически
);
CREATE INDEX idx_photo_zip_jobs_folder ON photo_zip_jobs(folder_id);
CREATE INDEX idx_photo_zip_jobs_user   ON photo_zip_jobs(user_id);
```

**Использование:** создаётся через `POST /photos/folders/{id}/zip`; ARQ-задача генерирует ZIP и обновляет `status`/`file_path`; файл отдаётся через `GET /photos/zip-jobs/{job_id}/download` и удаляется по TTL.

---

### Таблицы: photo_tags / photo_tag_assignments (миграция 018)

```sql
CREATE TABLE photo_tags (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100) NOT NULL UNIQUE,
    slug       VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE photo_tag_assignments (
    photo_id   UUID  NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    tag_id     UUID  NOT NULL REFERENCES photo_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);
CREATE INDEX idx_pta_photo ON photo_tag_assignments(photo_id);
CREATE INDEX idx_pta_tag   ON photo_tag_assignments(tag_id);
```

**Использование:** теги для фотографий. Облако тегов в боковой панели галереи; фильтрация по тегу. Управление через `GET/POST /photos/tags`, `DELETE /photos/tags/{id}`, `PATCH /photos/{id}/tags`.

---

### Таблица: photo_folder_share_tokens (миграция 019)

```sql
CREATE TABLE photo_folder_share_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id   UUID        NOT NULL REFERENCES photo_folders(id) ON DELETE CASCADE,
    token       VARCHAR(64) NOT NULL,
    created_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,              -- NULL = бессрочно
    revoked_at  TIMESTAMPTZ,              -- NULL = активен
    CONSTRAINT uq_pfst_token UNIQUE (token)
);
CREATE INDEX idx_pfst_folder     ON photo_folder_share_tokens(folder_id);
CREATE INDEX idx_pfst_created_by ON photo_folder_share_tokens(created_by);
```

**Поведение:** создаётся через `POST /photos/folders/{id}/share`; публичные endpoints (`GET /photos/public-folder/{token}/...`) возвращают `410 Gone` при истёкшем `expires_at` и `404` при `revoked_at IS NOT NULL`. Просмотр и отзыв токенов — через `GET /photos/my-shares` / `DELETE /photos/my-shares/folder/{id}`.

---

## Миграции (Alembic) — zero-downtime правила

1. **Новое поле всегда `NULL` сначала** — не `NOT NULL` сразу (лок таблицы)
2. **Затем** деплой кода, который пишет в поле
3. **Затем** бэкфилл + `ALTER COLUMN SET NOT NULL`
4. **Rename** — создать новое поле → писать в оба → читать из нового → удалить старое
5. Запрещены: `ALTER TABLE ... ADD COLUMN ... NOT NULL` без DEFAULT в одной транзакции с данными

```
Порядок деплоя: migration → code → (если нужно) backfill → add constraint
```

---

## §3.6 Файловый модуль (Phase 5 — миграция 020)

### file_folders

Теневое дерево папок портала, отражающее структуру в Nextcloud (под `portal-svc`).

```sql
CREATE TABLE file_folders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id           UUID REFERENCES file_folders(id) ON DELETE RESTRICT,
    name                VARCHAR(500) NOT NULL,
    nc_path             VARCHAR(2000) NOT NULL UNIQUE,  -- путь от корня portal-svc (e.g. "HR/Docs")
    description         TEXT,
    -- Миграция 042: наследование прав от родительской папки
    inherit_permissions BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ  -- soft delete
);

CREATE INDEX idx_file_folders_parent ON file_folders(parent_id);
CREATE INDEX idx_file_folders_nc_path ON file_folders(nc_path);
CREATE INDEX idx_file_folders_active ON file_folders(parent_id, name)
    WHERE deleted_at IS NULL;
```

### file_folder_permissions

ACL папок файлового модуля. Права наследуются вверх по дереву (`parent_id`).

```sql
CREATE TABLE file_folder_permissions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id    UUID NOT NULL REFERENCES file_folders(id) ON DELETE CASCADE,
    subject_type VARCHAR(10) NOT NULL CHECK (subject_type IN ('user', 'group')),
    subject_id   VARCHAR(255) NOT NULL,  -- keycloak_id пользователя или group_id
    subject_name VARCHAR(255) NOT NULL,  -- человекочитаемое имя
    permission   VARCHAR(20) NOT NULL CHECK (permission IN ('viewer', 'editor', 'manager')),
    granted_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_file_folder_perm_folder_subject UNIQUE (folder_id, subject_id)
);

CREATE INDEX idx_file_folder_perm_folder ON file_folder_permissions(folder_id);
CREATE INDEX idx_file_folder_perm_subject ON file_folder_permissions(subject_id);
```

**Уровни прав:**
- `viewer` — просмотр списка и скачивание файлов
- `editor` — также загрузка файлов и создание подпапок
- `manager` — также управление правами, переименование и удаление папки

### file_items (миграция 038)

Файлы внутри папок файлового модуля. Каждая запись соответствует одному файлу в Nextcloud. `nc_path` уникален среди активных (не удалённых) файлов.

```sql
CREATE TABLE file_items (
    id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id   UUID          NOT NULL REFERENCES file_folders(id) ON DELETE CASCADE,
    nc_path     VARCHAR(2000) NOT NULL,
    name        VARCHAR(500)  NOT NULL,
    size_bytes  BIGINT        NOT NULL DEFAULT 0,
    mime_type   VARCHAR(255),
    uploaded_by UUID          REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);

CREATE INDEX idx_file_items_folder_active ON file_items(folder_id)
    WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX idx_file_items_nc_path_active ON file_items(nc_path)
    WHERE deleted_at IS NULL;
```

---

### file_shares (миграция 063)

Пофайловый шеринг (ADR-032, см. [`sharing.md`](./sharing.md)). Файл адресуется парой `(folder_id, filename)`; `nc_path` хранится денормализованно (`folder.nc_path + '/' + filename`) для персистентности и admin-реестра. На файл выдаётся только уровень `viewer`/`editor` (`manager` не выдаётся). Повторная выдача на тот же `(folder_id, filename, subject_id)` = upsert. Отзыв мягкий — через `revoked_at`.

```sql
CREATE TABLE file_shares (
    id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id    UUID          NOT NULL REFERENCES file_folders(id) ON DELETE CASCADE,
    filename     VARCHAR(500)  NOT NULL,
    nc_path      VARCHAR(2000) NOT NULL,  -- денормализованный folder.nc_path + '/' + filename
    subject_type VARCHAR(10)   NOT NULL,  -- 'user' | 'group'
    subject_id   VARCHAR(255)  NOT NULL,
    subject_name VARCHAR(255)  NOT NULL,
    permission   VARCHAR(20)   NOT NULL,  -- 'viewer' | 'editor'
    shared_by    UUID          REFERENCES users(id) ON DELETE SET NULL,
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ   NOT NULL,
    revoked_at   TIMESTAMPTZ,
    CONSTRAINT ck_file_share_subject_type CHECK (subject_type IN ('user', 'group')),
    CONSTRAINT ck_file_share_permission   CHECK (permission IN ('viewer', 'editor')),
    CONSTRAINT uq_file_share_folder_file_subject UNIQUE (folder_id, filename, subject_id)
);

CREATE INDEX idx_file_shares_folder_filename ON file_shares(folder_id, filename);
CREATE INDEX idx_file_shares_subject_id      ON file_shares(subject_id);
CREATE INDEX idx_file_shares_subject_active  ON file_shares(subject_id, revoked_at);
CREATE INDEX idx_file_shares_expires_at      ON file_shares(expires_at);
```

---

## Справочники объектов (миграция 064_object_directories)

Универсальный движок справочников объектов с контактами (подробности — [`./directories.md`](./directories.md), первый кейс — «Флот»). Встраивается вкладками в `/staff`. Три таблицы: **тип** справочника (= вкладка), **объект** (судно/склад) и его **контакты** (роль × канал × значение). Схема полей идентификации (`field_schema`) и набор каналов связи (`channels`) хранятся как JSONB на самом типе — низкая кардинальность, добавление поля не требует миграции; валидация — на уровне Pydantic (`type ∈ {text, number, email, url, multiline}`).

Гейтинг двухуровневый: мастер-флаг `modules.json` (`directories.enabled`) → весь раздел 404; per-type `enabled` → скрытие отдельной вкладки. Soft-delete (`deleted_at`) на типах и объектах; контакты удаляются жёстко через `ON DELETE CASCADE`. Миграция сидит тип `fleet` с готовой схемой и объект «Академик Казанин».

### object_directories — тип справочника (= вкладка)

```sql
CREATE TABLE object_directories (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         VARCHAR(50)  NOT NULL UNIQUE,           -- fleet, warehouses…
    label_ru     VARCHAR(100) NOT NULL,                  -- название вкладки (рус)
    label_en     VARCHAR(100),
    icon         VARCHAR(50),
    description  VARCHAR(500),
    field_schema JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- [{key,label_ru,label_en,type,required,sort_order}]
    channels     JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- [{key,label_ru,label_en,sort_order}]
    enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
    sort_order   INTEGER      NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX idx_object_directories_sort ON object_directories(sort_order);
```

### object_directory_entries — объект (судно / склад / гараж)

```sql
CREATE TABLE object_directory_entries (
    id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    directory_id UUID          NOT NULL REFERENCES object_directories(id) ON DELETE CASCADE,
    name         VARCHAR(200)  NOT NULL,                   -- «Академик Казанин»
    folder_id    UUID          REFERENCES file_folders(id) ON DELETE SET NULL,  -- привязанная папка /files
    attributes   JSONB         NOT NULL DEFAULT '{}'::jsonb,  -- {imo:"9489481", mmsi:"273411580"…}
    note         VARCHAR(1000),
    sort_order   INTEGER       NOT NULL DEFAULT 0,
    created_by   UUID          REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX idx_ode_directory ON object_directory_entries(directory_id, sort_order);
CREATE INDEX idx_ode_active    ON object_directory_entries(deleted_at);
CREATE INDEX idx_ode_folder    ON object_directory_entries(folder_id);
```

Поиск (`?q=` и Cmd+K) — только по `name`; значения `attributes` НЕ индексируются.

### object_entry_contacts — роль × канал × значение

```sql
CREATE TABLE object_entry_contacts (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id   UUID         NOT NULL REFERENCES object_directory_entries(id) ON DELETE CASCADE,
    role       VARCHAR(100),                 -- свободная строка: «Мостик», «Капитан»
    channel    VARCHAR(50)  NOT NULL,        -- key из directory.channels
    label      VARCHAR(200),                 -- доп. подпись
    value      VARCHAR(255) NOT NULL,        -- номер/почта/добавочный
    sort_order INTEGER      NOT NULL DEFAULT 0
);

CREATE INDEX idx_oec_entry ON object_entry_contacts(entry_id, sort_order);
```

`value` для e-mail хранится как `VARCHAR(255)`, НЕ `EmailStr` (DNS-проверка ломается на `.local`/корпоративных доменах — известная грабля проекта).

---

## Справочник получателей рассылки (миграция 071_mailing_recipients)

Курируемая адресная книга для рассылки новостей по email (фича «Сделать
рассылку» из карточки новости, см. `docs/news.md` §«Справочник получателей рассылки»). Редактор
выбирает получателей **только** из этого справочника — ad-hoc-ввод адреса в
модалке запрещён (анти-спам/анти-фишинг от имени портала). Управление —
`editor`/`admin`.

### mailing_recipients — получатель рассылки

```sql
CREATE TABLE mailing_recipients (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name               VARCHAR(255) NOT NULL,        -- имя/название получателя
    email              VARCHAR(320) NOT NULL,        -- адрес (валидируется как str, НЕ EmailStr)
    label              VARCHAR(100),                  -- метка (отдел, группа)
    created_by_user_id UUID         REFERENCES users.id ON DELETE SET NULL,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at         TIMESTAMPTZ                    -- soft-delete
);

-- CI-уникальность email среди не удалённых (как idx_users_email_ci_active)
CREATE UNIQUE INDEX idx_mailing_recipients_email_ci_active
    ON mailing_recipients (lower(email)) WHERE deleted_at IS NULL;
CREATE INDEX idx_mailing_recipients_active ON mailing_recipients (deleted_at);
```

- **Soft-delete** (`deleted_at`); удалённый адрес недоступен для выбора и
  резолва при рассылке. Уникальность email — case-insensitive, только среди
  активных строк (частичный индекс).
- `email` хранится как `VARCHAR(320)`, НЕ `EmailStr` (DNS-проверка ломается на
  `.local`/корпоративных доменах — известная грабля проекта). Валидация —
  regex `^[^@\s]+@[^@\s]+$`.
- Рассылка не создаёт отдельной таблицы: письма ставятся в существующий
  `email_outbox` (`kind=news`), по одной строке на получателя.

---

## Helpdesk (миграции 075–084)

> **Полное описание — в [`./helpdesk.md`](./helpdesk.md) §3.** Здесь — только
> краткая выжимка таблиц; подробные колонки/индексы/CHECK/поведение смотрите
> в модульной документации (единый источник истины).

Миграции `075_add_helpdesk` (всё ядро, hand-written DDL), `076` (digest-settings
singleton), `077` (`is_inline`/`content_id` на attachments), `078` (FTS
tsvector + GIN на tickets/messages), `079` (упразднён статус `resolved`),
`080` (`helpdesk_ticket_reads`).

| Таблица | Назначение |
|---|---|
| `helpdesk_tickets` | Заявка: `number` (BIGINT IDENTITY), subject/description, status (`new`/`open`/`pending`/`closed`), source (`email`/`web`), requester (user_id NULL для гостя + email/name-снимок), assignee, `search_tsvector` (FTS 078). Партиционированный архив — `helpdesk_tickets_archive` (jsonb-снимок). |
| `helpdesk_messages` | Сообщения переписки: `direction` (`inbound`/`outbound`), `body_text` + `body_html`, `email_message_id` (для threading), `body_tsvector` (FTS 078). |
| `helpdesk_attachments` | Вложения: путь на FS, MIME, `is_inline`/`content_id` (077, для inline `cid:` картинок). ФС — `/data/helpdesk/TKT-{number}/`. |
| `helpdesk_agents` | Справочник агентов поддержки (`user_id` UNIQUE) — **отдельная** сущность от `users.role`, проверяется через `require_helpdesk_agent` (admin — суперсет). |
| `helpdesk_email_log` | Идемпотентность IMAP-фетчера (Message-ID → processed_at), anti-loop. |
| `helpdesk_mailbox_settings` | Singleton (id=1) с IMAP-настройками support-ящика; `imap_password_enc` Fernet-шифрован (write-only). |
| `helpdesk_digest_settings` | Singleton (id=1) расписания ежедневной email-сводки агентам (`enabled`, `digest_hour`/`digest_minute`, `digest_schedule`). |
| `helpdesk_ticket_reads` | Marker-таблица per-agent read-state (`ticket_id`, `user_id`, `last_seen_at`) — миграция 080, UNIQUE для UPSERT, CASCADE на обеих FK. Контракт «непрочитанности» — см. `helpdesk.md` §3. |
| `helpdesk_tickets_archive` | Партиционированная (по месяцам) таблица архива closed-тикетов (jsonb-снимок); партиции создаёт ARQ-задача. |

Все мутации аудируются (`helpdesk.*`). Module-gate `modules.json → helpdesk.enabled`
вешает 404 на весь `/api/v1/helpdesk/*` при выключенном модуле. Двусторонний
email-thread — через существующий `email_outbox` (`kind=helpdesk`).

---

## MAX-messenger / messenger_outbox (миграция 081)

> **Полное описание — в [`./helpdesk.md`](./helpdesk.md) §3 (`helpdesk_max_bot_settings`,
> `messenger_outbox`).** Здесь — только выжимка.

Миграция `081_add_messenger_outbox_and_max_bot_settings` добавляет две таблицы:

| Таблица | Назначение |
|---|---|
| `helpdesk_max_bot_settings` | Singleton (id=1, `CHECK (id=1)`) конфигурации MAX-бота для оповещений о новых заявках в общий чат поддержки. `enabled=False` по умолчанию; `bot_token_enc` Fernet-шифрован (write-only, как `imap_password_enc`); `chat_id` вводит админ. Канал готов при `enabled=True AND bot_token_enc IS NOT NULL AND chat_id IS NOT NULL` (флаг `configured` в API). |
| `messenger_outbox` | Transactional outbox для не-email каналов — полный аналог `email_outbox`: `provider` (`'max'`, зарезервировано для Telegram/Slack), `chat_id`, `text`, `payload` JSONB (attachments + format), `status` (`PENDING/SENDING/SENT/FAILED/DLQ/CANCELLED`), retry/backoff/DLQ. Воркер `process_messenger_outbox` (cron 15с, distributed lock + `FOR UPDATE SKIP LOCKED`), cleanup — nightly. Retry-классификация: 429/5xx/timeout → transient, 4xx → permanent (DLQ). |

TLS-особенность: сертификат `*.max.ru` подписан Russian Trusted Root CA
(Минцифры), который отсутствует в Mozilla CA Bundle / `certifi`. Корневой
сертификат лежит в `backend/certs/russian_trusted_root_ca.crt` и
устанавливается в Docker-образ через `update-ca-certificates` (см. `Dockerfile`);
httpx-клиент использует `ssl.create_default_context()` для системного trust
store. Это общий фикс для любых российских TLS-endpoint'ов.

---

## Индексные миграции (021–024)

Миграции только для индексов — не создают новых таблиц.

### 021 — `news.title` trgm + `photo_folders.fs_path`

```sql
CREATE INDEX CONCURRENTLY idx_news_title_trgm ON news USING GIN (title gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_photo_folders_fs_path ON photo_folders(fs_path);
```

### 022 — FK-индексы (joins и фильтры)

```sql
CREATE INDEX CONCURRENTLY idx_news_versions_editor_id         ON news_versions(editor_id);
CREATE INDEX CONCURRENTLY idx_service_links_created_by        ON service_links(created_by);
CREATE INDEX CONCURRENTLY idx_kb_sections_created_by          ON kb_sections(created_by);
CREATE INDEX CONCURRENTLY idx_kb_article_comments_author_id   ON kb_article_comments(author_id);
CREATE INDEX CONCURRENTLY idx_kb_suggestions_author_id        ON kb_suggestions(author_id);
CREATE INDEX CONCURRENTLY idx_kb_suggestions_reviewed_by      ON kb_suggestions(reviewed_by);
CREATE INDEX CONCURRENTLY idx_photo_folders_cover_photo_id    ON photo_folders(cover_photo_id);
CREATE INDEX CONCURRENTLY idx_photos_uploaded_by              ON photos(uploaded_by);
CREATE INDEX CONCURRENTLY idx_photo_share_tokens_created_by   ON photo_share_tokens(created_by);
```

### 023 — `users.keycloak_groups`

```sql
ALTER TABLE users ADD COLUMN keycloak_groups TEXT[] NOT NULL DEFAULT '{}';
```

Поле синхронизируется из JWT claim `groups` при каждом логине через Keycloak.
Используется KB ACL для subject_type = `'group'`.

### 024 — GIN-индексы `users` и `service_links` для pg_trgm поиска

```sql
CREATE INDEX CONCURRENTLY idx_users_full_name_trgm    ON users USING gin (full_name gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_users_department_trgm   ON users USING gin (department gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_service_links_title_trgm ON service_links USING gin (title gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_service_links_url_trgm   ON service_links USING gin (url gin_trgm_ops);
```

Ускоряет `GET /search?q=...` по пользователям и ярлыкам.

---

## Миграции 025–038 (май 2026)

### 025 — `users.attributes` JSONB

```sql
ALTER TABLE users ADD COLUMN attributes JSONB NOT NULL DEFAULT '{}';
```

Хранит произвольные атрибуты из Keycloak JWT claims. Структура ключей управляется через `user_attribute_mappings`.

### 026 — `user_attribute_mappings`

Новая таблица — справочник отображаемых атрибутов профиля. Описание см. в разделе **Таблица: user_attribute_mappings** выше.

### 027 — `news.cover_focal_point` (заменено миграцией 072)

```sql
ALTER TABLE news ADD COLUMN cover_focal_point VARCHAR(16);
```

Грубая enum-точка фокуса обложки (`top`/`center`/`bottom`). **Заменена в миграции 072** на произвольную точку в процентах.

### 072 — `news.cover_focal_x` / `cover_focal_y`

```sql
ALTER TABLE news ADD COLUMN cover_focal_x SMALLINT;  -- CHECK (NULL OR 0..100)
ALTER TABLE news ADD COLUMN cover_focal_y SMALLINT;  -- CHECK (NULL OR 0..100)
-- backfill из enum: top → (50, 0), bottom → (50, 100); center/NULL → NULL
ALTER TABLE news DROP COLUMN cover_focal_point;
```

Произвольная точка фокуса обложки в процентах для CSS `object-position` (`{x}% {y}%`). `NULL` интерпретируется приложением как центр (50/50). Кадрирование по-прежнему чисто клиентское (`object-fit: cover`), изображение не пересоздаётся.

### 073 — `news.cover_focal_zoom`

```sql
ALTER TABLE news ADD COLUMN cover_focal_zoom SMALLINT;  -- CHECK (NULL OR 100..300)
```

Лёгкое приближение обложки для CSS `transform: scale(zoom/100)` с `transform-origin` в точке фокуса. `NULL` = 100% = без приближения. Только zoom-IN; изображение и WebP/AVIF-варианты не пересоздаются.

### 028 — `users.deleted_at` (soft-delete)

```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ;
CREATE INDEX idx_users_active ON users(email) WHERE deleted_at IS NULL;
```

Пользователи теперь мягко удаляются. Hard-delete через прямой `DELETE` запрещён в приложении.

### 029 — `news.category` → `news.categories`

```sql
ALTER TABLE news ADD COLUMN categories TEXT[] NOT NULL DEFAULT '{}';
UPDATE news SET categories = ARRAY[category] WHERE category IS NOT NULL AND category <> '';
ALTER TABLE news DROP COLUMN category;
```

Замена одиночного поля `category VARCHAR` на массив `categories TEXT[]` для поддержки нескольких категорий.

### 030 — case-insensitive уникальность `users.email`

```sql
DROP CONSTRAINT uq_users_email;
DROP INDEX idx_users_email;
CREATE UNIQUE INDEX idx_users_email_ci    ON users (LOWER(email)) WHERE deleted_at IS NULL;
CREATE INDEX        idx_users_email_lower ON users (LOWER(email));
```

Предотвращает дублирование `user@example.ru` и `User@example.ru`. После soft-delete email освобождается для повторного использования.

### 031 — `photo_folders.parent_id` ON DELETE CASCADE → RESTRICT

Предотвращает случайное каскадное удаление всего поддерева при прямом `DELETE` из psql. Приложение использует soft-delete.

### 032 — FK SET NULL для `notifications` и `bookmarks`

```sql
-- notifications.user_id: CASCADE → SET NULL
-- bookmarks.user_id: CASCADE → SET NULL
```

История уведомлений и закладок сохраняется после удаления пользователя (soft-deleted). `user_id = NULL` означает «удалённый пользователь».

### 033 — GIN индекс на `audit_log.metadata`

```sql
CREATE INDEX IF NOT EXISTS idx_audit_log_metadata_gin ON audit_log USING gin(metadata jsonb_path_ops);
```

Ускоряет фильтрацию по `metadata @> '{"resource_type": "..."}'` в admin Audit Log. Без `CONCURRENTLY` — партиционированные таблицы его не поддерживают.

### 034 — `kb_articles.section_id` ON DELETE SET NULL → RESTRICT

Удаление раздела с активными статьями теперь запрещено на уровне БД. Приложение обрабатывает явно: active articles → 409; soft-deleted articles → `section_id = NULL` до удаления раздела.

### 035 — `photo_folders.path` UNIQUE partial index

```sql
DROP INDEX idx_photo_folders_path;
CREATE UNIQUE INDEX IF NOT EXISTS uq_photo_folders_path ON photo_folders(path) WHERE deleted_at IS NULL;
```

Гарантирует глобальную уникальность `path` среди активных папок. Soft-deleted папки исключены, что позволяет повторно использовать path.

### 036 — `kb_sections.deleted_at` (soft-delete)

```sql
ALTER TABLE kb_sections ADD COLUMN deleted_at TIMESTAMPTZ;
CREATE INDEX idx_kb_sections_deleted ON kb_sections(deleted_at) WHERE deleted_at IS NULL;
```

Разделы KB теперь мягко удаляются. Запросы фильтруют `WHERE deleted_at IS NULL`. Явное полное удаление — через `DELETE /kb/sections/{id}?force=true` (admin).

### 037 — `users.email` partial unique index (active-only)

```sql
DROP INDEX idx_users_email_ci;
CREATE UNIQUE INDEX idx_users_email_ci_active ON users (LOWER(email)) WHERE deleted_at IS NULL;
```

Переименование индекса из `idx_users_email_ci` в `idx_users_email_ci_active` с сохранением partial-условия. Позволяет повторно использовать email после soft-delete пользователя.

---

## Миграции 039–084 (июнь–июль 2026)

> Подробности таблиц — в соответствующих секциях выше или в модульных доках
> (`./helpdesk.md`, `./email.md`, `./news.md`, `./directories.md`). Здесь —
> краткий обзор каждой миграции как дополнение к разделу «Миграции 025–038».

| № | Имя | Что делает | Где подробно |
|---|---|---|---|
| 039 | `news_cover_meta` | `news.cover_dominant_color` (hex) + `cover_variants` (массив пикс.) — для CSS-палитры обложки | `./news.md` |
| 040 | `add_feedback` | Модуль обратной связи: `feedback_messages` + вложения в `/data/feedback/files/` | `./feedback.md` |
| 041 | `add_feedback_attachments` | Вложения к сообщениям обратной связи | `./feedback.md` |
| 042 | `file_folder_inherit_permissions` | `file_folders.inherit_permissions` — наследование прав папок файлового модуля | `./files.md` |
| 043 | `news_previous_status` | `news.previous_status` — статус до последней смены (для восстановления из архива/черновика) | `./news.md` |
| 044 | `staff_directory_order` | `staff_directory_order` — порядок отделов и скрытые сотрудники в `/staff` (admin-managed) | `./staff-directory-spec.md` |
| 045 | `soft_delete_partial_indexes` | Частичные индексы `WHERE deleted_at IS NULL` на ключевых таблицах (kb/news/links) | эта же дока |
| 046 | `kb_users_partial_indexes` | Доп. partial-индексы для KB и users | — |
| 047 | `user_attribute_mapping_full_name_source` | `user_attribute_mappings.is_full_name_source` — выбор атрибута-источника `users.full_name` | §«Таблица: user_attribute_mappings» |
| 048 | `meetings` | Модуль «Переговорные»: `meeting_rooms`, `meeting_bookings`, серии, iCal | `./meetings.md` |
| 049 | `meeting_rooms_add_email` | `meeting_rooms.email` — почта комнаты для iCal | `./meetings.md` |
| 050 | `drop_meetings_audit_log` | Удалена устаревшая `meetings_audit_log` (вся телеметрия — в общем `audit_log`) | — |
| 051 | `email_outbox` | Transactional outbox — см. [§«Email outbox»](#email-outbox-миграция-051) | `./email.md` |
| 052 | `kb_section_inherit_permissions` | `kb_sections.inherit_permissions` — наследование прав KB-раздела | §«kb_sections» |
| 053 | `add_news_polls` | Опросы в новостях (`news_polls`, single-question) | `./polls.md` |
| 054 | `news_poll_multi_questions` | Multi-question polls (`news_poll_questions`) | `./polls.md` |
| 055 | `meeting_rooms_add_kind` | `meeting_rooms.kind` — тип комнаты | `./meetings.md` |
| 056 | `photo_folder_perm_unique_subject_type` | UNIQUE `(folder_id, subject_type, subject_id)` — раздельные права user/group | §«photo_folder_permissions» |
| 057 | `photo_folder_storage_kind` | `photo_folders.storage_kind` (`originals`/`import`) | §«photo_folders» |
| 058 | `kb_article_version_body_required` | `kb_article_versions.body NOT NULL` (защита отката к версии с пустым телом) | §«kb_article_versions» |
| 059 | `kb_sections_parent_slug_unique` | `uq_kb_sections_parent_slug (parent_id, slug)` | §«kb_sections» |
| 060 | `photos_blurhash` | `photos.blurhash` — skeleton-preview до загрузки полного изображения | §«photos» |
| 061 | `kb_articles_list_index` | Индекс для списочного endpoint'а KB | — |
| 062 | `backfill_users_directory_active_index` | Backfill для `idx_users_directory_active` | — |
| 063 | `file_shares` | Пофайловый шеринг — см. §«file_shares» | `./sharing.md` |
| 064 | `object_directories` | Справочники объектов — 3 таблицы (тип/объект/контакты) | §«Справочники объектов», `./directories.md` |
| 065 | `directory_entry_folder` | `object_directory_entries.folder_id` — привязка к папке `/files` | `./directories.md` |
| 066 | `file_items_unique_active_name` | UNIQUE partial `file_items.nc_path WHERE deleted_at IS NULL` | §«file_items» |
| 067 | `backfill_folder_creator_manager_perm` | Backfill: создатель папки → manager на ней | `./files.md` |
| 068 | `news_likes` | Реакция «лайк» (♥) — см. §«news_likes» | `./news.md` |
| 069 | `news_comments` | Плоские комментарии к новостям — см. §«news_comments» | `./news.md` |
| 070 | `service_links_show_on_home` | `service_links.show_on_home` — виджет «Сервисы» на главной | §«service_links» |
| 071 | `mailing_recipients` | Справочник получателей рассылки — см. §«mailing_recipients» | эта же дока |
| 072 | `news_cover_focal_xy` | `news.cover_focal_x`/`cover_focal_y` (заменено enum 027) — точка фокуса для CSS `object-position` | §«Миграции 025–038» → 072 |
| 073 | `news_cover_focal_zoom` | `news.cover_focal_zoom` — приближение обложки (`transform: scale`) | §«Миграции 025–038» → 073 |
| 074 | `add_kb_url_to_service_links` | `service_links.kb_url` — опциональная ссылка на инструкцию | §«service_links» |
| 075 | `add_helpdesk` | 7 таблиц helpdesk + первая партиция архива — см. [§«Helpdesk»](#helpdesk-миграции-075080) | `./helpdesk.md` §3 |
| 076 | `add_helpdesk_digest_settings` | Singleton `helpdesk_digest_settings` (расписание сводки) | `./helpdesk.md` §3 |
| 077 | `add_helpdesk_attachments_inline_columns` | `helpdesk_attachments.is_inline`/`content_id` (schema-drift фикс) | `./helpdesk.md` §3 |
| 078 | `add_helpdesk_fts` | `helpdesk_tickets.search_tsvector` + `helpdesk_messages.body_tsvector` (GIN) | `./helpdesk.md` §3, §4 (поиск) |
| 079 | `drop_helpdesk_resolved` | Упразднён статус `resolved` (data-mig → `closed`) | `./helpdesk.md` §5 |
| 080 | `add_helpdesk_ticket_reads` | `helpdesk_ticket_reads` — per-agent read-state | `./helpdesk.md` §3 |
| 081 | `add_messenger_outbox_and_max_bot_settings` | `messenger_outbox` + `helpdesk_max_bot_settings` (MAX-бот) — см. [§«MAX-messenger»](#max-messenger--messenger_outbox-миграция-081) | `./helpdesk.md` §«MAX-messenger оповещения» |
| 082 | `add_helpdesk_draft_attachments` | `helpdesk_draft_attachments` — вложения в черновиках ответа агента | `./helpdesk.md` §3 |
| 083 | `add_helpdesk_messages_cc` | `helpdesk_messages.cc` (JSONB) — копия (Cc) входящей/исходящей почты | `./helpdesk.md` §3 |
| 084 | `drop_helpdesk_message_visibility` | Удалена колонка `helpdesk_messages.visibility` (internal-note-видимость не используется) | `./helpdesk.md` §3 |
| 085 | `notifications_cleanup_index` | Индекс для очистки старых уведомлений | §«notifications» |
| 086 | `add_helpdesk_smtp_settings` | SMTP-блок в `helpdesk_mailbox_settings` (собственный исходящий контур helpdesk) | `./helpdesk.md` §3 |
| 087 | `add_users_birth_date_gender_erp_sync` | `users.birth_date`/`gender` + `erp_sync_runs` + `erp_sync_settings` (импорт дней рождения и пола из ERP) | [§«ERP-sync»](#erp-sync-миграция-087) |
| 088 | `add_erp_sync_mail_filter_and_poll` | `erp_sync_settings`: `poll_enabled` (двойной гейтинг) + `mail_subject_filter`/`mail_sender_filter`/`mail_attachment_filter` (post-fetch фильтры для общего ящика) | [§«ERP-sync»](#erp-sync-миграция-087) |
| 089 | `move_erp_imap_to_email_settings` | Бэкфилл IMAP `erp_sync_settings` → `/data/branding/email-settings.json` (ADR-048) + DROP `imap_*` колонок из `erp_sync_settings` | [§«ERP-sync»](#erp-sync-миграция-087) |
| 090 | `add_erp_sync_delete_after_fetch` | `erp_sync_settings.delete_after_fetch` (удаление писем из общего ящика после успешного импорта) | [§«ERP-sync»](#erp-sync-миграция-087) |

---

## ERP-sync (миграция 087)

Импорт даты рождения и пола сотрудников из ERP-выгрузки (1С). ERP шлёт письмо 2
раза в неделю с отчётом «Справочник: Сотрудники»; портал опрашивает служебный
ящик по IMAP (cron), парсит вложение, сопоставляет ФИО с `users.full_name` и
записывает `birth_date` + `gender`. Каждый импорт перетирает значения (источник
истины — ERP); diff попадает в email-отчёт админу. Подробно —
[`./wip/erp-sync.md`](./wip/erp-sync.md) (пока WIP; полноценный модульный док
появится в PR2).

### `users.birth_date` / `users.gender`

Колонки на `users` (nullable). Видны всем авторизованным в карточке `/staff`
(аналогично `position`/`phone`). Admin может редактировать вручную через
`PATCH /users/admin/{id}/profile`, но следующий импорт ERP перетрёт значение.

### `erp_sync_runs`

Лог каждого прохода импорта (автоматического по cron или ручного). Idempotency
по `message_id` (UNIQUE) для дедупа писем; `report` (JSONB) — структурированный
результат для email-отчёта админу (разделы `changed`/`unmatched`/`ambiguous`/
`conflicts`/`errors`).

### `erp_sync_settings`

Singleton (`id = 1`) с IMAP-настройками ящика, на который ERP шлёт отчёты. Клон
паттерна `helpdesk_mailbox_settings`: пароль — Fernet-шифр (`imap_password_enc`),
plaintext write-only. `poll_interval_seconds` (CHECK 60–3600, default 900) —
как часто cron опрашивает ящик; `expected_interval_days` (default 4) — для
watchdog-алерта «письма нет >N дней»; `notify_emails` — override списка адресов
для отчётов (NULL = все admin с `notify_email=true`). Гетируется модулем
`erp_sync.enabled` в `modules.json`.

**Миграция 088** (additive): `poll_enabled` (default false) — отдельный флаг
авто-поллинга. Двойной гейтинг: `modules.erp_sync.enabled` (вся фича) AND
`poll_enabled` (только авто-забор); позволяет выключить поллинг, оставив ручной
upload. `mail_subject_filter` / `mail_sender_filter` / `mail_attachment_filter`
(nullable) — CI-подстроки для post-fetch фильтрации писем на общем ящике (без
фильтра импорт сломается на чужом письме; письма мимо фильтра **не**
помечаются `\Seen`). Подробно — [`./erp-sync.md`](./erp-sync.md).

**Миграция 089** (бэкфилл + DROP): IMAP-настройки (`imap_host`/`port`/`use_ssl`/
`username`/`password_enc`/`folder`) перенесены из `erp_sync_settings` в общий
`/data/branding/email-settings.json` (ADR-048 — приёмка почты общая, вкладка
Email); колонки удалены. Пароль шифруется Fernet в `imap_password_enc` в JSON.

**Миграция 090** (additive): `delete_after_fetch` (default false) — удалять
письма из общего ящика после успешного импорта (`STORE +FLAGS \Deleted` +
`EXPUNGE`, клон `helpdesk_mailbox_settings.delete_after_fetch`). Default off:
удаление на общем ящике необратимо, админ включает осознанно. Дедуп по
`message_id` (UNIQUE в `erp_sync_runs`) защищает от повторной обработки и без
удаления.

