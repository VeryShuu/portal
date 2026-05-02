-- backend/migrations/init.sql
-- Выполняется при первом старте PostgreSQL контейнера (docker-entrypoint-initdb.d)
-- Порядок важен: расширения → FTS → первые партиции audit_log

-- ── Расширения ───────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Full-Text Search: hunspell_ru ────────────────────────────
-- Требует файлы russian.dict, russian.affix, russian.stop в $SHAREDIR/tsearch_data/
-- (устанавливаются через кастомный postgres/Dockerfile)
CREATE TEXT SEARCH DICTIONARY russian_hunspell_dict (
    TEMPLATE  = ispell,
    DictFile  = russian,
    AffFile   = russian,
    StopWords = russian
);

CREATE TEXT SEARCH CONFIGURATION russian_hunspell (COPY = russian);

ALTER TEXT SEARCH CONFIGURATION russian_hunspell
    ALTER MAPPING FOR hword, hword_part, word
    WITH russian_hunspell_dict, russian_stem;

-- ── Audit log: партиционированная таблица ───────────────────
-- Партиционирование по created_at — native PG16, без pg_partman
CREATE TABLE IF NOT EXISTS audit_log (
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

-- Индексы на parent-таблице наследуются дочерними (PG16)
CREATE INDEX IF NOT EXISTS idx_audit_user_time  ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_time ON audit_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_resource   ON audit_log(resource_type, resource_id);

-- Начальные партиции (текущий и следующие 2 месяца)
-- Скрипт backend/scripts/create_audit_partitions.py создаёт партиции автоматически
-- Здесь жёстко прописаны 3 партиции для первоначального деплоя

DO $$
DECLARE
    start_date DATE;
    end_date   DATE;
    tbl_name   TEXT;
BEGIN
    FOR i IN 0..2 LOOP
        start_date := DATE_TRUNC('month', NOW()) + (i || ' month')::INTERVAL;
        end_date   := start_date + '1 month'::INTERVAL;
        tbl_name   := 'audit_log_' || TO_CHAR(start_date, 'YYYY_MM');

        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = tbl_name AND n.nspname = 'public'
        ) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                tbl_name,
                start_date,
                end_date
            );
        END IF;
    END LOOP;
END $$;
