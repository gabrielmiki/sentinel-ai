-- PostgreSQL initialization script for SentinelAI application database

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schema for application
CREATE SCHEMA IF NOT EXISTS sentinel;

-- Set search path
SET search_path TO sentinel, public;

-- Create users table
CREATE TABLE IF NOT EXISTS sentinel.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create incidents table
CREATE TABLE IF NOT EXISTS sentinel.incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'open',
    created_by UUID REFERENCES sentinel.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Create agent_runs table for tracking agentic graph executions
CREATE TABLE IF NOT EXISTS sentinel.agent_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID REFERENCES sentinel.incidents(id),
    status VARCHAR(50) NOT NULL,
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER
);

-- Create runbooks table
CREATE TABLE IF NOT EXISTS sentinel.runbooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    tags VARCHAR(100)[],
    category VARCHAR(100),
    created_by UUID REFERENCES sentinel.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_incidents_status ON sentinel.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON sentinel.incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON sentinel.incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON sentinel.agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_incident_id ON sentinel.agent_runs(incident_id);
CREATE INDEX IF NOT EXISTS idx_runbooks_tags ON sentinel.runbooks USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_runbooks_content_trgm ON sentinel.runbooks USING GIN(content gin_trgm_ops);

-- Create function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION sentinel.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON sentinel.users
    FOR EACH ROW EXECUTE FUNCTION sentinel.update_updated_at_column();

CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON sentinel.incidents
    FOR EACH ROW EXECUTE FUNCTION sentinel.update_updated_at_column();

CREATE TRIGGER update_runbooks_updated_at BEFORE UPDATE ON sentinel.runbooks
    FOR EACH ROW EXECUTE FUNCTION sentinel.update_updated_at_column();

-- Grant permissions
GRANT USAGE ON SCHEMA sentinel TO sentinel;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA sentinel TO sentinel;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA sentinel TO sentinel;

-- Insert default admin user (password: admin123 - CHANGE IN PRODUCTION!)
-- Password hash for 'admin123' using bcrypt
INSERT INTO sentinel.users (username, email, hashed_password, is_superuser)
VALUES (
    'admin',
    'admin@sentinel.ai',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqW.jYL7K2',
    TRUE
) ON CONFLICT (username) DO NOTHING;
