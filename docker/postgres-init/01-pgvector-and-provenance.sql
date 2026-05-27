-- Bootstrap script for the Postgres+pgvector container.
-- 1. Enable the pgvector extension.
-- 2. Create the Vismaran provenance index schema.
-- 3. Create the demo's embeddings table.
--
-- Day-1 scaffold: schema is final; population happens via vismaran_sdk wrappers
-- (provenance) and the demo seed script (embeddings).

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Vismaran provenance index
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS vismaran;

CREATE TABLE IF NOT EXISTS vismaran.provenance (
    id             BIGSERIAL PRIMARY KEY,
    subject_id     TEXT        NOT NULL,
    framework      TEXT        NOT NULL,  -- 'cognee' | 'pgvector' | 'tensorzero'
    record_id      TEXT        NOT NULL,  -- framework-native row identifier
    write_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    tags           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- Natural dedup key — re-recording is a no-op (ON CONFLICT DO NOTHING).
    UNIQUE (subject_id, framework, record_id)
);

CREATE INDEX IF NOT EXISTS provenance_subject_idx
    ON vismaran.provenance (subject_id);

CREATE INDEX IF NOT EXISTS provenance_subject_framework_idx
    ON vismaran.provenance (subject_id, framework);

-- Local audit log of erasure operations (for fail-loud retry semantics).
CREATE TABLE IF NOT EXISTS vismaran.erasure_log (
    id             BIGSERIAL PRIMARY KEY,
    operation_id   UUID        NOT NULL UNIQUE,
    subject_id_hash TEXT       NOT NULL,
    in_progress    BOOLEAN     NOT NULL DEFAULT TRUE,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    per_adapter    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    receipt_path   TEXT
);

-- ---------------------------------------------------------------------------
-- Demo embeddings (consumed by the pgvector adapter via the provenance index)
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS demo;

CREATE TABLE IF NOT EXISTS demo.embeddings (
    id          UUID        PRIMARY KEY,
    source_text TEXT        NOT NULL,
    embedding   vector(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx
    ON demo.embeddings
    USING hnsw (embedding vector_cosine_ops);
