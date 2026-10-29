"""The context a section or an overlay renders from, built from cached loaders.

rewatchables.context defines it; this builds it once per rerun from the app's
cached loaders, so a widget change does not reload the database.
"""

from rewatchables.app import data
from rewatchables.context import build_context as _build


def build_context(db_stamp):
    """Load everything once for this rerun. `db_stamp` keys the caches."""
    return _build(db_stamp, loaders=data)
