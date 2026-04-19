-- TimescaleDB schema for PM interaction tracking and ECEF cognitive modeling

-- Core interaction table (hypertable for time-series optimisation)
CREATE TABLE IF NOT EXISTS pm_interactions (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT NOT NULL,
    pm_sub TEXT NOT NULL,
    pm_desk TEXT[],
    tool_name TEXT NOT NULL,
    tool_server TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}',
    result_summary TEXT,
    latency_ms INTEGER,
    preceding_tool TEXT,
    preceding_interval_ms INTEGER,
    context_tags TEXT[],
    PRIMARY KEY (id, timestamp)
);

SELECT create_hypertable('pm_interactions', 'timestamp', if_not_exists => TRUE);

-- Indexes for pattern queries
CREATE INDEX IF NOT EXISTS idx_pm_interactions_sub ON pm_interactions (pm_sub, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pm_interactions_tool ON pm_interactions (tool_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pm_interactions_session ON pm_interactions (session_id, timestamp ASC);

-- Heuristic models (ECEF output)
CREATE TABLE IF NOT EXISTS pm_heuristic_models (
    id BIGSERIAL PRIMARY KEY,
    pm_sub TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    transitions JSONB NOT NULL DEFAULT '{}',
    triggers JSONB NOT NULL DEFAULT '[]',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    convergence_gap DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    iteration_count INTEGER NOT NULL DEFAULT 0,
    training_window_size INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pm_sub, version)
);

CREATE INDEX IF NOT EXISTS idx_heuristic_pm ON pm_heuristic_models (pm_sub, version DESC);

-- Continuous aggregate: tool transition matrix per PM (hourly rollup)
CREATE MATERIALIZED VIEW IF NOT EXISTS pm_tool_transitions
WITH (timescaledb.continuous) AS
SELECT
    pm_sub,
    tool_name AS from_tool,
    time_bucket('1 hour', timestamp) AS bucket,
    COUNT(*) AS call_count
FROM pm_interactions
GROUP BY pm_sub, tool_name, bucket
WITH NO DATA;

-- Continuous aggregate: PM daily usage patterns
CREATE MATERIALIZED VIEW IF NOT EXISTS pm_daily_usage
WITH (timescaledb.continuous) AS
SELECT
    pm_sub,
    tool_name,
    time_bucket('1 day', timestamp) AS day,
    COUNT(*) AS call_count,
    AVG(latency_ms) AS avg_latency
FROM pm_interactions
GROUP BY pm_sub, tool_name, day
WITH NO DATA;
