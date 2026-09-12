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

DO $$
BEGIN
  BEGIN
    CREATE TEXT SEARCH DICTIONARY russian_hunspell_dict (
      TEMPLATE  = ispell,
      DictFile  = russian,
      AffFile   = russian,
      StopWords = russian
    );
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION
      E'Cannot create hunspell FTS dictionary (russian_hunspell_dict).\n'
      'Ensure files russian.dict, russian.affix, russian.stop are present in '
      '$SHAREDIR/tsearch_data/ of the PostgreSQL image.\n'
      'Solution: build with the custom postgres/Dockerfile that copies hunspell/ files.\n'
      'Original error: %', SQLERRM;
  END;

  CREATE TEXT SEARCH CONFIGURATION russian_hunspell (COPY = russian);

  ALTER TEXT SEARCH CONFIGURATION russian_hunspell
      ALTER MAPPING FOR hword, hword_part, word
      WITH russian_hunspell_dict, russian_stem;
END $$;

-- audit_log и его партиции создаются миграцией 013_audit_log.py (единственный источник истины).
-- init.sql намеренно не создаёт audit_log, чтобы избежать рассинхронизации схемы.
