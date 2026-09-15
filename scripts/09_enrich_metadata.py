#!/usr/bin/env python3
"""Step 09: enrich metadata from TMDB.

The code is in src/rewatchables/pipeline/s09_enrich_metadata.py; this wrapper keeps
`python scripts/09_enrich_metadata.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s09_enrich_metadata", run_name="__main__",
                 alter_sys=True)
