CREATE TABLE IF NOT EXISTS monitored_sources (
    source_id text PRIMARY KEY,
    name text NOT NULL,
    source_type text NOT NULL,
    engine text NOT NULL,
    environment text NOT NULL,
    host text,
    port integer,
    database_name text,
    username text,
    cloud_provider text NOT NULL DEFAULT 'none',
    telemetry_provider text NOT NULL DEFAULT 'none',
    status text NOT NULL DEFAULT 'pending',
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_metric_snapshots (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL REFERENCES monitored_sources(source_id) ON DELETE CASCADE,
    captured_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL,
    health_score integer NOT NULL,
    latency_ms numeric(12, 2),
    active_connections integer,
    total_connections integer,
    idle_connections integer,
    database_size_bytes bigint,
    tables_count integer,
    locks_count integer,
    cache_hit_ratio numeric(10, 4),
    xact_commit bigint,
    xact_rollback bigint,
    deadlocks bigint,
    error text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS table_inventory_snapshots (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL REFERENCES monitored_sources(source_id) ON DELETE CASCADE,
    captured_at timestamptz NOT NULL DEFAULT now(),
    schema_name text NOT NULL,
    table_name text NOT NULL,
    estimated_rows bigint,
    size_bytes bigint,
    table_type text NOT NULL DEFAULT 'table'
);

CREATE TABLE IF NOT EXISTS recommendation_events (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL REFERENCES monitored_sources(source_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    severity text NOT NULL,
    category text NOT NULL,
    title text NOT NULL,
    recommendation text NOT NULL,
    evidence text NOT NULL,
    action_type text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_metric_snapshots_source_time
    ON source_metric_snapshots (source_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_table_inventory_snapshots_source_time
    ON table_inventory_snapshots (source_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_events_source_time
    ON recommendation_events (source_id, created_at DESC);
