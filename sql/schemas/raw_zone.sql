-- Raw Zone: Immutable source data snapshots from Google Sheets
-- All timestamps in UTC. No transformations applied.

CREATE TABLE IF NOT EXISTS raw_ingest_runs (
    ingest_run_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    sync_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rows_ingested INTEGER,
    sync_status TEXT CHECK(sync_status IN ('success', 'partial', 'failed')),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw_episodes (
    raw_episode_id TEXT PRIMARY KEY,
    ingest_run_id TEXT NOT NULL,
    
    -- Raw columns from Google Sheets (exact names)
    ep TEXT,
    ep_ex_1999 TEXT,
    title TEXT,
    date TEXT,
    host TEXT,
    guest1 TEXT,
    guest2 TEXT,
    guest3 TEXT,
    guest4 TEXT,
    year TEXT,
    genre TEXT,
    director TEXT,
    ebert TEXT,
    tomatoes_score TEXT,
    cruise_hanks TEXT,
    notes TEXT,
    rating TEXT,
    is_film TEXT,
    ebert_stars TEXT,
    
    -- Metadata for change detection and auditability
    source_hash TEXT NOT NULL,
    gs_row_number INTEGER,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (ingest_run_id) REFERENCES raw_ingest_runs(ingest_run_id),
    UNIQUE(ingest_run_id, source_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_episodes_ingest_run ON raw_episodes(ingest_run_id);
CREATE INDEX IF NOT EXISTS idx_raw_episodes_date ON raw_episodes(date);
