#!/usr/bin/env python3
"""
Publish the episode list: run the pipeline, check it, commit the data, push.

The whole routine for a new episode is two steps:

    1. Edit data/episodes.xlsx in Excel, save, close it.
    2. python scripts/publish.py        (or double-click publish.bat)

In order, publish:

  1. runs the pipeline from step 01 (orchestrate.py --from 1), which ends with
     step 15 writing the public site's data;
  2. stops if TMDB queued a film it was not sure of, and names it. Decide it in
     data/manual_review.csv and run publish again. --allow-pending publishes
     without it: the film stays off the site until it is decided;
  3. runs the quick tests that guard the published data (the workbook renders
     to the tracked CSV; the site export is complete and valid);
  4. prints what changed -- "Added: Ep 484, The Texas Chain Saw Massacre" --
     and asks before going further;
  5. commits only the published data files (PUBLISHED below), never anything
     else in the working tree, with a message written from that summary;
  6. pushes. GitHub Actions then deploys the site (deploy-site.yml).

Each stop happens before anything is committed, so a failed run leaves git
exactly as it was.

Options:
    --dry-run         do 1-4, then stop: nothing is committed or pushed
    --skip-pipeline   use the data as it is (the pipeline was just run)
    --skip-tests      skip step 3
    --allow-pending   publish even with films awaiting review
    --yes             do not ask before committing (for scripted runs)

A real run commits to PUBLISH_BRANCH only. A dry run works on any branch.
"""

import argparse
import csv
import io
import logging
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from rewatchables import config

logger = logging.getLogger(__name__)

PUBLISH_BRANCH = "master"

# Everything a publish may commit, and nothing else. The two workbooks are the
# sources; the CSVs are rendered from them and tracked so a diff names the row
# that changed; manual_review.csv is the only record of hand-corrected matches;
# site/src/ holds what step 15 wrote. A path is left out of a run when it
# neither exists nor is tracked.
PUBLISHED = (
    "data/episodes.xlsx",
    "data/episodes.csv",
    "data/remaining films.xlsx",
    "data/upcoming.csv",
    "data/manual_review.csv",
    "site/src/data",
    "site/src/theme.css",
)
EPISODES_CSV = "data/episodes.csv"

# The tests that guard the published data, not the whole suite (~4 minutes).
QUICK_TESTS = ("tests/test_source_csv.py", "tests/test_export_site.py")


# ── git ───────────────────────────────────────────────────────────────────────

def git(*args, cwd=None, check=True):
    """Run git; return its stdout. Raises CalledProcessError when check fails."""
    result = subprocess.run(
        ["git", *args], cwd=cwd or config.ROOT, capture_output=True,
        text=True, encoding="utf-8",
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git", *args], result.stdout, result.stderr)
    return result.stdout


def current_branch(cwd=None):
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).strip()


def remote_url(cwd=None, name="origin"):
    """The remote's URL, or None when there is no such remote."""
    out = git("remote", "get-url", name, cwd=cwd, check=False).strip()
    return out or None


_GITHUB = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


def pages_url(remote):
    """Where GitHub Pages serves this repository's site, from its remote URL.

    A repository named <owner>.github.io is served at the domain root; any
    other at /<repo>/. None for a remote that is not on github.com.
    """
    match = _GITHUB.search(remote or "")
    if not match:
        return None
    owner, repo = match["owner"], match["repo"]
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def actions_url(remote):
    match = _GITHUB.search(remote or "")
    return (f"https://github.com/{match['owner']}/{match['repo']}/actions"
            if match else None)


def publishable_paths(cwd=None):
    """PUBLISHED, less any path that neither exists nor is tracked.

    git refuses a pathspec that matches nothing, so a file that has never
    existed -- manual_review.csv before the first review -- is dropped rather
    than failing the run. A tracked file that was deleted stays, so the
    deletion is committed.
    """
    root = cwd or config.ROOT
    keep = []
    for path in PUBLISHED:
        if (root / path).exists() or git("ls-files", "--", path, cwd=cwd).strip():
            keep.append(path)
    return keep


def changed_files(paths, cwd=None):
    """The changed files under `paths`, as (status, path) pairs.

    Read with -z so a path with a space ("remaining films.xlsx") comes back
    unquoted, and with untracked files listed one by one, so a new film page
    counts as one file rather than as its folder.
    """
    if not paths:
        return []
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all",
              "--", *paths, cwd=cwd)
    entries = [e for e in out.split("\0") if e]
    return [(e[:2].strip(), e[3:]) for e in entries]


def commit_published(message, paths, cwd=None):
    """Stage `paths` and commit them alone; return the new commit's hash.

    `git add -A -- paths` stages new, changed and deleted files under those
    paths only. `git commit -- paths` then commits just those paths, so
    anything else already in the index is left staged, not swept in.
    """
    git("add", "-A", "--", *paths, cwd=cwd)
    # Two -m flags make two paragraphs: the subject, then the body.
    subject, _, body = message.partition("\n\n")
    args = ["commit", "--quiet", "-m", subject]
    if body:
        args += ["-m", body]
    git(*args, "--", *paths, cwd=cwd)
    return git("rev-parse", "--short", "HEAD", cwd=cwd).strip()


def unpushed(cwd=None):
    """Commits on this branch that its upstream does not have.

    A branch with no upstream yet has never been pushed, so all of it counts:
    that is the first publish after the remote is added.
    """
    out = git("rev-list", "--count", "@{upstream}..HEAD", cwd=cwd, check=False).strip()
    if out.isdigit():
        return int(out)
    return int(git("rev-list", "--count", "HEAD", cwd=cwd).strip())


# ── What changed ──────────────────────────────────────────────────────────────

def _rows(text):
    return list(csv.DictReader(io.StringIO(text))) if text.strip() else []


def _key(row):
    # The episode number alone is not unique: the sheet reuses it when a film
    # is revisited (Notting Hill is episode 73 in 2019 and in 2024). Number,
    # date and title together are.
    return (row.get("ep", ""), row.get("date", ""), row.get("title", ""))


def episode_changes(before, after):
    """Episodes added, changed and removed between two renders of the CSV.

    An edit to any other column is "changed". An edit to the number, date or
    title reads as one episode removed and another added, which is what it is
    from the site's point of view.
    """
    old = {_key(r): r for r in _rows(before)}
    new = {_key(r): r for r in _rows(after)}
    return {
        "added": [new[k] for k in new if k not in old],
        "changed": [new[k] for k in new if k in old and new[k] != old[k]],
        "removed": [old[k] for k in old if k not in new],
    }


def describe(row):
    date = f" ({row['date']})" if row.get("date") else ""
    return f"Ep {row.get('ep', '?')}, {row.get('title', '?')}{date}"


def commit_message(changes, files):
    """A subject naming the episodes, and a body listing everything else."""
    added, changed, removed = changes["added"], changes["changed"], changes["removed"]
    if len(added) == 1:
        subject = f"Add episode {added[0].get('ep', '?')}: {added[0].get('title', '?')}"
    elif added:
        numbers = sorted({r.get("ep", "") for r in added}, key=lambda n: (len(n), n))
        subject = f"Add episodes {numbers[0]}-{numbers[-1]}"
    elif changed or removed:
        n = len(changed) + len(removed)
        subject = f"Update {n} episode{'s' if n != 1 else ''}"
    else:
        subject = "Refresh the published data"

    lines = ([f"Added: {describe(r)}" for r in added]
             + [f"Changed: {describe(r)}" for r in changed]
             + [f"Removed: {describe(r)}" for r in removed])
    site = [p for _, p in files if p.startswith("site/")]
    other = sorted({p for _, p in files if not p.startswith("site/")} - {EPISODES_CSV})
    if other:
        lines.append("Also: " + ", ".join(other))
    if site:
        lines.append(f"Site data: {len(site)} file{'s' if len(site) != 1 else ''}")
    lines.append("")
    lines.append("Published with scripts/publish.py.")
    return subject + "\n\n" + "\n".join(lines)


# ── Gates ─────────────────────────────────────────────────────────────────────

def pending_reviews(db_path):
    """Titles TMDB was not sure of and nobody has decided yet."""
    # sqlite3.connect creates a missing file, which would leave an empty
    # database where the real one belongs.
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT movie_title_raw, year_parsed FROM manual_review_queue "
            "WHERE queue_status = 'pending' ORDER BY movie_title_raw").fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [f"{t} ({y})" if y else str(t) for t, y in rows]


def confirm(question, ask=None):
    """True only for an explicit yes. No answer -- EOF, Ctrl+C -- is a no."""
    ask = ask or input   # looked up per call, not bound once at import
    try:
        return ask(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _run(args, what):
    logger.info(f"== {what}")
    return subprocess.run([sys.executable, *args], cwd=config.ROOT).returncode == 0


# ── The command ───────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-pipeline", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--allow-pending", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    branch = current_branch()
    if branch != PUBLISH_BRANCH and not args.dry_run:
        logger.error(f"On branch '{branch}'. Publishing commits to "
                     f"'{PUBLISH_BRANCH}': switch to it, or pass --dry-run.")
        return 1

    if not args.skip_pipeline:
        if not _run(["-m", "rewatchables.pipeline.orchestrate", "--from", "1"],
                    "Running the pipeline from step 01"):
            logger.error("The pipeline failed; nothing was committed. "
                         "Its log is the newest file in logs/.")
            return 1

    pending = pending_reviews(config.db_path())
    if pending:
        names = "\n".join(f"    {p}" for p in pending)
        if not args.allow_pending:
            logger.error(
                f"TMDB was not sure of {len(pending)} film(s):\n{names}\n"
                "Choose each in data/manual_review.csv (action, chosen_tmdb_id), "
                "then run publish again. Nothing was committed.\n"
                "To publish without them for now: --allow-pending.")
            return 2
        logger.warning(f"Publishing with {len(pending)} film(s) awaiting "
                       f"review; they stay off the site until decided:\n{names}")

    if not args.skip_tests:
        if not _run(["-m", "pytest", "-q", "-p", "no:cacheprovider", *QUICK_TESTS],
                    "Checking the published data"):
            logger.error("A check failed; nothing was committed.")
            return 1

    paths = publishable_paths()
    files = changed_files(paths)
    remote = remote_url()
    if files:
        before = git("show", f"HEAD:{EPISODES_CSV}", check=False)
        after = (config.ROOT / EPISODES_CSV).read_text(encoding="utf-8")
        message = commit_message(episode_changes(before, after), files)
        # The printed text stays ASCII: publish.bat's console on this machine
        # decodes as GBK, which garbles box-drawing characters and dashes.
        logger.info("== To publish\n" + message.rsplit("\n\nPublished with", 1)[0]
                    + f"\n({len(files)} file{'s' if len(files) != 1 else ''})")
    elif remote and unpushed():
        # Committed by an earlier run, before the remote existed or while
        # the push failed. Nothing new to commit, but it still has to go out.
        logger.info(f"== Nothing new to commit; {unpushed()} commit(s) not yet pushed.")
    else:
        logger.info("Nothing to publish: the published data matches the last commit.")
        return 0

    if args.dry_run:
        logger.info("Dry run: nothing committed or pushed.")
        return 0
    if not args.yes and not confirm("Publish this?"):
        logger.info("Not published. The files are as the pipeline left them.")
        return 2

    if files:
        sha = commit_published(message, paths)
        logger.info(f"Committed {sha} on {branch}.")

    if remote is None:
        logger.warning("No GitHub remote yet, so nothing was pushed. Once the "
                       "repository exists: git remote add origin <url>, then "
                       "run publish again -- it pushes what is waiting.")
        return 0
    push = subprocess.run(["git", "push", "--set-upstream", "origin", "HEAD"],
                          cwd=config.ROOT)
    if push.returncode != 0:
        logger.error("The push failed; the commit is saved locally. Fix the "
                     "cause and run: git push")
        return 1

    logger.info("Pushed. GitHub Actions is deploying the site, which takes a "
                "few minutes.")
    if actions_url(remote):
        logger.info(f"  Progress: {actions_url(remote)}")
    if pages_url(remote):
        logger.info(f"  Site:     {pages_url(remote)}")
    return 0


if __name__ == "__main__":
    config.setup_logging(format="%(message)s")
    sys.exit(main())
