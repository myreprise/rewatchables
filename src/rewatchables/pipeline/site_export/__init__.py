"""The public site's data, as one SQLite database.

Pipeline step 15 (s15_export_site.py) writes what site_db produces: site.sql,
the database as a sorted dump, and synopses.json. The other modules build the
parts of it that are a section's own numbers and charts, using the same
functions the Streamlit sections call, so the two front ends print the same
numbers:

  site_db    the database: its tables, the dump, the synopses
  common     addresses (prepare), the poster card, JSON-safe values
  overview   the front page's numbers and chart
  sections   each chart section's figures and numbers
  keywords   the Keywords section's numbers
  upcoming   the Upcoming section's numbers, and each request's row
"""
