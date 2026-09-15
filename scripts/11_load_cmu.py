#!/usr/bin/env python3
"""Step 11: load the vendored CMU corpus subset.

The code is in src/rewatchables/pipeline/s11_load_cmu.py; this wrapper keeps
`python scripts/11_load_cmu.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s11_load_cmu", run_name="__main__",
                 alter_sys=True)
