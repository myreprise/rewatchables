#!/usr/bin/env python3
"""Step 03: normalize episodes and stage movie mentions.

The code is in src/rewatchables/pipeline/s03_normalize_and_resolve.py; this wrapper keeps
`python scripts/03_normalize_and_resolve.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s03_normalize_and_resolve", run_name="__main__",
                 alter_sys=True)
