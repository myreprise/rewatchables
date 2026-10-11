"""The public site's data, one module per kind of page.

Pipeline step 15 (s15_export_site.py) runs these and writes what they return.
Each module turns the app's context into plain rows, using the same functions
the Streamlit sections call, so the two front ends print the same numbers:

  common     serialisation, addresses, the poster card
  films      films.json and one file per film page
  overview   the front page and its chart
  keywords   the Keywords section and one file per keyword page
  people     the person index and one file per person page
  sections   one file per chart section: Ratings, Box Office, Timeline,
             Genres, Cruise vs. Hanks
"""
