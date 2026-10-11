-- For the place keywords of one region (a JSON array of words): how many
-- distinct films carry any of them. Agrees with: keyword_profile()['region_films'].
SELECT count(DISTINCT slug) AS films FROM film_keywords
WHERE word IN (SELECT value FROM json_each(?))
