-- The keywords that travel with one: most shared films first, ties
-- alphabetical, fourteen. Agrees with: keyword_profile()['partners'].
SELECT o.word, count(*) AS shared, k.reach, k.band, k.slug
FROM film_keywords fk
JOIN film_keywords o ON o.slug = fk.slug AND o.word <> fk.word
JOIN keywords k ON k.word = o.word
WHERE fk.word = ?
GROUP BY o.word
ORDER BY shared DESC, o.word
LIMIT 14
