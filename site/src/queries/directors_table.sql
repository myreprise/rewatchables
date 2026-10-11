-- Every director, most films first, then best rated.
-- Agrees with: directors.ranked_directors.
SELECT * FROM directors ORDER BY films DESC, avg_tmdb DESC, name
