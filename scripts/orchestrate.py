#!/usr/bin/env python3
"""Run the pipeline.

The code is in src/rewatchables/pipeline/orchestrate.py; this wrapper keeps
`python scripts/orchestrate.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.orchestrate", run_name="__main__",
                 alter_sys=True)
