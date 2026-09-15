#!/usr/bin/env python3
"""Step 10: resolve external identifiers.

The code is in src/rewatchables/pipeline/s10_resolve_external_ids.py; this wrapper keeps
`python scripts/10_resolve_external_ids.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s10_resolve_external_ids", run_name="__main__",
                 alter_sys=True)
