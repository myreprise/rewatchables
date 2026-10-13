#!/usr/bin/env python3
"""Step 17: build the category tables from stored rewatchvault pages.

The code is in src/rewatchables/pipeline/s17_build_categories.py; this wrapper keeps
`python scripts/17_build_categories.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s17_build_categories", run_name="__main__",
                 alter_sys=True)
