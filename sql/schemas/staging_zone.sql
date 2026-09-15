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

    -- Curated `revisited` flag carried verbatim from raw_episodes. Lives on the
    -- mention rather than the episode because it describes the film, and the
    -- mention is what survives the group-by tmdb_id in 06_build_curated.
    revisited_flag INTEGER,
    
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

-- ---------------------------------------------------------------------------
-- tmdb_search_cache -- persistent memory of every TMDB /search/movie call
--
-- 03_normalize clears staging and 04_enrich re-resolves every mention from
-- 'unresolved', so before this table a rebuild re-searched all ~481 films:
-- roughly four minutes of wall clock and, historically, 3,340 logged calls for
-- 481 distinct titles. The cache makes a full rebuild cost zero calls; only a
-- genuinely new title reaches the network.
--
-- It stores the RAW candidate list, before scoring. Scoring and the
-- auto-resolve threshold stay live in 04, so changing MATCH_YEAR_WINDOW or
-- MATCH_CONFIDENCE_THRESHOLD re-derives every resolution from cache without
-- re-querying TMDB. Caching the scored result would have frozen the tuning
-- parameters into the stored rows.
--
-- An empty result is cached too (result_count = 0). A title TMDB has no match
-- for is exactly the one that would otherwise be re-queried on every single
-- run, and its emptiness is as stable as any hit.
--
-- Keyed on the NORMALIZED title, because that is what 04's scorer compares --
-- same key implies same scoring implies same outcome. The year is folded into
-- the key rather than kept as its own column: SQLite treats NULLs as distinct
-- in a unique index, so a nullable year column would let unyeared searches
-- insert a duplicate row on every run.
--
-- Staleness is not tracked. TMDB search results for a 30-year-old film do not
-- move, and 04 --refresh re-fetches when something does.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tmdb_search_cache (
    cache_key TEXT PRIMARY KEY,     -- '<normalized title>|<year>' ('' year = unyeared)
    query_title TEXT NOT NULL,      -- the string actually sent to TMDB
    query_year INTEGER,             -- NULL when the search carried no year
    candidates_json TEXT NOT NULL,  -- raw TMDB candidates (top 5), pre-scoring
    result_count INTEGER NOT NULL,  -- 0 is a real, cacheable answer
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
