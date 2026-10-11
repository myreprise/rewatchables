-- One of a film's related-film shelves: kind is 'director' or 'cast'.
-- Agrees with: dossier.same_director / dossier.shared_cast (precomputed).
SELECT f.slug, f.title, f.year, f.poster
FROM film_shelves s JOIN films f ON f.slug = s.other
WHERE s.slug = ? AND s.kind = ?
ORDER BY s.rank
