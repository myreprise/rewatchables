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

    -- Curated ground truth: 1 = this film has been revisited in a later
    -- episode, 0 = not. Film-level (every row for a film carries the same
    -- value), so it identifies WHICH films were revisited, not which airing
    -- was the revisit -- the chronology still comes from episode ordering.
    revisited TEXT,
    
    -- Identity and change detection.
    --
    -- episode_key is the airing's business key (ep|ISO date|title), computed by
    -- scripts/_keys.py -- see that module for why those three fields. It is what
    -- makes a load an upsert: a row whose key AND content are unchanged is
    -- recognised and skipped rather than re-inserted.
    --
    -- source_hash covers every source column, so a row that comes back edited
    -- hashes differently and is stored as a NEW version alongside the old one.
    -- The raw zone stays append-only; it just stops appending rows that say
    -- nothing new.
    episode_key TEXT,
    source_hash TEXT NOT NULL,
    gs_row_number INTEGER,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Provenance of the row's lifespan. ingest_run_id is the load that first
    -- introduced this version; last_seen_* is the most recent load that still
    -- found it in the source.
    --
    -- These are the only columns a later load may write to an existing row, and
    -- they are provenance, not source data -- the ingested values themselves are
    -- never touched. They exist so that a row DELETED from the sheet can be
    -- recognised: it simply stops being re-seen, and drops out of
    -- raw_episodes_current without anything having to remember it was there.
    last_seen_ingest_run_id TEXT,
    last_seen_at TIMESTAMP,

    FOREIGN KEY (ingest_run_id) REFERENCES raw_ingest_runs(ingest_run_id),
    UNIQUE(ingest_run_id, source_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_episodes_ingest_run ON raw_episodes(ingest_run_id);
CREATE INDEX IF NOT EXISTS idx_raw_episodes_date ON raw_episodes(date);

-- One stored row per (airing, version). This is what makes the load idempotent:
-- re-running it against an unchanged sheet inserts nothing.
--
-- Databases created before the upsert hold one copy of every row per ingest run
-- and CANNOT take this index until they are compacted; run
-- scripts/migrate_compact_raw_zone.py, which deduplicates and then creates it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_episodes_version
    ON raw_episodes(episode_key, source_hash);
CREATE INDEX IF NOT EXISTS idx_raw_episodes_last_seen
    ON raw_episodes(last_seen_ingest_run_id);

-- ---------------------------------------------------------------------------
-- raw_episodes_current -- one row per airing, as the source last had it
--
-- raw_episodes is append-only version history: an airing that comes back edited
-- gets a second row rather than overwriting the first. Query this view instead
-- of the table unless you genuinely want that history.
--
-- "Current" means last seen by the most recent load, which resolves all three
-- cases at once:
--   * unchanged  -- the row was re-seen, so its last_seen advances; still current
--   * edited     -- the new version is the one re-seen; the old version's
--                   last_seen stays behind and it drops out
--   * deleted    -- nothing re-sees it, so it falls out on its own
--
-- The alternative selector, "rows belonging to the newest ingest run", only
-- works while every load re-inserts the entire sheet. Once loads are upserts an
-- unchanged row belongs to the run that first saw it, months ago, and that
-- selector would return only the handful of rows edited in the last load.
--
-- 03_normalize reads THIS VIEW rather than re-deriving the selector, so the raw
-- zone and the staging zone cannot disagree about what is current.
--
-- Do NOT deduplicate on `ep` instead. A revisit reuses the original episode
-- number, so the 481 current airings span only 471 distinct numbers; grouping
-- on `ep` silently drops every revisit -- the exact rows the Revisits analysis
-- depends on.
--
-- Known gap: this does not filter on raw_ingest_runs.sync_status, so a
-- 'partial' or 'failed' run would become "current".
--
-- Raw-zone fidelity is preserved -- `date` passes through exactly as ingested.
-- `episode_date` is added beside it, normalising to ISO the M/D/YYYY values the
-- source sheet mixes in with timestamps (17 of 481 at the time of writing).
-- Those values silently became NaT in pandas and dropped the most recent
-- episodes from every time series, so consumers should prefer `episode_date`
-- rather than re-deriving the parse.
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS raw_episodes_current;

CREATE VIEW raw_episodes_current AS
WITH parts AS (
    SELECT
        re.*,
        -- Offsets of the two separators in an M/D/YYYY value; 0 when absent.
        instr(re.date, '/') AS slash1,
        instr(substr(re.date, instr(re.date, '/') + 1), '/') AS slash2
    FROM raw_episodes re
    WHERE re.last_seen_ingest_run_id = (
        SELECT ingest_run_id FROM raw_ingest_runs
        ORDER BY sync_timestamp DESC LIMIT 1
    )
)
SELECT
    raw_episode_id,
    ingest_run_id,
    ep,
    ep_ex_1999,
    title,
    date,
    CASE
        WHEN slash1 > 0 AND slash2 > 0 THEN printf(
            '%s-%02d-%02d',
            substr(substr(date, slash1 + 1), slash2 + 1),              -- year
            CAST(substr(date, 1, slash1 - 1) AS INTEGER),              -- month
            CAST(substr(substr(date, slash1 + 1), 1, slash2 - 1) AS INTEGER)
        )
        ELSE substr(date, 1, 10)
    END AS episode_date,
    host, guest1, guest2, guest3, guest4,
    year, genre, director,
    ebert, tomatoes_score, cruise_hanks,
    notes, rating, is_film, ebert_stars, revisited,
    episode_key,
    source_hash, gs_row_number, ingested_at,
    last_seen_ingest_run_id, last_seen_at
FROM parts;

-- ---------------------------------------------------------------------------
-- CMU Movie Summary Corpus (vendored subset)
--
-- Loaded from data/external/cmu/*.tsv by 11_load_cmu.py. This is a static
-- reference dataset -- a Nov 2012 snapshot of Wikipedia + Freebase -- not a
-- synced source, so it deliberately does NOT use raw_ingest_runs: 03_normalize
-- pins staging to the most recent row of that table, and a CMU load appearing
-- there would starve the episode rebuild. Loads are tracked separately.
--
-- Raw-zone fidelity: values are stored as they appear in the corpus, including
-- known-bad Freebase data (two actor DOBs imply negative ages). Filter
-- downstream rather than dropping rows here.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_cmu_loads (
    load_id TEXT PRIMARY KEY,
    source_url TEXT,
    tarball_sha256 TEXT,
    manifest_json TEXT,          -- the vendored manifest, for provenance
    movies_loaded INTEGER,
    summaries_loaded INTEGER,
    characters_loaded INTEGER,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_cmu_movies (
    wikipedia_page_id INTEGER PRIMARY KEY,   -- CMU's own key (Nov 2012 curid)
    freebase_id TEXT NOT NULL UNIQUE,        -- join key to curated_movies
    name TEXT,
    release_date TEXT,
    box_office_revenue INTEGER,
    runtime REAL,
    languages TEXT,   -- JSON object of freebase_id -> name, verbatim
    countries TEXT,
    genres TEXT,
    load_id TEXT,
    FOREIGN KEY (load_id) REFERENCES raw_cmu_loads(load_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_cmu_movies_fb ON raw_cmu_movies(freebase_id);

CREATE TABLE IF NOT EXISTS raw_cmu_summaries (
    wikipedia_page_id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,       -- verbatim, incl. {{template}}/[[wikilink]] residue
    word_count INTEGER,
    load_id TEXT,
    FOREIGN KEY (load_id) REFERENCES raw_cmu_loads(load_id)
);

CREATE TABLE IF NOT EXISTS raw_cmu_characters (
    fb_character_actor_map_id TEXT PRIMARY KEY,
    wikipedia_page_id INTEGER,
    freebase_id TEXT,
    release_date TEXT,
    character_name TEXT,
    actor_dob TEXT,
    actor_gender TEXT,           -- 'M', 'F', or NULL
    actor_height_m REAL,
    actor_ethnicity_fbid TEXT,   -- raw freebase id; only ~38% populated
    actor_name TEXT,
    actor_age_at_release INTEGER,
    fb_character_id TEXT,
    fb_actor_id TEXT,
    load_id TEXT,
    FOREIGN KEY (load_id) REFERENCES raw_cmu_loads(load_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_cmu_characters_fb ON raw_cmu_characters(freebase_id);
CREATE INDEX IF NOT EXISTS idx_raw_cmu_characters_actor ON raw_cmu_characters(actor_name);

-- ---------------------------------------------------------------------------
-- Live Wikipedia sections
--
-- The CMU corpus's live counterpart: the same articles, read from the MediaWiki
-- TextExtracts API by 12_enrich_plot_summaries.py, one request per film, keyed
-- on the article's CURRENT page id (curated_movies.wikipedia_page_id -- not
-- CMU's 2012 one). Only the sections the pipeline uses are kept, not the
-- article: the plot, and any themes/analysis section.
--
-- Neither vintage supersedes the other. Editors have since trimmed many
-- overlong 2012 plots and expanded many thin ones, so step 12 keeps whichever
-- is longer per film and both stay here verbatim.
--
-- Also the cache that lets step 12 re-run offline: 06_build_curated wipes
-- curated_movies, never this table. A row's existence = "already fetched";
-- plot_text is legitimately NULL for an article without a plot section, and
-- that film is not re-asked on every run. Step 12 --refresh re-fetches.
--
-- revid pins the revision the text was read from:
--   https://en.wikipedia.org/w/index.php?oldid=<revid>
-- Text is CC BY-SA, like the CMU corpus.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_wiki_articles (
    wikipedia_page_id INTEGER PRIMARY KEY,
    revid INTEGER,
    title TEXT,
    plot_heading TEXT,
    plot_text TEXT,              -- plain text incl. subsections; NULL if no plot section
    plot_words INTEGER,
    themes_heading TEXT,         -- '; '-joined when several sections match
    themes_text TEXT,
    themes_words INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Upcoming films -- the second source file
--
-- data/upcoming.csv lists films expected to be covered in future episodes,
-- contributed by listeners. Loaded by 13_build_upcoming.py. These are NOT
-- airings: no episode number, no date, and nothing to join to
-- curated_episode_movies. They live in their own tables the whole way down.
--
-- Loads are tracked in raw_upcoming_loads, NOT in raw_ingest_runs. This is the
-- same rule the CMU corpus follows above, and for the same reason:
-- raw_episodes_current pins to the most recent row of raw_ingest_runs, so an
-- upcoming-films load appearing there would make itself "the newest episode
-- snapshot" and starve every episode row out of the view -- and out of the app.
--
-- The upsert is identical in shape to raw_episodes: business key (title|year,
-- see scripts/_keys.py) plus source_hash over every column, with last_seen_*
-- provenance so a row removed from the list falls out on its own. A film that
-- graduates to a real episode is expected to be deleted from the source list
-- eventually, but the pipeline does not wait for that -- see
-- curated_upcoming_films.superseded_by_movie_id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_upcoming_loads (
    load_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rows_ingested INTEGER,
    load_status TEXT CHECK(load_status IN ('success', 'partial', 'failed'))
);

CREATE TABLE IF NOT EXISTS raw_upcoming_films (
    raw_upcoming_id TEXT PRIMARY KEY,
    load_id TEXT NOT NULL,

    -- Source columns, verbatim (see scripts/convert_xlsx_to_csv.py for how the
    -- sheet's three justification columns became these two).
    title TEXT,
    year TEXT,               -- text, not INTEGER: 2 rows are ranges, 1 is blank
    contributor TEXT,
    mention_note TEXT,       -- prose evidence the film was mentioned on air
    pitch_tags TEXT,         -- comma-separated pitch ("1980s, John Carpenter")

    upcoming_key TEXT,
    source_hash TEXT NOT NULL,
    source_row_number INTEGER,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    last_seen_load_id TEXT,
    last_seen_at TIMESTAMP,

    FOREIGN KEY (load_id) REFERENCES raw_upcoming_loads(load_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_upcoming_version
    ON raw_upcoming_films(upcoming_key, source_hash);
CREATE INDEX IF NOT EXISTS idx_raw_upcoming_last_seen
    ON raw_upcoming_films(last_seen_load_id);

-- One row per film, as the source list last had it. Same "last seen by the
-- most recent load" selector as raw_episodes_current, for the same three
-- reasons -- unchanged rows stay, edited rows are replaced by their new
-- version, deleted rows fall out.
DROP VIEW IF EXISTS raw_upcoming_films_current;

CREATE VIEW raw_upcoming_films_current AS
SELECT *
FROM raw_upcoming_films
WHERE last_seen_load_id = (
    SELECT load_id FROM raw_upcoming_loads
    WHERE load_status = 'success'
    ORDER BY loaded_at DESC LIMIT 1
);
