# The site's queries

One query per file, with `?` for its parameters. The pages load these with
`FileAttachment("queries/<name>.sql").text()` and run them against site.db in
the browser. `tests/test_site_db.py` runs the same files against the same
database and compares the answers with the Streamlit app's own functions, so
a page and the app cannot drift apart unnoticed.

Each file's first comment says what it returns and which app function it
must agree with.
