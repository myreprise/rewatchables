-- A film's directors, in credit order, with their spotlight if they have one.
SELECT d.name, d.ord, s.slug AS director_slug
FROM film_directors d LEFT JOIN directors s ON s.name = d.name
WHERE d.slug = ?
ORDER BY d.ord
