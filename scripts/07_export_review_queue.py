#!/usr/bin/env python3
"""Step 07: export the manual-review queue.

The code is in src/rewatchables/pipeline/s07_export_review_queue.py; this wrapper keeps
`python scripts/07_export_review_queue.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s07_export_review_queue", run_name="__main__",
                 alter_sys=True)
