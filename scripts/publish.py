#!/usr/bin/env python3
"""Publish the episode list: pipeline, checks, commit, push.

The code is in src/rewatchables/publish.py; this wrapper keeps
`python scripts/publish.py` working. Arguments and the exit code pass through.
"""

import runpy

runpy.run_module("rewatchables.publish", run_name="__main__", alter_sys=True)
