-- Rewatchables Analytics Queries
-- Explore film revisits and podcast trends

-- ============================================================================
-- REVISIT ANALYTICS
-- ============================================================================

-- Find all movies that were revisited (discussed more than once)
SELECT 
    m.movie_id,
    m.tmdb_id,
    m.title,
    m.year,
    COUNT(DISTINCT em.staging_episode_id) as total_episodes,
    SUM(CASE WHEN em.is_revisit = 0 THEN 1 ELSE 0 END) as first_discussion_count,
    SUM(CASE WHEN em.is_revisit = 1 THEN 1 ELSE 0 END) as revisit_count,
    MIN(em.episode_date) as first_episode_date,
    MAX(em.episode_date) as last_episode_date,
    ROUND(CAST((julianday(MAX(em.episode_date)) - julianday(MIN(em.episode_date))) AS REAL), 0) as days_between_episodes
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
GROUP BY m.movie_id, m.title, m.year
HAVING COUNT(DISTINCT em.staging_episode_id) > 1
ORDER BY revisit_count DESC;

-- ============================================================================
-- REVISIT TIMELINE FOR A SPECIFIC MOVIE
-- ============================================================================

-- Show all episodes discussing "Fight Club" with revisit info
SELECT 
    se.episode_number,
    se.episode_date,
    se.episode_title,
    m.title as movie_title,
    em.revisit_sequence,
    em.is_revisit,
    em.revisit_type,
    em.mention_type
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
JOIN staging_episodes se ON em.staging_episode_id = se.staging_episode_id
WHERE m.title = 'Fight Club'
ORDER BY em.episode_date;

-- ============================================================================
-- MOVIES REVISITED N TIMES
-- ============================================================================

-- Movies revisited exactly once
SELECT 
    m.title,
    m.year,
    COUNT(DISTINCT em.staging_episode_id) as times_discussed
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
GROUP BY m.movie_id
HAVING COUNT(DISTINCT em.staging_episode_id) = 2
ORDER BY m.title;

-- ============================================================================
-- TOP REVISITED MOVIES
-- ============================================================================

-- Top 20 most revisited films
SELECT 
    m.title,
    m.year,
    m.rating_tmdb,
    COUNT(DISTINCT em.staging_episode_id) as episodes_featured,
    SUM(CASE WHEN em.is_revisit = 1 THEN 1 ELSE 0 END) as revisit_count,
    MIN(em.episode_date) as first_featured,
    MAX(em.episode_date) as last_featured
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
GROUP BY m.movie_id
ORDER BY episodes_featured DESC
LIMIT 20;

-- ============================================================================
-- REVISIT PATTERNS: TIME BETWEEN DISCUSSIONS
-- ============================================================================

-- Average time between discussions for revisited films
SELECT 
    m.title,
    m.year,
    COUNT(DISTINCT em.staging_episode_id) as episodes,
    ROUND(AVG(julianday(em.episode_date) - 
        LAG(julianday(em.episode_date)) OVER (
            PARTITION BY em.movie_id 
            ORDER BY em.episode_date
        )), 0) as avg_days_between_discussions
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
WHERE em.movie_id IN (
    SELECT movie_id FROM curated_episode_movies 
    GROUP BY movie_id 
    HAVING COUNT(DISTINCT staging_episode_id) > 1
)
GROUP BY em.movie_id
ORDER BY episodes DESC;

-- ============================================================================
-- GENRES OF REVISITED VS. NON-REVISITED FILMS
-- ============================================================================

-- Genre distribution: revisited films vs others
SELECT 
    CASE 
        WHEN revisit_count > 0 THEN 'Revisited'
        ELSE 'Non-Revisited'
    END as film_type,
    COUNT(*) as film_count,
    ROUND(AVG(m.rating_tmdb), 2) as avg_rating,
    ROUND(AVG(m.popularity_tmdb), 2) as avg_popularity
FROM (
    SELECT DISTINCT em.movie_id,
        SUM(CASE WHEN em.is_revisit = 1 THEN 1 ELSE 0 END) as revisit_count
    FROM curated_episode_movies em
    GROUP BY em.movie_id
) subq
JOIN curated_movies m ON subq.movie_id = m.movie_id
GROUP BY film_type;

-- ============================================================================
-- VALIDATION: CHECK FOR ACCIDENTAL DUPLICATES
-- ============================================================================

-- Should return 0 rows (no duplicate episode-movie pairs within same episode)
SELECT 
    staging_episode_id,
    movie_id,
    COUNT(*) as duplicate_count
FROM curated_episode_movies
GROUP BY staging_episode_id, movie_id
HAVING COUNT(*) > 1;

-- ============================================================================
-- AUDIT TRAIL: WHO ENRICHED WHAT AND WHEN
-- ============================================================================

-- Recent enrichment decisions
SELECT 
    ca.enriched_at,
    ca.enriched_by,
    m.title,
    ca.field_changed,
    ca.old_value,
    ca.new_value
FROM curated_audits ca
LEFT JOIN curated_movies m ON ca.movie_id = m.movie_id
ORDER BY ca.enriched_at DESC
LIMIT 50;

-- ============================================================================
-- DATA QUALITY: CONFIDENCE LEVELS
-- ============================================================================

-- Confidence distribution across enriched films
SELECT 
    m.canonical_key_confidence,
    COUNT(*) as film_count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM curated_movies), 1) as pct
FROM curated_movies m
GROUP BY m.canonical_key_confidence
ORDER BY 
    CASE m.canonical_key_confidence 
        WHEN 'high' THEN 1 
        WHEN 'medium' THEN 2 
        WHEN 'low' THEN 3 
    END;

-- ============================================================================
-- API PERFORMANCE: RATE LIMITS AND RESPONSE TIMES
-- ============================================================================

-- API call statistics by source
SELECT 
    api_source,
    COUNT(*) as call_count,
    ROUND(AVG(response_time_ms), 1) as avg_response_ms,
    MAX(response_time_ms) as max_response_ms,
    SUM(CASE WHEN response_status_code = 200 THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN response_status_code != 200 THEN 1 ELSE 0 END) as failed
FROM api_call_log
GROUP BY api_source;

-- ============================================================================
-- UNRESOLVED MOVIES (MANUAL REVIEW QUEUE)
-- ============================================================================

-- Current manual review queue
SELECT 
    mrq.review_id,
    mrq.movie_title_raw,
    mrq.year_parsed,
    mrq.director_raw,
    mrq.queue_status,
    mrq.queued_at,
    mrq.reviewer_name
FROM manual_review_queue mrq
WHERE mrq.queue_status IN ('pending', 'in_review')
ORDER BY mrq.queued_at;
