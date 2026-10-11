-- Who a person sits with most, Bill aside (precomputed, six).
-- Agrees with: hosts.sits_with.
SELECT c.other AS name, c.episodes, p.slug
FROM person_company c LEFT JOIN people p ON p.name = c.other
WHERE c.person = ?
ORDER BY c.ord
