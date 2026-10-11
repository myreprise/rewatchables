-- Every lean comparison, most significant first. Agrees with: Hosts &
-- Guests' "All comparisons" table (hosts.regular_leans).
SELECT l.*, p.slug FROM leans l LEFT JOIN people p ON p.name = l.person
ORDER BY l.p, l.person, l.metric
