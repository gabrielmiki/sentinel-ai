-- PostgreSQL initialization script for vector database (pgvector)

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS embeddings;
CREATE SCHEMA IF NOT EXISTS sentinel;

SET search_path TO embeddings, sentinel, public;

-- Create table for runbook embeddings
CREATE TABLE IF NOT EXISTS embeddings.runbook_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runbook_id UUID NOT NULL,
    content TEXT NOT NULL,
    embedding vector(3072),  -- Google Gemini embedding dimension
    meta JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create table for incident embeddings
CREATE TABLE IF NOT EXISTS embeddings.incident_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,
    content TEXT NOT NULL,
    embedding vector(3072),  -- Google Gemini embedding dimension
    meta JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create runbooks table in sentinel schema (co-located with embeddings for JOIN queries)
CREATE TABLE IF NOT EXISTS sentinel.runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    tags VARCHAR(100)[],
    category VARCHAR(100),
    chunk_count INTEGER DEFAULT 0,
    source_filename VARCHAR(255),
    created_by UUID,  -- No FK constraint since users table is in different database
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for vector similarity search
-- Note: Indexes disabled for 3072-dimension embeddings due to pgvector limitations
-- TODO: Investigate halfvec type or dimension reduction for index support
-- For now, queries will use sequential scan (slower but functional)
--
-- CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_vector
--     ON embeddings.runbook_embeddings
--     USING hnsw (embedding vector_cosine_ops);
--
-- CREATE INDEX IF NOT EXISTS idx_incident_embeddings_vector
--     ON embeddings.incident_embeddings
--     USING hnsw (embedding vector_cosine_ops);

-- Create indexes for filtering
CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_runbook_id
    ON embeddings.runbook_embeddings(runbook_id);

CREATE INDEX IF NOT EXISTS idx_incident_embeddings_incident_id
    ON embeddings.incident_embeddings(incident_id);

CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_meta
    ON embeddings.runbook_embeddings USING GIN(meta);

-- Create indexes for runbooks table
CREATE INDEX IF NOT EXISTS idx_runbooks_tags
    ON sentinel.runbooks USING GIN(tags);

-- Create function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION sentinel.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for runbooks updated_at
CREATE TRIGGER update_runbooks_updated_at BEFORE UPDATE ON sentinel.runbooks
    FOR EACH ROW EXECUTE FUNCTION sentinel.update_updated_at_column();

-- Grant permissions
GRANT USAGE ON SCHEMA embeddings TO vectoradmin;
GRANT USAGE ON SCHEMA sentinel TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA embeddings TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA sentinel TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA embeddings TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA sentinel TO vectoradmin;

-- Create function for similarity search
CREATE OR REPLACE FUNCTION embeddings.search_similar_runbooks(
    query_embedding vector(3072),  -- Google Gemini embedding dimension
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    runbook_id UUID,
    content TEXT,
    similarity float,
    meta JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        re.id,
        re.runbook_id,
        re.content,
        1 - (re.embedding <=> query_embedding) as similarity,
        re.meta
    FROM embeddings.runbook_embeddings re
    WHERE 1 - (re.embedding <=> query_embedding) > match_threshold
    ORDER BY re.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
