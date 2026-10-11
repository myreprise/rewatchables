-- A film's genres, in TMDB's order.
SELECT genre FROM film_genres WHERE slug = ? ORDER BY ord
