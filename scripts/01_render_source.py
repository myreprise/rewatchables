#!/usr/bin/env python3
"""Step 01: render data/episodes.xlsx to data/episodes.csv.

The code is in src/rewatchables/pipeline/s01_render_source.py; this wrapper keeps
`python scripts/01_render_source.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s01_render_source", run_name="__main__",
                 alter_sys=True)
