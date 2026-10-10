# 011 — One command to publish a new episode

Date: 2026-10-10. Branch: `publish-command`, uncommitted. It carries the
uncommitted work it builds on: the step 14 posters and the site prototype from
[010](010_public_site_prototype.md).

## TL;DR

Adding an episode and publishing it is now two steps:

1. Edit `data/episodes.xlsx`, save, close.
2. `python scripts/publish.py`, or double-click `publish.bat`.

Done by hand, the same thing took six: edit, run the pipeline, review, stage
the right files, commit, push. Steps 4–6 were where mistakes happened: a stray
work-in-progress file staged, `site/` forgotten, a wrong TMDB match pushed.
`publish` does those three and checks the data before it does.

**Tried on the real workbook:** the dry run stopped at step 01 on the two rows
whose air dates are typed as text: ep 484, *The Texas Chain Saw Massacre*
(`'10/5/2026'`), and ep 485, *Friday the 13th* (`'10/12/2026'`). The CSV and
the workbook were byte-for-byte unchanged and nothing was committed. With the
pipeline skipped, the summary read "Add episodes 482-483", listing both films
and 465 files (462 of them site data, all new because `site/` has never been
committed).

**Tests:** 854 passed, 33 of them new, in `tests/test_publish.py`.

## What publish does

| Stage | Stops when | Override |
| --- | --- | --- |
| Branch check | Not on `master` | `--dry-run` works on any branch |
| Pipeline (`--from 1`) | Excel has a workbook open; a cell is invalid | `--skip-pipeline` |
| Review gate | A `pending` row in `manual_review_queue`; it names the films | `--allow-pending` |
| Quick checks | `test_source_csv.py` or `test_export_site.py` fails (about a minute) | `--skip-tests` |
| Summary | Nothing changed: prints "nothing to publish" and exits 0 | — |
| Confirm | Any answer except y/yes. End of input counts as no | `--yes` |
| Commit | — | — |
| Push | No remote: commits, warns, and pushes on a later run | — |

**What a commit may contain is a fixed list:** both workbooks, both CSVs,
`manual_review.csv`, `site/src/data/` and `site/src/theme.css`. The files are
staged with `git add -A -- <paths>` and committed with
`git commit -- <paths>`. Anything else already staged stays staged and is not
committed (tested). Deleted film pages are committed as deletions (tested).

**The commit message is written from the CSV diff** against `HEAD`. Episodes
are keyed on number, date and title, because the number alone repeats on a
revisit (Notting Hill, ep 73, in 2019 and 2024). A revisit is "added", an
edited cell is "changed" (both tested). Subjects read "Add episode 484: The
Texas Chain Saw Massacre", "Add episodes 482-483", "Update 2 episodes" or
"Refresh the published data".

**After the push, it prints the Actions and Pages links**, derived from the
remote URL. A repository named `<owner>.github.io` is served at the domain
root (tested).

## Other changes

- `.gitignore` now tracks `data/manual_review.csv`. It is the only record of
  hand-corrected matches, and it existed only on this machine.
- `README.md`: the episode routine leads with publish, there is a "Publishing"
  section, and the review section says the file is tracked.
- `publish.bat` at the repo root, for a desktop shortcut.

## Findings

1. **`sqlite3.connect` creates a missing database file.** The first draft of
   the review gate would have left an empty `rewatchables.db` behind on a
   fresh clone. A test caught it, and the gate now checks that the file exists.
2. **This console decodes as GBK.** Dashes and box-drawing characters came out
   garbled, so publish's own output and commit subjects are now ASCII. The
   orchestrator's arrows (`→`, `✓`) garble the same way. That predates this
   change and is left alone.

## Tests

- `tests/test_publish.py`, 33 cases. The pure parts cover change detection,
  subjects, the Pages URL, the confirm prompt and the review gate. End to end,
  in a throwaway git repository: a real run commits the episode and nothing
  else; a dry run, a declined prompt and the wrong branch each commit nothing;
  a pending review stops the run unless `--allow-pending` is passed; and a run
  with nothing changed does nothing.
- Full suite, with the workbook test deselected as in 010: **854 passed**.

## Before the first real publish

Publish commits data, not code. The code it depends on is still uncommitted:
step 14, step 15, `site/`, the workflow and publish itself. That needs one
ordinary commit to `master` first. Then:

1. Create the GitHub repository and `git remote add origin <url>`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Fix the two date cells in the workbook.
4. Run `publish`.
