-- The catalogue's size and averages: what a keyword's share and rating are
-- read against, and what a person's share of airings is out of.
SELECT (SELECT count(*) FROM films) AS films,
       (SELECT avg(tmdb) FROM films) AS avg_tmdb,
       (SELECT count(*) FROM episodes) AS airings
