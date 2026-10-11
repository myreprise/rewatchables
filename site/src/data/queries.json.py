# Framework data loader: every query in src/queries/, as one JSON file
# {name: sql}, so a page fetches its SQL in one request rather than one per
# query. The .sql files stay the source: tests/test_site_db.py runs the same
# files against the same database and checks them against the app.

import json
import sys
from pathlib import Path

queries = Path(__file__).parent.parent / "queries"
out = {p.stem: p.read_text(encoding="utf-8") for p in sorted(queries.glob("*.sql"))}
sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1))
