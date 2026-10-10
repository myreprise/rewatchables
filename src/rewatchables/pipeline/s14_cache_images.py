#!/usr/bin/env python3
"""
Phase I: Download the app's TMDB images to the local drive.

Every poster in curated_movies and curated_upcoming_films, and the Cruise/Hanks
portraits, at each width in images.SIZES, into static/tmdb/<size>/, each named
for its film: "Heat (1995).jpg". static/tmdb/manifest.json records which TMDB
image each file is, which is how the app finds it; see rewatchables/images.py.

Idempotent: a file already on disk is not fetched again, and a film whose
title changes has its file renamed rather than downloaded again. After the first run
only a newly added film costs a download -- two, one per width. The image CDN
needs no API key and has no request budget of its own to stay under.

A failed download is logged and the rest carry on; the app shows that image
from TMDB until a later run gets it. The step exits 1 if any download failed,
which the orchestrator reports as a skip rather than halting on, since nothing
downstream depends on it.

Files for films that have left the lists are left where they are: a few stray
posters cost less than deleting something a later rebuild would fetch again.
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

import requests

from rewatchables import config, http, images

logger = logging.getLogger(__name__)

POSTER_TABLES = ("curated_movies", "curated_upcoming_films")


def wanted(conn):
    """Every image the app can draw: TMDB name -> local name, sorted.

    Episode films come first, so a film that has graduated from the upcoming
    list is named from curated_movies. Two films with one title and year would
    share a name; the later one takes its tmdb_id as well.
    """
    names = {images.file_name(path): images.local_name(person, None, path)
             for person, path in images.PORTRAITS.items()}
    for table in POSTER_TABLES:
        try:
            rows = conn.execute(
                f"SELECT title, year, tmdb_id, poster_url_tmdb FROM {table} "
                "WHERE poster_url_tmdb IS NOT NULL").fetchall()
        except sqlite3.OperationalError:
            # curated_upcoming_films exists only once step 13 has run.
            logger.info(f"  {table} not found; skipping its posters")
            continue
        taken = {n.casefold() for n in names.values()}
        for title, year, tmdb_id, url in rows:
            tmdb = images.file_name(url)
            if tmdb is None or tmdb in names:
                continue
            local = images.local_name(title, year, url)
            if local.casefold() in taken:
                stem, ext = os.path.splitext(local)
                local = f"{stem} [{tmdb_id}]{ext}"
            names[tmdb] = local
            taken.add(local.casefold())
    return dict(sorted(names.items(), key=lambda kv: kv[1].casefold()))


def download(tmdb, target, size, session=None):
    """Fetch one image to `target`. True on success."""
    url = images.remote(tmdb, size)
    try:
        r = http.get(url, timeout=15, what=f"{size}/{tmdb}", session=session)
    except http.TRANSIENT as e:
        logger.error(f"{size}/{tmdb}: gave up after {http.ATTEMPTS} attempts: {e}")
        return False
    if r.status_code != 200 or not r.content:
        logger.error(f"{size}/{tmdb} ({target.name}): HTTP {r.status_code}")
        return False
    # Written beside the target and renamed into place, so an interrupted run
    # never leaves a truncated file that later runs would take as downloaded.
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(r.content)
    partial.replace(target)
    return True


def write_manifest(names):
    """Write TMDB name -> local name where the app reads it.

    Replaced in one step, so the app never reads half a file.
    """
    images.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = images.IMAGE_DIR / images.MANIFEST
    partial = target.with_name(target.name + ".part")
    partial.write_text(json.dumps(names, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    partial.replace(target)


def cache_images(db_path, session=None):
    """Bring static/tmdb/ up to date.

    A file already under its name is left alone. One under an earlier name --
    the TMDB hash an older run saved it as, or the film's previous title -- is
    renamed rather than fetched again. Anything else is downloaded.

    Returns (downloaded, renamed, present, failed).
    """
    conn = sqlite3.connect(db_path)
    try:
        names = wanted(conn)
    finally:
        conn.close()
    previous = images.read_manifest()

    downloaded = renamed = present = failed = 0
    for size in images.SIZES:
        folder = images.IMAGE_DIR / size
        folder.mkdir(parents=True, exist_ok=True)
        fetched = 0
        for tmdb, local in names.items():
            target = folder / local
            if target.exists():
                present += 1
                continue
            old = next((folder / n for n in (previous.get(tmdb), tmdb)
                        if n and n != local and (folder / n).exists()), None)
            if old is not None:
                old.replace(target)
                renamed += 1
                continue
            if download(tmdb, target, size, session=session):
                downloaded += 1
            else:
                failed += 1
            fetched += 1
            if fetched % 100 == 0:
                logger.info(f"  {size}: {fetched} downloaded so far")

    write_manifest(names)
    logger.info(f"✓ Images: {downloaded} downloaded, {renamed} renamed, "
                f"{present} already in place, {failed} failed "
                f"({len(names)} images x {len(images.SIZES)} sizes)")
    logger.info(f"  in {images.IMAGE_DIR}")
    return downloaded, renamed, present, failed


def main():
    db_path = str(config.db_path())
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase I: Download TMDB images to the local drive")
    logger.info("=" * 60)
    with requests.Session() as session:
        *_, failed = cache_images(db_path, session=session)
    logger.info("=" * 60)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    config.setup_logging()
    main()
