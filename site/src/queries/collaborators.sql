-- A director's recurring actors or an actor's recurring directors
-- (precomputed). Agrees with: directors.actors_brought_back /
-- actors.directors_returned_to.
SELECT c.other AS name, c.films,
       CASE WHEN c.kind = 'director' THEN (SELECT slug FROM actors WHERE name = c.other)
            ELSE (SELECT slug FROM directors WHERE name = c.other) END AS slug
FROM collaborators c WHERE c.kind = ? AND c.name = ? ORDER BY c.ord
