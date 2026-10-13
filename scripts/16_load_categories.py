#!/usr/bin/env python3
"""Step 16: load rewatchvault.com category entries, in batches.

The code is in src/rewatchables/pipeline/s16_load_categories.py; this wrapper keeps
`python scripts/16_load_categories.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s16_load_categories", run_name="__main__",
                 alter_sys=True)
