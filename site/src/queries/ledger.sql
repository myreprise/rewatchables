-- Every Cruise vs. Hanks verdict, newest first. Agrees with: the verdicts
-- section's ledger (ctx.cruise_hanks).
SELECT e.number, e.date, e.verdict, f.slug, f.title, f.year, f.poster
FROM episodes e JOIN films f ON f.slug = e.slug
WHERE e.verdict IN ('Cruise', 'Hanks', 'Tie')
ORDER BY e.number DESC, e.date DESC
