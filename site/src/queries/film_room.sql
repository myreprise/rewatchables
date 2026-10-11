-- Everyone in the room on a film's airings, in chair order, with the address
-- of their person page (NULL for the anchor, who has none).
SELECT r.episode, r.seat, r.person, r.chair, p.slug AS person_slug
FROM episode_room r
JOIN episodes e ON e.id = r.episode
LEFT JOIN people p ON p.name = r.person
WHERE e.slug = ?
ORDER BY r.episode, r.seat
