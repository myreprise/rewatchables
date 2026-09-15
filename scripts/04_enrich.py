#!/usr/bin/env python3
"""Step 04: resolve mentions against TMDB.

The code is in src/rewatchables/pipeline/s04_enrich.py; this wrapper keeps
`python scripts/04_enrich.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s04_enrich", run_name="__main__",
                 alter_sys=True)
