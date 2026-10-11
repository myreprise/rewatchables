-- The whole vocabulary, commonest first: search runs over it.
SELECT word, slug, reach, band FROM keywords ORDER BY reach DESC, word
