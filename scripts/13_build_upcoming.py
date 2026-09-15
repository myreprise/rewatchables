#!/usr/bin/env python3
"""Step 13: build the upcoming-films list.

The code is in src/rewatchables/pipeline/s13_build_upcoming.py; this wrapper keeps
`python scripts/13_build_upcoming.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s13_build_upcoming", run_name="__main__",
                 alter_sys=True)
