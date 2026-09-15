#!/usr/bin/env python3
"""Step 12: plot summaries from CMU and live Wikipedia.

The code is in src/rewatchables/pipeline/s12_enrich_plot_summaries.py; this wrapper keeps
`python scripts/12_enrich_plot_summaries.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.s12_enrich_plot_summaries", run_name="__main__",
                 alter_sys=True)
