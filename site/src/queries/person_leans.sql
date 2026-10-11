-- A regular's leans that survive the correction, most certain first, ties
-- by measure. Agrees with: panels.lean_chips.
SELECT phrase, diff > 0 AS up FROM leans WHERE person = ? AND shown = 1 ORDER BY q, metric
