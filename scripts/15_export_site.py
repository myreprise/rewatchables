#!/usr/bin/env python3
"""Step 15: export the public site's data to site/src/data/.

The code is in src/rewatchables/pipeline/s15_export_site.py; this wrapper keeps
`python scripts/15_export_site.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s15_export_site", run_name="__main__",
                 alter_sys=True)
