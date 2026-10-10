"""TMDB images on the local drive, and the URL the app should use for one.

Step 14 downloads every poster the app can show -- curated_movies and
curated_upcoming_films -- plus the two Cruise/Hanks portraits, at the two
widths the app draws them at, into static/tmdb/<size>/. Streamlit serves that
folder at app/static/ (server.enableStaticServing in .streamlit/config.toml),
so the browser loads posters from this machine rather than from image.tmdb.org.

Files are named for the film -- "Heat (1995).jpg" -- so the folder is readable
on its own. The database keeps TMDB's URL, whose last segment is TMDB's own
content hash, and static/tmdb/manifest.json maps that hash to the local name.
That keeps the app's call sites on the stored URL alone: a caller never needs
the title and year to find a poster. An image not in the manifest, or not yet
downloaded, falls back to TMDB, so a film added since step 14 last ran still
shows its poster.
"""

import functools
import json
import os
import re
from urllib.parse import quote

from rewatchables import config

TMDB_BASE = "https://image.tmdb.org/t/p"
IMAGE_DIR = config.ROOT / "static" / "tmdb"
MANIFEST = "manifest.json"
# Where Streamlit serves IMAGE_DIR from. Relative, like Streamlit's own
# examples, so it resolves against whatever host and port the app is on.
SERVED_AT = "app/static/tmdb"

# w185 for poster grids and the upcoming list, w342 for the dossier, the
# overview spotlight and the Cruise/Hanks rails and portraits.
SIZES = ("w185", "w342")

# Publicity portraits for the two subjects of the Cruise vs. Hanks segment,
# resolved once from TMDB /person (Cruise is 500, Hanks is 31) and pinned here.
# TMDB image paths are content-addressed and stable, so hard-coding them keeps
# the section header off the API entirely -- there is no person cache, and one
# lookup per cold start to render two decorative images is not worth building.
PORTRAITS = {
    "Tom Cruise": "/3mShHjSQR7NXOVbdTu5rT2Qd0MN.jpg",
    "Tom Hanks": "/oFvZoKI6lvU03n4YoNGAll9rkas.jpg",
}

# Characters Windows refuses in a file name. A colon is almost always a
# subtitle ("Mad Max: Fury Road"), so it reads best as a dash; the rest go.
_SUBTITLE = re.compile(r"\s*:\s*")
_FORBIDDEN = re.compile(r'[<>"\\|?*\x00-\x1f]')


def file_name(url):
    """The image's TMDB name: the last segment of a TMDB URL or path.

    None for an empty value, so a film without a poster stays without one.
    """
    if not url or not isinstance(url, str):
        return None
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return name or None


def local_name(title, year, url):
    """The name a poster is saved under: "Title (Year).jpg".

    The extension is TMDB's. Characters Windows cannot store are replaced, and
    a trailing dot or space -- which Windows silently drops -- is trimmed.
    """
    stem = _SUBTITLE.sub(" - ", str(title).strip())
    stem = _FORBIDDEN.sub("", stem.replace("/", "-"))
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if year is not None:
        stem = f"{stem} ({int(year)})"
    return stem + os.path.splitext(file_name(url))[1]


def remote(url, size):
    """TMDB's URL for the image at `size`."""
    return f"{TMDB_BASE}/{size}/{file_name(url)}"


def read_manifest(folder=None):
    """TMDB name -> local name, as step 14 last wrote it; {} if never."""
    try:
        with open((folder or IMAGE_DIR) / MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


@functools.cache
def _manifest():
    return read_manifest()


@functools.cache
def _on_disk(size):
    """The file names downloaded at `size`, read once per process.

    A poster grid asks for hundreds of images a render; one directory listing
    is cheaper than a stat per image. A file step 14 adds while the app is up
    is not seen until a restart, and until then it is loaded from TMDB, which
    is where it came from anyway.
    """
    try:
        return frozenset(os.listdir(IMAGE_DIR / size))
    except OSError:
        return frozenset()


def src(url, size):
    """What an <img src> should say: the local copy if there is one, else TMDB.

    None when there is no image at all. The local name is percent-encoded:
    titles carry spaces, apostrophes and ampersands.
    """
    name = file_name(url)
    if name is None:
        return None
    local = _manifest().get(name)
    if local and local in _on_disk(size):
        return f"{SERVED_AT}/{size}/{quote(local)}"
    return remote(name, size)
