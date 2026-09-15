#!/usr/bin/env python3
"""Step 05: validate data quality.

The code is in src/rewatchables/pipeline/s05_validate.py; this wrapper keeps
`python scripts/05_validate.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s05_validate", run_name="__main__",
                 alter_sys=True)
