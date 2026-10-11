-- A film's top-billed cast (ten), each with the number of films they are
-- top-five billed in, and their actor page if they have one.
-- Agrees with: dossier.cast_billing.
SELECT c.name, c.billing,
       (SELECT count(*) FROM film_cast o WHERE o.name = c.name AND o.billing < 5) AS films,
       a.slug AS actor_slug
FROM film_cast c LEFT JOIN actors a ON a.name = c.name
WHERE c.slug = ? AND c.billing < 10
ORDER BY c.billing
