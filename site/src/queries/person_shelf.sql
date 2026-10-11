-- Every airing a person was on, newest first. Agrees with: analysis.person_shelf.
SELECT e.id, e.number, e.date, e.verdict, f.slug, f.title, f.year, f.poster
FROM episode_room r
JOIN episodes e ON e.id = r.episode
JOIN films f ON f.slug = e.slug
WHERE r.person = ?
ORDER BY e.date DESC, e.number DESC
