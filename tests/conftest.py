"""
Shared pytest configuration.
Adds the scripts directory to sys.path so test files can import directly from
the pipeline scripts without requiring a package restructure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
