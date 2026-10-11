-- A film's keywords, furthest-reaching first, ties alphabetical.
-- Agrees with: views.rank_by_reach.
SELECT k.word, k.reach, k.band, k.slug
FROM film_keywords fk JOIN keywords k ON k.word = fk.word
WHERE fk.slug = ?
ORDER BY k.reach DESC, k.word
