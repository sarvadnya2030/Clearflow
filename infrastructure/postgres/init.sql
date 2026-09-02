-- ClearFlow Compliance Vector Store — PostgreSQL + pgvector initialisation
-- Runs automatically when the pgvector container starts for the first time.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Compliance embeddings table ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      VARCHAR(100) NOT NULL,
    source      VARCHAR(50)  NOT NULL,   -- FATF / OFAC / AMLD6 / MAS / SWIFT / PCI
    category    VARCHAR(50)  NOT NULL,   -- SANCTIONS / AML / KYC / RISK / SECURITY
    chunk_index INTEGER      NOT NULL,
    chunk_text  TEXT         NOT NULL,
    embedding   vector(384),             -- all-MiniLM-L6-v2 dimensions
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ANN index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_compliance_embedding_cosine
    ON compliance_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Composite index for filtered searches by source/category
CREATE INDEX IF NOT EXISTS idx_compliance_source_category
    ON compliance_embeddings (source, category);

-- Spring AI vector store table (used by PgVectorStore auto-schema)
CREATE TABLE IF NOT EXISTS vector_store (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content     TEXT,
    metadata    JSON,
    embedding   vector(384)
);

CREATE INDEX IF NOT EXISTS idx_vector_store_embedding
    ON vector_store
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
