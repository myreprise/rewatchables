"""The pipeline's thirteen steps, one module each, plus the orchestrator.

A step is `sNN_<name>`, numbered as orchestrate.STEPS numbers it; the `s`
exists only because a module name cannot start with a digit. Run one with
`python -m rewatchables.pipeline.s04_enrich`, or through its wrapper,
`python scripts/04_enrich.py`.
"""
