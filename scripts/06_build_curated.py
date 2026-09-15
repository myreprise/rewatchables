#!/usr/bin/env python3
"""Step 06: build the curated zone and detect revisits.

The code is in src/rewatchables/pipeline/s06_build_curated.py; this wrapper keeps
`python scripts/06_build_curated.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s06_build_curated", run_name="__main__",
                 alter_sys=True)
