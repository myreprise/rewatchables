-- Every actor on three or more films, most films first, then best rated.
-- Agrees with: actors.ranked_actors.
SELECT * FROM actors ORDER BY films DESC, avg_tmdb DESC, name
