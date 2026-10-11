-- Every film, for the Movie Explorer's grid, filters and table. The page
-- filters and sorts these rows. Agrees with: sections/explorer.py (ctx.rated).
SELECT f.slug, f.title, f.year, f.decade, f.sort_title, f.runtime, f.tmdb, f.rt, f.ebert,
       f.episodes, f.first_episode, f.last_episode, f.poster, f.director_primary,
       (SELECT group_concat(genre, '|') FROM (SELECT genre FROM film_genres g
         WHERE g.slug = f.slug ORDER BY ord)) AS genres
FROM films f
ORDER BY f.year, f.sort_title
