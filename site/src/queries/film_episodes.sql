-- A film's airings, oldest first. Agrees with: the dossier's episode spine.
SELECT * FROM episodes WHERE slug = ? ORDER BY number, date
