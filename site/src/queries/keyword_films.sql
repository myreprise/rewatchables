-- The films carrying a keyword, oldest first. Agrees with: keyword_profile()['films'].
SELECT f.slug, f.title, f.year, f.poster, f.tmdb, f.decade
FROM film_keywords fk JOIN films f ON f.slug = fk.slug
WHERE fk.word = ?
ORDER BY f.year, f.slug
