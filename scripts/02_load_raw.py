#!/usr/bin/env python3
"""Step 02: load the raw zone from data/episodes.csv.

The code is in src/rewatchables/pipeline/s02_load_raw.py; this wrapper keeps
`python scripts/02_load_raw.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s02_load_raw", run_name="__main__",
                 alter_sys=True)
