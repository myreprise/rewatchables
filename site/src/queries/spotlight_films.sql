-- A director's films (kind 'director', by primary director) or an actor's
-- (kind 'actor', anywhere in the billed cast), oldest first.
-- Agrees with: analysis.films_by_director / films_by_actor.
SELECT f.* FROM films f
WHERE (?1 = 'director' AND f.director_primary = ?2)
   OR (?1 = 'actor' AND EXISTS (SELECT 1 FROM film_cast c
        WHERE c.slug = f.slug AND c.name = ?2 AND c.billing < 10))
ORDER BY f.year, f.slug
