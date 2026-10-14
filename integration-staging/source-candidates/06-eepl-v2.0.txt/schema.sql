-- schema.sql
-- PostgreSQL + pgvector required

CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    usi_vector JSONB NOT NULL,               -- style vector as list of floats
    negative_preferences JSONB NOT NULL,
    cultural_constraints JSONB NOT NULL,
    location JSONB,
    style_history JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    engagement_rate FLOAT NOT NULL,
    exploration_rate FLOAT NOT NULL,
    archetype VARCHAR(100) NOT NULL
);

-- Items table with environmental attributes
CREATE TABLE items (
    item_id UUID PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    features JSONB NOT NULL,
    embedding vector(128) NOT NULL,           -- pgvector type, dimension 128
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    revival_score FLOAT NOT NULL,
    trend_score FLOAT NOT NULL,
    climate_compatibility JSONB NOT NULL,
    confidence FLOAT NOT NULL,
    thermal_rating FLOAT NOT NULL,
    water_resistance FLOAT NOT NULL,
    uv_protection FLOAT NOT NULL,
    breathability FLOAT NOT NULL,
    wind_resistance FLOAT NOT NULL
);

-- Segment priors table
CREATE TABLE segment_priors (
    segment_id VARCHAR(100) PRIMARY KEY,
    embedding JSONB NOT NULL,                  -- list of floats
    confidence FLOAT NOT NULL,
    variance FLOAT NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    sample_size INTEGER NOT NULL
);

-- Style snapshots table
CREATE TABLE style_snapshots (
    user_id UUID NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    dominant_style_embedding JSONB NOT NULL,
    confidence_trend FLOAT NOT NULL,
    revival_trend FLOAT NOT NULL,
    PRIMARY KEY (user_id, timestamp)
);

-- Optional indexes for vector similarity (pgvector)
CREATE INDEX idx_items_embedding ON items USING ivfflat (embedding vector_cosine_ops);
