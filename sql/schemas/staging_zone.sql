-- Staging Zone: Normalized and parsed data from raw, with resolution candidates
-- This zone is where movies get matched to external APIs and candidates are ranked.

CREATE TABLE IF NOT EXISTS staging_episodes (
    staging_episode_id TEXT PRIMARY KEY,
    raw_episode_id TEXT UNIQUE NOT NULL,
    
    -- Parsed and normalized episode data
    episode_number INTEGER,
    episode_date DATE,
    episode_title TEXT,
    
    -- Normalized host/guest structure (optional: parse from raw)
    host_primary TEXT,
    guest_count INTEGER,
    
    -- Quality indicators
    validation_status TEXT DEFAULT 'pending' CHECK(validation_status IN ('pass', 'warning', 'fail', 'pending')),
    validation_notes TEXT,
    
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_episode_id) REFERENCES raw_episodes(raw_episode_id)
);

CREATE TABLE IF NOT EXISTS staging_movie_mentions (
    staging_mention_id TEXT PRIMARY KEY,
    staging_episode_id TEXT NOT NULL,
    raw_episode_id TEXT NOT NULL,
    
    -- Mention details
    mention_order INTEGER NOT NULL,  -- 1st mention, 2nd mention, etc. in episode
    title_raw TEXT NOT NULL,
    title_normalized TEXT,
    year_raw TEXT,
    year_parsed INTEGER,
    director_raw TEXT,
    director_normalized TEXT,
    
    -- Resolution process tracking
    resolution_method TEXT DEFAULT 'unresolved' 
        CHECK(resolution_method IN ('exact_tmdb', 'fuzzy_tmdb', 'year_window_tmdb', 'wiki_match', 'wikidata_match', 'unresolved', 'manual_approved')),
    confidence_score REAL DEFAULT 0.0,  -- 0.0 to 1.0
    
    -- Resolved external IDs (from API matching or manual review)
    tmdb_id INTEGER,
    wikidata_qid TEXT,
    wikipedia_url TEXT,
    
    -- Resolution candidates for manual review
    candidate_json TEXT,  -- JSON array of top N matches with confidence scores
    resolution_notes TEXT,
    
    -- Quality flags
    requires_manual_review BOOLEAN DEFAULT 0,
    manual_review_approver TEXT,
    manual_review_timestamp TIMESTAMP,
    
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staging_episode_id) REFERENCES staging_episodes(staging_episode_id),
    FOREIGN KEY (raw_episode_id) REFERENCES raw_episodes(raw_episode_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_mentions_unique 
    ON staging_movie_mentions(staging_episode_id, mention_order);
CREATE INDEX IF NOT EXISTS idx_staging_mentions_resolution 
    ON staging_movie_mentions(resolution_method, confidence_score);
CREATE INDEX IF NOT EXISTS idx_staging_mentions_manual_review 
    ON staging_movie_mentions(requires_manual_review);
