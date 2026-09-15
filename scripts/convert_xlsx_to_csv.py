#!/usr/bin/env python3
"""Render a spreadsheet to its tracked CSV.

The code is in src/rewatchables/pipeline/convert_xlsx_to_csv.py; this wrapper keeps
`python scripts/convert_xlsx_to_csv.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.pipeline.convert_xlsx_to_csv", run_name="__main__",
                 alter_sys=True)
