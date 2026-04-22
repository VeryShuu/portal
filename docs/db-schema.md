# Database Schema

> Корпоративный интранет-портал
> PostgreSQL 16
> Последнее обновление: апрель 2026

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
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at    TIMESTAMPTZ
);

CREATE INDEX idx_users_keycloak ON users(keycloak_id) WHERE keycloak_id IS NOT NULL;
CREATE INDEX idx_users_email    ON users(email);
CREATE INDEX idx_users_dept     ON users(department);
CREATE INDEX idx_users_source   ON users(auth_source);
```

> Отдельная таблица `user_profiles` и `user_preferences` не создаются — все доп. поля слиты в `users`. Персональные настройки (скрытые ярлыки) хранятся в `preferences JSONB`.
>
> **Account-linking:** при логине через Keycloak пользователь с тем же `email`, у которого `keycloak_id IS NULL`, переводится с `auth_source = 'local'` на `'keycloak'` (см. `app/api/auth.py::_upsert_user`). Роль при этом сохраняется (важно для bootstrap-admin), событие пишется в логи как `auth.account_linked`.

---

## База знаний (KB)

### kb_sections

```sql
CREATE TABLE kb_sections (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id    UUID         REFERENCES kb_sections(id)
                     ON DELETE RESTRICT,            -- CASCADE опасен: снесёт всё дерево
    title        VARCHAR(255) NOT NULL,
    slug         VARCHAR(255) UNIQUE NOT NULL,
    description  TEXT,
    order_index  INTEGER      NOT NULL DEFAULT 0,
    created_by   UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kb_sections_parent ON kb_sections(parent_id);
```

> Дерево реализовано как adjacency list. Хлебные крошки строятся рекурсивным CTE.
> Удаление раздела с дочерними элементами запрещено на уровне БД.
> Явное удаление со всем содержимым — только через `DELETE /kb/sections/{id}?force=true` (admin).

---

### kb_articles

```sql
CREATE TABLE kb_articles (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id     UUID         REFERENCES kb_sections(id) ON DELETE SET NULL,
    title          VARCHAR(500) NOT NULL,
    body           TEXT         NOT NULL DEFAULT '',   -- Markdown (CommonMark + GFM)
    -- Черновик: автосохранение каждые 30 сек, не создаёт версию
    draft_title    VARCHAR(500),
    draft_body     TEXT,
    draft_saved_at TIMESTAMPTZ,
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
    version_number INTEGER      NOT NULL,
    title          VARCHAR(500),
    body           TEXT,
    changed_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    change_comment VARCHAR(500),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(article_id, version_number)
);

CREATE INDEX idx_kb_versions_article ON kb_article_versions(article_id, version_number DESC);
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

## Новости

### news

```sql
CREATE TABLE news (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title              VARCHAR(500) NOT NULL,
    body               TEXT         NOT NULL DEFAULT '',   -- Markdown
    -- Черновик (автосохранение каждые 30 сек)
    draft_title        VARCHAR(500),
    draft_body         TEXT,
    draft_saved_at     TIMESTAMPTZ,
    body_tsvector      TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('russian_hunspell',
            coalesce(title, '') || ' ' || coalesce(body, ''))
    ) STORED,
    category           VARCHAR(100),                       -- 'company', 'it', 'hr', 'projects'
    status             VARCHAR(20)  NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'published', 'archived')),
    is_pinned          BOOLEAN      NOT NULL DEFAULT FALSE,
    -- Таргетирование: NULL = все; непустой массив = только указанные
    target_departments TEXT[],                             -- ['IT', 'HR']
    target_roles       TEXT[],                             -- ['editor', 'admin']
    created_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    updated_by         UUID         REFERENCES users(id) ON DELETE SET NULL,
    publish_at         TIMESTAMPTZ,                        -- отложенная публикация
    archive_at         TIMESTAMPTZ,                        -- автоархивация
    view_count         INTEGER      NOT NULL DEFAULT 0,
    -- Soft delete
    deleted_at         TIMESTAMPTZ,
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

### news_versions

```sql
CREATE TABLE news_versions (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id        UUID         NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    version_number INTEGER      NOT NULL,
    title          VARCHAR(500),
    body           TEXT,
    changed_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    change_comment VARCHAR(500),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(news_id, version_number)
);

CREATE INDEX idx_news_versions_news ON news_versions(news_id, version_number DESC);
```

---

## Ярлыки сервисов

### service_links

```sql
CREATE TABLE service_links (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(255) NOT NULL,
    url          VARCHAR(2048) NOT NULL,
    icon_url     VARCHAR(2048),
    category     VARCHAR(100),                     -- 'dev', 'finance', 'hr', 'common', 'comm'
    order_index  INTEGER      NOT NULL DEFAULT 0,
    supports_sso BOOLEAN      NOT NULL DEFAULT FALSE,  -- пробрасывать ли id_token_hint
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_service_links_active ON service_links(category, order_index)
    WHERE is_active = TRUE;
```

---

## Закладки

### bookmarks

```sql
CREATE TABLE bookmarks (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource_type  VARCHAR(50)  NOT NULL,    -- 'article', 'news', 'file', 'link'
    resource_id    VARCHAR(255) NOT NULL,    -- UUID или Nextcloud path
    resource_title VARCHAR(500),
    resource_url   VARCHAR(2048),
    group_name     VARCHAR(100),             -- пользовательская группа закладок
    order_index    INTEGER      NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, resource_type, resource_id)
);

CREATE INDEX idx_bookmarks_user ON bookmarks(user_id, group_name, order_index);
```

---

## Уведомления

### notifications

```sql
CREATE TABLE notifications (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       VARCHAR(50)  NOT NULL,    -- 'new_news', 'article_updated', 'file_shared', 'suggest_approved'
    title      VARCHAR(255) NOT NULL,
    body       TEXT,
    link       VARCHAR(2048),
    is_read    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
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
    user_id        UUID,
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
CREATE INDEX idx_audit_user_time   ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_event_time  ON audit_log(event_type, created_at DESC);
CREATE INDEX idx_audit_resource    ON audit_log(resource_type, resource_id);
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

## Схема связей (ERD)

```
users ──────────────────────────────────────────────────────────────────────┐
  │ 1                                                                        │
  │ ├─ n kb_articles (created_by, updated_by)                                │
  │ ├─ n news (created_by, updated_by)                                        │
  │ ├─ n bookmarks                                                           │
  │ ├─ n notifications                                                       │
  │ └─ n audit_log (user_id)                                                 │
                                                                             │
kb_sections ──(self-ref parent_id, RESTRICT)──► kb_sections                 │
  │ 1                                                                        │
  └─ n kb_articles (SET NULL on section delete)                              │
       │ 1                                                                   │
       ├─ n kb_article_versions (CASCADE)                                    │
       ├─ n kb_article_tags (CASCADE) ──► kb_tags                            │
       └─ n kb_article_comments (CASCADE)                                    │
                                                                             │
news ──► n news_versions (CASCADE)                                           │
                                                                             │
service_links (standalone)                                                   │
bookmarks → users (CASCADE), resource_* (no FK, polymorphic)                │
notifications → users (CASCADE)                                             │
audit_log (partitioned, user_id без FK для производительности)               │
idempotency_keys (standalone, TTL 24h)                                       │
```

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
