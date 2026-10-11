-- Every film with a gross, highest first. Agrees with: boxoffice.money_table.
SELECT slug, title, year, budget_real, budget, revenue_real, box_office, multiple, tmdb, episodes
FROM films WHERE revenue_real IS NOT NULL ORDER BY revenue_real DESC
