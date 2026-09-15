-- Curated Zone: Canonical, enriched, and fully resolved data ready for analysis
-- Includes explicit revisit/rewatch tracking and full audit lineage.

CREATE TABLE IF NOT EXISTS curated_movies (
    movie_id TEXT PRIMARY KEY,
    
    -- External identifiers (unique constraints per source)
    tmdb_id INTEGER UNIQUE,
    wikidata_qid TEXT UNIQUE,
    wikipedia_url TEXT,
    wikipedia_page_id INTEGER,  -- enwiki curid; join key for the CMU corpus
    freebase_id TEXT,           -- /m/xxxxx; CMU's primary key (Freebase froze 2016)
    
    -- Core film metadata
    title TEXT NOT NULL,
    year INTEGER,
    directors TEXT,  -- JSON array of director names
    genres TEXT,     -- JSON array of genre strings
    keywords TEXT,   -- JSON array of TMDB keyword strings (thematic tags)
    runtime_minutes INTEGER,
    
    -- Enriched metadata from APIs
    rating_tmdb REAL,
    popularity_tmdb REAL,
    cast_names TEXT,  -- JSON array of top 10 cast members
    -- JSON array of TMDB person ids, positionally parallel to cast_names.
    -- Names are not a key: TMDB carries several distinct people called e.g.
    -- "Chris Evans", and every actor statistic in the app groups by name. This
    -- column is what lets curated_people be joined on the person rather than
    -- on a string that two people can share.
    cast_ids TEXT,
    plot_summary TEXT,           -- TMDB overview (~1 paragraph)
    -- Wikipedia plot section, whichever of its two vintages is longer (see
    -- 12_enrich_plot_summaries): the CMU corpus's Nov 2012 text, markup
    -- cleaned, or the live article's. _source says which; the other is still
    -- in raw_cmu_summaries / raw_wiki_articles.
    plot_summary_wiki TEXT,
    plot_summary_wiki_words INTEGER,
    plot_summary_wiki_source TEXT,   -- 'cmu_2012' | 'wikipedia_live'
    wikipedia_revid INTEGER,         -- live revision read, for plot AND themes; NULL if never fetched
    -- The article's themes/analysis section(s), where it has one (~1 film in 6).
    -- Critics' interpretation rather than plot, kept apart so nothing
    -- downstream mistakes a reading of a film for an event in it.
    themes_wiki TEXT,
    themes_wiki_heading TEXT,
    themes_wiki_words INTEGER,

    -- Financials, from TMDB. Nominal USD as reported, NOT inflation-adjusted;
    -- the app adjusts at read time. TMDB returns 0 for "unknown" on both
    -- fields, which 09_enrich_metadata coerces to NULL -- a film whose budget
    -- nobody published must not read as a film that cost nothing.
    -- CMU (v_movie_cmu.box_office_revenue) carries revenue too, but its
    -- Freebase snapshot froze in 2012: coverage is ~92% before 2010 and 0%
    -- after 2019, so TMDB is the series to trust and CMU is the cross-check.
    budget_tmdb INTEGER,
    revenue_tmdb INTEGER,
    
    -- Media URLs
    poster_url_tmdb TEXT,
    
    -- Source and provenance tracking
    data_sources JSONB,  -- {"tmdb": "2024-06-19T10:30Z", "wiki": "2024-06-19T11:15Z", ...}
    enriched_at TIMESTAMP,
    
    -- Revisit analytics (denormalized for fast queries)
    first_episode_date DATE,  -- When this movie was first discussed
    last_episode_date DATE,   -- Most recent discussion
    total_episodes_featured INTEGER DEFAULT 1,  -- distinct episodes, not airings
    revisit_count INTEGER DEFAULT 0,            -- derived: distinct episodes - 1

    -- Curated ground truth from the source sheet's `revisited` column, carried
    -- through raw -> staging unchanged. This is what the app displays.
    -- `revisit_count` is derived independently from episode numbering; the two
    -- must agree, and 06_build_curated logs any film where they don't.
    revisited_flag INTEGER,
    
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
    keywords TEXT,          -- JSON array of TMDB keyword strings
    runtime_minutes INTEGER,
    cast_names TEXT,        -- JSON array of top 10 cast members
    cast_ids TEXT,          -- JSON array of TMDB person ids, parallel to cast_names
    -- Set whenever the cast has been re-read for person ids and gender. Plays
    -- the same role as financials_cached_at below: rows cached before the cast
    -- carried ids read as a miss exactly once, then settle.
    cast_cached_at TIMESTAMP,
    plot_summary TEXT,
    poster_url_tmdb TEXT,
    budget_tmdb INTEGER,     -- nominal USD; 0 from the API is stored as NULL
    revenue_tmdb INTEGER,    -- nominal USD; 0 from the API is stored as NULL
    -- Set whenever the financial fields have been fetched, whether or not TMDB
    -- knew them. Without it a film with genuinely unknown revenue is
    -- indistinguishable from one never asked about, and would be refetched on
    -- every run forever.
    financials_cached_at TIMESTAMP,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- People dimension: one row per credited person, keyed on the stable TMDB
-- person id. Filled by 09_enrich_metadata from the `credits` sub-object of the
-- movie detail call it already makes, so it costs no extra API request.
--
-- Persistent, and deliberately NOT wiped by 06_build_curated -- same contract
-- as the two caches below. The rebuild clears curated_movies.cast_ids, but the
-- person rows those ids point at stay put, so gender survives a rebuild
-- without a refetch.
--
-- gender is TMDB's recorded gender for the performer, mapped from their
-- integer code (0 -> 'unknown', 1 -> 'F', 2 -> 'M', 3 -> 'NB'). 'unknown' is a
-- real value, stored rather than coerced: on a 15-film sample it was 1.3% of
-- billed credits, and folding it into either gender would quietly overstate
-- that one. gender_source records where the value came from, so a later CMU
-- backfill or a hand correction can be told apart from TMDB's answer -- and so
-- a 'manual' row is never overwritten by a refetch.
CREATE TABLE IF NOT EXISTS curated_people (
    tmdb_person_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT CHECK(gender IN ('F', 'M', 'NB', 'unknown')),
    gender_source TEXT CHECK(gender_source IN ('tmdb', 'cmu', 'manual')),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- The app resolves gender by name (every actor statistic groups by name), so
-- the name lookup is the hot path, not the primary key.
CREATE INDEX IF NOT EXISTS idx_curated_people_name ON curated_people(name);

-- External-ID bridge cache: persistent, keyed by the stable tmdb_id.
-- Same rationale as tmdb_metadata_cache -- the curated rebuild clears these
-- columns, and re-resolving costs one TMDB call plus Wikidata/Wikipedia
-- lookups per film. A row's existence = "already resolved"; individual columns
-- may legitimately be NULL (films after Freebase froze have no freebase_id).
CREATE TABLE IF NOT EXISTS external_id_cache (
    tmdb_id INTEGER PRIMARY KEY,
    wikidata_qid TEXT,
    freebase_id TEXT,
    wikipedia_page_id INTEGER,
    wikipedia_url TEXT,
    imdb_id TEXT,
    resolved INTEGER DEFAULT 1,  -- 1 once the 3-hop resolve has been attempted
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

-- ---------------------------------------------------------------------------
-- Curated movie <-> CMU corpus join.
--
-- IMPORTANT: the path is freebase_id -> raw_cmu_movies -> wikipedia_page_id ->
-- raw_cmu_summaries. Do NOT join curated_movies.wikipedia_page_id directly to
-- raw_cmu_summaries: CMU's page ids come from a Nov 2012 dump and some articles
-- have been recreated since (e.g. The Firm, Big), so a direct page-id join
-- silently drops those films. freebase_id is immutable -- Freebase froze in
-- 2016 -- which is why it is the primary key here.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_movie_cmu;
CREATE VIEW v_movie_cmu AS
SELECT
    m.movie_id,
    m.tmdb_id,
    m.title,
    m.year,
    m.freebase_id,
    cm.wikipedia_page_id  AS cmu_page_id,
    cm.name               AS cmu_name,
    cm.release_date       AS cmu_release_date,
    cm.box_office_revenue,
    cm.runtime            AS cmu_runtime,
    cm.genres             AS cmu_genres,
    cs.summary            AS plot_summary_wiki_raw,
    cs.word_count         AS plot_summary_wiki_raw_words
FROM curated_movies m
JOIN raw_cmu_movies cm
  ON cm.freebase_id = m.freebase_id
LEFT JOIN raw_cmu_summaries cs
  ON cs.wikipedia_page_id = cm.wikipedia_page_id;


-- ---------------------------------------------------------------------------
-- Cruise vs. Hanks segment.
--
-- "Who ya got -- Cruise or Hanks?" is a recurring end-of-episode bit: the room
-- picks which of the two stars would have been better in the film. The verdict
-- is a property of the EPISODE, not the film, so this view is episode-grained
-- and a film revisited later can carry a different verdict each time.
--
-- The bit is effectively a modern-era feature: 124 of the 125 verdicts are
-- ep 350 (Mar 2024) onward, where coverage is near-total. The lone earlier one
-- is ep 105. Filter on episode_number if you need the contiguous run.
--
-- IMPORTANT: the movie is joined via curated_episode_movies.episode_number, NOT
-- via staging_episodes.raw_episode_id. raw_episodes keeps one full copy per
-- ingest run and raw_episodes_current pins to the NEWEST run, while staging
-- still references the raw_episode_ids of whichever run last flowed through
-- 03_normalize. When those differ -- they do today -- the raw_episode_id path
-- joins to zero rows. episode_number is stable across snapshots.
--
-- Grain: one row per verdict episode. Verified 1:1 -- 125 rows, 125 distinct
-- episodes, no fan-out.
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS v_cruise_hanks;

CREATE VIEW v_cruise_hanks AS
SELECT
    CAST(re.ep AS INTEGER)  AS episode_number,
    re.episode_date,
    re.title                AS episode_title,
    re.cruise_hanks         AS verdict,
    re.host,
    re.guest1, re.guest2, re.guest3, re.guest4,
    re.tomatoes_score,
    re.ebert_stars,
    re.rating               AS episode_rating,
    cm.movie_id,
    cm.tmdb_id,
    cm.title                AS movie_title,
    cm.year                 AS movie_year,
    (cm.year / 10) * 10     AS movie_decade,
    cm.genres,
    cm.directors,
    cm.runtime_minutes,
    cm.rating_tmdb,
    cm.poster_url_tmdb,
    cem.is_revisit,
    cem.revisit_sequence
FROM raw_episodes_current re
LEFT JOIN curated_episode_movies cem
       ON cem.episode_number = CAST(re.ep AS INTEGER)
LEFT JOIN curated_movies cm
       ON cm.movie_id = cem.movie_id
WHERE re.cruise_hanks IN ('Cruise', 'Hanks', 'Tie');

-- ---------------------------------------------------------------------------
-- curated_upcoming_films -- films expected in future episodes
--
-- Built by 13_build_upcoming.py from raw_upcoming_films_current, resolved
-- against TMDB through the same tmdb_search_cache the episode path uses, and
-- enriched from the same tmdb_metadata_cache. Nothing here re-queries an id
-- either cache already holds.
--
-- WHY A SEPARATE TABLE, not a status column on curated_movies. Every section of
-- the app and most of the test suite reads curated_movies as "films that have
-- aired": the Films KPI, the decade histogram, keyword reach, the box-office
-- leaderboards and all of the revisit analytics. Adding 214 rows that were
-- never on the show would silently move all of them. The join costs one query;
-- the alternative costs a correctness audit of ten sections.
--
-- THE OVERLAP RULE. A flagged film that becomes a real episode must stop being
-- a flagged film. That match is made on tmdb_id, resolved independently on both
-- sides -- NEVER on title. Measured against the catalogue, title matching finds
-- seven pairs and is wrong about four of them:
--
--     Apollo 13 (1995)             = Apollo 13 (1995)         graduated
--     The Sure Thing (1985)        = The Sure Thing (1985)    graduated
--     Toy Story (1995)             = Toy Story (1995)         graduated
--     Crash (1996)                != Crash (2005)             Cronenberg/Haggis
--     Heat (w/ Burt Reynolds) 1987 != Heat (1995)             different films
--     Miami Vice (TV series)       != Miami Vice (2006)       series, not film
--     Miami Vice (2027)            != Miami Vice (2006)       different films
--
-- A graduate is MARKED, not deleted: superseded_by_movie_id points at the
-- curated_movies row that absorbed it, and superseded_at records when. The app
-- excludes those rows from the main grid -- the requirement -- but can still
-- show that the transition happened, and a test can assert on it. A row deleted
-- instead would make the rule invisible the moment it fired.
--
-- Films the resolver could not place (a TV series, a film with no year) carry a
-- NULL tmdb_id. They can never falsely graduate, which is the safe direction to
-- fail in: the cost is a card with no poster, not a real entry disappearing.
--
-- Rebuilt from raw on every run, like the rest of the curated zone.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS curated_upcoming_films (
    upcoming_film_id TEXT PRIMARY KEY,   -- uuid5 of title|year, see _keys.py

    -- Source fields
    title TEXT NOT NULL,
    year_raw TEXT,               -- as written, including ranges and blanks
    year INTEGER,                -- parsed, NULL when the raw value is not a year
    contributor TEXT,
    mention_note TEXT,
    pitch_tags TEXT,             -- comma-separated, as written

    -- Resolution against TMDB
    tmdb_id INTEGER,
    resolution_method TEXT CHECK(resolution_method IN (
        'auto_tmdb', 'unresolved_no_year', 'unresolved_no_match',
        'unresolved_low_confidence', 'unresolved_error')),
    confidence_score REAL,
    candidate_json TEXT,         -- raw TMDB candidates, for a later review pass

    -- Metadata, from tmdb_metadata_cache (same payload as curated_movies)
    genres TEXT,                 -- JSON array
    keywords TEXT,               -- JSON array
    runtime_minutes INTEGER,
    cast_names TEXT,             -- JSON array
    plot_summary TEXT,
    poster_url_tmdb TEXT,
    rating_tmdb REAL,
    directors TEXT,              -- JSON array

    -- The overlap rule. Both NULL for a film still waiting.
    superseded_by_movie_id TEXT,
    superseded_at TIMESTAMP,

    source_row_number INTEGER,   -- position in the source list, for stable order
    built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (superseded_by_movie_id) REFERENCES curated_movies(movie_id)
);

CREATE INDEX IF NOT EXISTS idx_upcoming_tmdb ON curated_upcoming_films(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_upcoming_superseded
    ON curated_upcoming_films(superseded_by_movie_id);

-- The films still waiting: everything the app's main grid shows. Reading this
-- rather than filtering by hand is what keeps "already made" from leaking back
-- into a count somewhere.
DROP VIEW IF EXISTS v_upcoming_pending;

CREATE VIEW v_upcoming_pending AS
SELECT * FROM curated_upcoming_films
WHERE superseded_by_movie_id IS NULL;

-- The graduates, with the episode they graduated into. first_episode_date is
-- the answer to "when did this stop being a request?".
DROP VIEW IF EXISTS v_upcoming_graduated;

CREATE VIEW v_upcoming_graduated AS
SELECT
    u.upcoming_film_id,
    u.title              AS requested_title,
    u.year_raw,
    u.contributor,
    u.mention_note,
    u.pitch_tags,
    u.superseded_at,
    m.movie_id,
    m.title              AS movie_title,
    m.year               AS movie_year,
    m.poster_url_tmdb,
    m.first_episode_date,
    m.total_episodes_featured
FROM curated_upcoming_films u
JOIN curated_movies m ON m.movie_id = u.superseded_by_movie_id;
