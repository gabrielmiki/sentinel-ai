-- PostgreSQL initialization script for vector database (pgvector)

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schema for embeddings
CREATE SCHEMA IF NOT EXISTS embeddings;

SET search_path TO embeddings, public;

-- Create table for runbook embeddings
CREATE TABLE IF NOT EXISTS embeddings.runbook_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runbook_id UUID NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 dimension
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create table for incident embeddings
CREATE TABLE IF NOT EXISTS embeddings.incident_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for vector similarity search
CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_vector
    ON embeddings.runbook_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_incident_embeddings_vector
    ON embeddings.incident_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create indexes for filtering
CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_runbook_id
    ON embeddings.runbook_embeddings(runbook_id);

CREATE INDEX IF NOT EXISTS idx_incident_embeddings_incident_id
    ON embeddings.incident_embeddings(incident_id);

CREATE INDEX IF NOT EXISTS idx_runbook_embeddings_metadata
    ON embeddings.runbook_embeddings USING GIN(metadata);

-- Grant permissions
GRANT USAGE ON SCHEMA embeddings TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA embeddings TO vectoradmin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA embeddings TO vectoradmin;

-- Create function for similarity search
CREATE OR REPLACE FUNCTION embeddings.search_similar_runbooks(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    runbook_id UUID,
    content TEXT,
    similarity float,
    metadata JSONB
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
        re.metadata
    FROM embeddings.runbook_embeddings re
    WHERE 1 - (re.embedding <=> query_embedding) > match_threshold
    ORDER BY re.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
