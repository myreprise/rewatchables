-- Films per decade across the catalogue: the baseline a keyword's decade
-- shape is read against.
SELECT decade, count(*) AS films FROM films WHERE decade IS NOT NULL GROUP BY decade ORDER BY decade
