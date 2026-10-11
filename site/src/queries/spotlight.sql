-- One director (kind 'director') or actor ('actor') by address.
SELECT name, slug, films, 'director' AS kind FROM directors WHERE ?1 = 'director' AND slug = ?2
UNION ALL
SELECT name, slug, films, 'actor' AS kind FROM actors WHERE ?1 = 'actor' AND slug = ?2
