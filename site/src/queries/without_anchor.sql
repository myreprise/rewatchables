-- The airings the named anchor was not on, with who hosted, oldest first.
-- Agrees with: hosts.without_anchor (the page groups them by host).
SELECT e.id, e.number, e.date, f.slug, f.title, f.year, f.poster,
       (SELECT person FROM episode_room h WHERE h.episode = e.id AND h.chair = 'host') AS host
FROM episodes e JOIN films f ON f.slug = e.slug
WHERE NOT EXISTS (SELECT 1 FROM episode_room r WHERE r.episode = e.id AND r.person = ?)
ORDER BY e.date
