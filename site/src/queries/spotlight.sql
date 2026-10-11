-- One director (kind 'director') or actor ('actor') by address, with the
-- spotlight's statistics. Agrees with: analysis.PERSON_AGG / person_stats.
SELECT name, slug, films, avg_tmdb, avg_rt, avg_runtime, first_year, last_year
FROM directors WHERE ?1 = 'director' AND slug = ?2
UNION ALL
SELECT name, slug, films, avg_tmdb, avg_rt, avg_runtime, first_year, last_year
FROM actors WHERE ?1 = 'actor' AND slug = ?2
