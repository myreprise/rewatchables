#!/usr/bin/env python3
"""Step 14: download the app's TMDB images to the local drive.

The code is in src/rewatchables/pipeline/s14_cache_images.py; this wrapper keeps
`python scripts/14_cache_images.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s14_cache_images", run_name="__main__",
                 alter_sys=True)
