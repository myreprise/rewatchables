-- The Cruise vs. Hanks verdicts on the airings a person was on.
-- Agrees with: hosts.verdict_tally.
SELECT e.verdict, count(*) AS n
FROM episode_room r JOIN episodes e ON e.id = r.episode
WHERE r.person = ? AND e.verdict IS NOT NULL
GROUP BY e.verdict
