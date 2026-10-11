-- One Upcoming request by address, with its pitch tags.
SELECT r.*, (SELECT group_concat(tag, '|') FROM (SELECT tag FROM request_tags t
             WHERE t.slug = r.slug ORDER BY ord)) AS tags
FROM requests r WHERE r.slug = ?
