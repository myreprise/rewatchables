-- The twenty most-featured directors (kind 'director') or actors ('actor'),
-- in the app's pickers' order. Agrees with: top_directors / top_actors.
SELECT name, slug, films FROM directors WHERE ?1 = 'director' AND top_rank IS NOT NULL
UNION ALL
SELECT name, slug, films FROM actors WHERE ?1 = 'actor' AND top_rank IS NOT NULL
ORDER BY films DESC, name
