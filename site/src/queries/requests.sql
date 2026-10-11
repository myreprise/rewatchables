-- Every Upcoming request in source order, with its pitch tags.
-- Agrees with: the upcoming section's frame (ctx.upcoming).
SELECT r.*, (SELECT group_concat(tag, '|') FROM (SELECT tag FROM request_tags t
             WHERE t.slug = r.slug ORDER BY ord)) AS tags
FROM requests r ORDER BY r.ord
