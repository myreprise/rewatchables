#!/usr/bin/env python3
"""Step 08: apply manual-review decisions.

The code is in src/rewatchables/pipeline/s08_apply_review.py; this wrapper keeps
`python scripts/08_apply_review.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s08_apply_review", run_name="__main__",
                 alter_sys=True)
