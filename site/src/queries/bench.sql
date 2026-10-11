-- Everyone on at least the given number of episodes, the bench table's order.
-- Agrees with: Hosts & Guests' bench (hosts.the_room, BENCH_FLOOR).
SELECT * FROM people WHERE episodes >= ? ORDER BY rank
