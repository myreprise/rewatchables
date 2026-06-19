# Rewatchables Movie Database

A secure, reproducible data pipeline for enriching podcast episode metadata with film information from public APIs (TMDB, Wikipedia, Wikidata). This system handles revisited movies correctly and maintains a complete audit trail of all enrichment decisions.

## Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp config/.env.template config/.env

# Fill in required API keys in config/.env
# - GOOGLE_SHEETS_WORKSHEET_ID (from your Google Sheet URL)
# - TMDB_API_KEY (register at https://www.themoviedb.org/settings/api)
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Pipeline

```bash
# Run full pipeline
python scripts/orchestrate.py

# Or run individual steps
python scripts/01_sync_sheets.py
python scripts/02_load_raw.py
python scripts/03_normalize_and_resolve.py
python scripts/04_enrich.py
python scripts/05_validate.py
```

## Architecture

### Data Flow

```
Google Sheets (source of truth)
    ↓
master.xlsx (local mirror)
    ↓
SQLite raw_zone (immutable snapshots)
    ↓
SQLite staging_zone (normalized + candidates)
    ↓
SQLite curated_zone (enriched + resolved)
    ↓
Analysis/Export
```

### Database Zones

#### Raw Zone
- **Purpose**: Immutable snapshots from Google Sheets
- **Tables**: `raw_episodes`, `raw_ingest_runs`
- **Key Fields**: Source hash for change detection, ingestion timestamp

#### Staging Zone
- **Purpose**: Parsed, normalized data with API resolution candidates
- **Tables**: `staging_episodes`, `staging_movie_mentions`
- **Key Fields**: Normalized titles, parsed years, confidence scores, candidate JSON

#### Curated Zone
- **Purpose**: Canonical, enriched data ready for analysis
- **Tables**:
  - `curated_movies`: One row per unique film (keyed by TMDB ID first, fallback to Wikidata/title+year)
  - `curated_episode_movies`: Fact table linking episodes to movies **with explicit revisit tracking**
  - `curated_audits`: Immutable log of all enrichment decisions
  - `api_call_log`: API performance and rate-limit monitoring
  - `manual_review_queue`: Movies awaiting human approval
  - `data_quality_results`: Quality metrics per pipeline run

## Revisited Movies (Critical)

The system correctly handles movies the podcast revisited:

1. **Canonical Movies**: Each film gets exactly one row in `curated_movies` (e.g., "Fight Club" appears once).

2. **Episode-Movie Links**: The `curated_episode_movies` table has one row per episode mention, even if it's the same film.

3. **Revisit Detection**: Rows are marked with:
   - `is_revisit`: boolean (true = movie discussed in prior episode)
   - `revisit_sequence`: integer (1 = first episode, 2+ = nth rewatch)
   - `revisit_type`: label (e.g., "regular_revisit", "special_edition")

4. **Uniqueness Constraint**: `UNIQUE(staging_episode_id, movie_id)` prevents accidental duplicates *within* one episode, while allowing same movie *across* different episodes.

### Example: Fight Club revisit

```sql
-- curated_movies
| movie_id | tmdb_id | title      | year |
| ---      | 550     | Fight Club | 1999 |

-- curated_episode_movies (two rows for two different episodes)
| episode_movie_id | episode_number | movie_id | is_revisit | revisit_sequence |
| ---              | 10             | ---      | false      | 1                |
| ---              | 287            | ---      | true       | 2                |
```

## Configuration

### Environment Variables

Create `config/.env` (never commit):

```env
# Google Sheets
GOOGLE_SHEETS_WORKSHEET_ID=13KsNb1SxA7DYYQAzhaYxj_qKX0PXV1PXyKAZ7cEapRc
GOOGLE_SHEET_GID=637738347

# TMDB API (free tier sufficient for this use case)
TMDB_API_KEY=your_api_key_here

# Database
DB_PATH=./rewatchables.db

# Pipeline tuning
MATCH_CONFIDENCE_THRESHOLD=0.85
MATCH_YEAR_WINDOW=2
API_RATE_LIMIT_BACKOFF_SECONDS=2
```

## Workflow

### Weekly Sync Workflow

1. **Sync**: Pull latest episodes from Google Sheet → `master.xlsx`
2. **Ingest**: Load `master.xlsx` → SQLite raw zone
3. **Normalize**: Parse titles/years → staging zone
4. **Enrich**: Search TMDB/Wiki → staging candidates
5. **Validate**: Quality checks and reporting
6. **Manual Review** (if needed): Approve unresolved matches before promotion to curated

### File Structure

```
rewatchables/
├── data/
│   ├── master.xlsx           # Current working copy (synced from Google Sheets)
│   ├── raw/                  # Historical snapshots (optional)
│   └── staging/              # Working CSV exports (optional)
├── sql/
│   ├── schemas/
│   │   ├── raw_zone.sql
│   │   ├── staging_zone.sql
│   │   └── curated_zone.sql
│   ├── migrations/           # Schema evolution scripts
│   └── queries/              # Reusable analysis queries
├── scripts/
│   ├── 01_sync_sheets.py
│   ├── 02_load_raw.py
│   ├── 03_normalize_and_resolve.py
│   ├── 04_enrich.py
│   ├── 05_validate.py
│   └── orchestrate.py
├── config/
│   └── .env.template
├── tests/
│   └── (test files)
├── logs/
│   └── (pipeline run logs)
├── rewatchables.db           # SQLite database
├── .gitignore
└── README.md
```

## Security & Best Practices

### Secrets
- **Never commit** `.env` file or API keys
- Use `.env.template` for configuration template
- Rotate API keys every 90 days
- GitHub Actions: store secrets in repository settings

### Data Protection
- Only store public film metadata (no PII)
- Exclude podcast internal notes/emails
- All enrichment decisions logged with timestamp and source

### Auditability
- Every API call logged (`api_call_log` table)
- Every enrichment decision immutable (`curated_audits` table)
- Full lineage: raw → staging → curated with source attribution

## Troubleshooting

### "No TMDB matches found"
- Check title normalization: titles with "The" at the start are moved to end
- Try manually approving in `manual_review_queue`
- Check `api_call_log` for rate-limit errors

### Rate Limit Errors
- Pipeline respects TMDB's 40 requests / 10 seconds
- Built-in backoff: waits 2^n seconds on failure
- Check `api_call_log` for `rate_limit_remaining` field

### Database Locked
- Only one pipeline instance should run at a time
- Check for stale `rewatchables.db-journal` files and delete if needed

### Duplicate Movies
- Check `curated_episode_movies` for accidental same-episode duplicates (should be prevented by unique constraint)
- Revisits are expected: different episodes, same movie = valid and tracked

## API Sources (Free Tier)

| Source | Coverage | Rate Limit | Use Case |
|--------|----------|-----------|----------|
| **TMDB** | Excellent (modern films) | 40 req/10s | Primary film identity + metadata |
| **Wikipedia** | Good (notable films) | 200 req/min | Plot summaries, context |
| **Wikidata** | Good (structured IDs) | 200 req/min | Identifier reconciliation |

## Queries

### Find all revisits
```sql
SELECT 
    e.episode_number, 
    e.episode_date,
    m.title,
    em.revisit_sequence
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
JOIN staging_episodes e ON em.staging_episode_id = e.staging_episode_id
WHERE em.is_revisit = 1
ORDER BY m.title, em.revisit_sequence;
```

### Most revisited movies
```sql
SELECT 
    m.title,
    COUNT(DISTINCT em.staging_episode_id) as times_discussed,
    SUM(CASE WHEN em.is_revisit THEN 1 ELSE 0 END) as revisit_count
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
GROUP BY m.title
ORDER BY revisit_count DESC
LIMIT 10;
```

### Data quality summary
```sql
SELECT 
    run_timestamp,
    total_episodes_processed,
    resolution_rate_pct,
    unresolved_mentions
FROM data_quality_results
ORDER BY run_timestamp DESC
LIMIT 10;
```

## Limitations & Future Enhancements

### Current
- Manual review required for low-confidence matches (ensures accuracy)
- Free API tier only (covers most use cases)
- SQLite (suitable for <100K episodes)

### Potential Future
- Lightweight web UI for manual review (replace CSV workflow)
- PostgreSQL for cloud deployment
- OMDb API for detailed ratings (paid tier)
- Automated cast/crew deep-linking
- Historical enrichment updates when APIs change

## Support & Runbook

For detailed operations runbook, see [OPERATIONS.md](OPERATIONS.md) (to be created after pilot).

For architectural decisions, see [ARCHITECTURE.md](ARCHITECTURE.md) (to be created).
