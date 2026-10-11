# Framework data loader: builds site.db from site.sql, the sorted SQL dump
# pipeline step 15 writes beside this file.
#
# The dump is what the repository tracks: text, one row per line, so a
# publish changes only the rows that changed. The binary database is built
# here, at build time, and is what a visitor's browser downloads and queries.
# Framework runs this on `npm run dev` and `npm run build`, and writes what it
# prints to stdout as site.db.

import sqlite3
import sys
from pathlib import Path

dump = (Path(__file__).parent / "site.sql").read_text(encoding="utf-8")
db = sqlite3.connect(":memory:")
db.executescript(dump)
# A tidy file: no free pages, and statistics for the query planner.
db.execute("ANALYZE")
db.commit()
sys.stdout.buffer.write(db.serialize())
