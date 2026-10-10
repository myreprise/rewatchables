# 012 — Film addresses that survive a rebuild

Date: 2026-10-10. Branch: `master`, uncommitted.
Previous: [011 — the publish command](011_publish_command.md).

## TL;DR

A film is now addressed by its title and year in both front ends:
`/movie/heat-1995` on the public site, `?movie=heat-1995` in the Streamlit app.

**The problem it fixes.** Both used to address a film by `movie_id`. Step 06
mints a fresh `uuid4` for every film each time it rebuilds the curated zone,
which `--from 1` does on every publish. The first real publish (episodes
484–485) reissued **all 458** existing ids. Every film URL changed, and the
commit touched 465 files to add two episodes. The live site briefly 404'd on
the old addresses.

**Measured:** 460 films, 460 unique addresses, no collisions. With every
`movie_id` reissued and the films shuffled, the export is byte-for-byte
identical (tested). A one-episode publish will now commit a handful of files,
not 465.

## What changed

- `views.py`: `slugify(title, year)` and `film_slugs(movies)` are the one
  definition of an address, shared by the app and step 15. An address is
  lower-case words joined by hyphens, then the year:
  - apostrophes are dropped (`oceans-eleven-2001`);
  - `&` becomes `and`, and accents fold to ASCII;
  - any other punctuation separates words (`face-off-1997`).

  If two films ever share a title and year, only those two take their TMDB id
  as a suffix.
- `app/data.py`: `load_data` adds `movies["slug"]`.
- `app/state.py`: `open_dossier` writes the address to `?movie=`.
  `seed_from_url` reads it back through `film_from_address`. A bare `movie_id`
  is still accepted while it is current, so an old link keeps working until the
  next rebuild. Inside the app a film is still keyed by `movie_id`, so no call
  site changed.
- `s15_export_site.py`: page files and every `id` the site sees are addresses.
  No `movie_id` reaches the site (tested). Films are sorted by year and address
  before export, so ties land the same way whatever order step 06 inserted
  them in.

## Checked in the browser

- App: `?movie=heat-1995&from=explorer` opens Heat's dossier on a cold load.
  Clicking Thief on its director shelf changes the URL to
  `?movie=thief-1981&from=explorer`.
- Site (dev preview): `/movie/heat-1995` renders. Shelf and overview links
  point at addresses (`../movie/thief-1981`, `./movie/friday-the-13th-1980`).

## Not changed

`movie_id` itself is still a fresh `uuid4` per rebuild. Nothing user-facing
depends on it now, and every API cache is keyed on `tmdb_id`, so this costs
nothing visible. Deriving it from `tmdb_id` in step 06 remains an option if
something internal ever needs it stable.

An address changes only if TMDB corrects a film's title or year.

## Tests

New: 11 slug cases, the collision suffix, independence from `movie_id`,
unique and URL-safe addresses, no `movie_id` in any exported file, and the
reissued-and-shuffled rebuild. Updated: the app's deep-link tests use
`heat-1995`, and one pins that a current `movie_id` still opens. Full suite:
**873 passed**, with nothing deselected now that the workbook's two dates are
fixed.
