-- Requests that have since aired, by first airing. Agrees with: ctx.graduated.
SELECT g.ord, g.requested_as, g.aired, g.episodes, f.slug, f.title, f.year, f.poster
FROM graduated g LEFT JOIN films f ON f.slug = g.film ORDER BY g.ord
