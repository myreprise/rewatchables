-- Curated Zone: Canonical, enriched, and fully resolved data ready for analysis
-- Includes explicit revisit/rewatch tracking and full audit lineage.

CREATE TABLE IF NOT EXISTS curated_movies (
    movie_id TEXT PRIMARY KEY,
    
    -- External identifiers (unique constraints per source)
    tmdb_id INTEGER UNIQUE,
    wikidata_qid TEXT UNIQUE,
    wikipedia_url TEXT,
    
    -- Core film metadata
    title TEXT NOT NULL,
    year INTEGER,
    directors TEXT,  -- JSON array of director names
    genres TEXT,     -- JSON array of genre strings
    runtime_minutes INTEGER,
    
    -- Enriched metadata from APIs
    rating_tmdb REAL,
    popularity_tmdb REAL,
    cast_names TEXT,  -- JSON array of top 10 cast members
    plot_summary TEXT,
    
    -- Media URLs
    poster_url_tmdb TEXT,
    
    -- Source and provenance tracking
    data_sources JSONB,  -- {"tmdb": "2024-06-19T10:30Z", "wiki": "2024-06-19T11:15Z", ...}
    enriched_at TIMESTAMP,
    
    -- Revisit analytics (denormalized for fast queries)
    first_episode_date DATE,  -- When this movie was first discussed
    last_episode_date DATE,   -- Most recent discussion
    total_episodes_featured INTEGER DEFAULT 1,
    revisit_count INTEGER DEFAULT 0,
    
    -- Confidence and resolution metadata
    canonical_key_confidence TEXT CHECK(canonical_key_confidence IN ('high', 'medium', 'low')),
    unresolved_reason TEXT,  -- Why if confidence is low
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_curated_movies_tmdb ON curated_movies(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_curated_movies_wikidata ON curated_movies(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_curated_movies_title ON curated_movies(title);

-- TMDB metadata cache: persistent, keyed by the stable tmdb_id.
-- The curated zone is wiped and rebuilt from staging on every run, which clears
-- the enriched metadata columns on curated_movies. This cache is NEVER cleared
-- by the rebuild, so 09_enrich_metadata can refill those columns from here
-- instead of re-calling TMDB. A row's existence = "already fetched"; individual
-- columns may legitimately be NULL (e.g. a film with no poster).
CREATE TABLE IF NOT EXISTS tmdb_metadata_cache (
    tmdb_id INTEGER PRIMARY KEY,
    genres TEXT,            -- JSON array of genre strings
    runtime_minutes INTEGER,
    cast_names TEXT,        -- JSON array of top 10 cast members
    plot_summary TEXT,
    poster_url_tmdb TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Episode-to-Movie facts: allows same movie across multiple episodes
-- This is where revisits are explicitly modeled
CREATE TABLE IF NOT EXISTS curated_episode_movies (
    episode_movie_id TEXT PRIMARY KEY,
    
    -- Foreign keys
    staging_episode_id TEXT NOT NULL,
    movie_id TEXT NOT NULL,
    
    -- Episode context
    episode_number INTEGER NOT NULL,
    episode_date DATE NOT NULL,
    episode_title TEXT,
    
    -- Mention context
    mention_order INTEGER NOT NULL,  -- Position of this movie mention in episode
    mention_type TEXT DEFAULT 'central_topic'
        CHECK(mention_type IN ('central_topic', 'compared_to', 'mentioned_in_passing')),
    
    -- Revisit tracking (explicit)
    is_revisit BOOLEAN DEFAULT 0,
    revisit_sequence INTEGER DEFAULT 1,  -- 1 = first episode, 2+ = rewatch number
    revisit_type TEXT,  -- e.g., 'regular_revisit', 'special_edition', 'mini_rewatch'
    
    -- Audit trail
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'enrichment_pipeline',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (staging_episode_id) REFERENCES staging_episodes(staging_episode_id),
    FOREIGN KEY (movie_id) REFERENCES curated_movies(movie_id),
    
    -- Prevent accidental duplicate (same episode, same movie)
    -- but allow revisits (same movie, different episodes)
    UNIQUE(staging_episode_id, movie_id)
);

CREATE INDEX IF NOT EXISTS idx_episode_movies_movie_id ON curated_episode_movies(movie_id);
CREATE INDEX IF NOT EXISTS idx_episode_movies_episode_date ON curated_episode_movies(episode_date);
CREATE INDEX IF NOT EXISTS idx_episode_movies_is_revisit ON curated_episode_movies(is_revisit);
CREATE INDEX IF NOT EXISTS idx_episode_movies_revisit_sequence ON curated_episode_movies(revisit_sequence);

-- Immutable audit trail: every enrichment decision
CREATE TABLE IF NOT EXISTS curated_audits (
    audit_id TEXT PRIMARY KEY,
    
    -- What changed
    movie_id TEXT,
    field_changed TEXT,
    old_value TEXT,
    new_value TEXT,
    
    -- How and why
    enriched_from TEXT,  -- 'tmdb', 'wiki', 'wikidata', 'manual', 'system'
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    enriched_by TEXT,    -- 'automation_v1', 'human:user@example.com', 'system_migration'
    
    -- Approval workflow
    approved_by TEXT,
    approved_at TIMESTAMP,
    approval_notes TEXT,
    
    FOREIGN KEY (movie_id) REFERENCES curated_movies(movie_id)
);

CREATE INDEX IF NOT EXISTS idx_audits_movie_id ON curated_audits(movie_id);
CREATE INDEX IF NOT EXISTS idx_audits_timestamp ON curated_audits(enriched_at);

-- Operational: API call log for rate limit and performance monitoring
CREATE TABLE IF NOT EXISTS api_call_log (
    call_id TEXT PRIMARY KEY,
    api_source TEXT NOT NULL CHECK(api_source IN ('tmdb', 'wiki', 'wikidata')),
    query_text TEXT,
    response_status_code INTEGER,
    response_time_ms INTEGER,
    rate_limit_remaining INTEGER,
    called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_call_log_source ON api_call_log(api_source);
CREATE INDEX IF NOT EXISTS idx_api_call_log_timestamp ON api_call_log(called_at);

-- Operational: Manual review queue
CREATE TABLE IF NOT EXISTS manual_review_queue (
    review_id TEXT PRIMARY KEY,
    
    staging_mention_id TEXT NOT NULL,
    movie_title_raw TEXT,
    year_parsed INTEGER,
    director_raw TEXT,
    
    -- Candidates to choose from (JSON)
    candidates JSONB NOT NULL,
    
    -- Workflow
    queue_status TEXT DEFAULT 'pending' 
        CHECK(queue_status IN ('pending', 'in_review', 'approved', 'rejected', 'deferred')),
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Resolution
    reviewer_name TEXT,
    approved_movie_id TEXT,
    approval_notes TEXT,
    resolved_at TIMESTAMP,
    
    FOREIGN KEY (staging_mention_id) REFERENCES staging_movie_mentions(staging_mention_id),
    FOREIGN KEY (approved_movie_id) REFERENCES curated_movies(movie_id)
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON manual_review_queue(queue_status);
CREATE INDEX IF NOT EXISTS idx_review_queue_queued_at ON manual_review_queue(queued_at);

-- Data Quality Results: track metrics per run
CREATE TABLE IF NOT EXISTS data_quality_results (
    quality_run_id TEXT PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Counts
    total_episodes_processed INTEGER,
    total_movie_mentions INTEGER,
    resolved_mentions INTEGER,
    unresolved_mentions INTEGER,
    high_confidence_count INTEGER,
    medium_confidence_count INTEGER,
    low_confidence_count INTEGER,
    
    -- Percentages
    resolution_rate_pct REAL,
    high_confidence_pct REAL,
    
    -- Revisits
    new_movies INTEGER,
    revisited_movies INTEGER,
    
    -- Issues
    validation_failures INTEGER,
    api_errors INTEGER,
    
    -- Summary
    run_status TEXT CHECK(run_status IN ('success', 'partial', 'failed')),
    summary_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_quality_results_timestamp ON data_quality_results(run_timestamp);
