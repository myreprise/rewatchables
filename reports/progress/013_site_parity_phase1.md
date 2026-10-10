# 013 — Site parity, phase 1: the Explorer, keywords and people

Date: 2026-10-11. Branch: `master`.
Previous: [012 — film addresses that survive a rebuild](012_stable_film_addresses.md).

## TL;DR

The public site now covers the Streamlit app's Movie Explorer, its Keywords
section and keyword overlay, and the Hosts & Guests lookup, and its pages link
to one another the way the app's do.

| | Before | After |
| --- | ---: | ---: |
| Pages | 462 | 1,789 |
| Film pages | 460 | 460 |
| Keyword pages (keywords on 2+ films) | 0 | 1,265 |
| Person pages (everyone but Bill Simmons) | 0 | 62 |
| Explorer filters / sort orders | 3 / 5 | 6 / 9 (the app's) |
| Tests | 873 | 881 |

**Checked against the app.** With the Explorer filtered to Crime and RT ≥ 90
and sorted by RT, the site shows 32 films in the same order as the app's
filter code, run in Python on the same database. The export tests compare
keyword pages with the overlay's `keyword_profile()` and person pages with the
Hosts lookup's own numbers.

## The plan this belongs to

This is phase 1 of 4 in bringing the site up to the app, as agreed on
2026-10-10:

1. **Phase 0: the stable addresses from 012.** Released. Live since `c8944ce`.
2. **Phase 1: the Explorer, keywords and people.** This report.
3. **Phase 2: Ratings, Box Office, Timeline, Genres, Cruise vs. Hanks.** These
   are fixed charts, shipped as the app's Plotly figures.
4. **Phase 3: Hosts & Guests in full, Directors, Actors**, with their spotlights.
5. **Phase 4: Upcoming and requested-film pages**, the Overview's "Go deeper"
   doors and spotlight, and navigation grouped like the app's.

## What changed

### Step 15 is now a package

`s15_export_site.py` had grown to 394 lines for three kinds of page. It now
only runs the export. The work is in `pipeline/site_export/`, one module per
kind of page:

| Module | Writes |
| --- | --- |
| `common` | Nothing itself: JSON helpers, `write_pages()` (which also removes stale pages), `prepare()`, `Addresses`, `card()` |
| `films` | `films.json`, `films/<slug>.json` |
| `overview` | `overview.json`, `charts/*.json` |
| `keywords` | `keywords.json`, `keywords/<slug>.json` |
| `people` | `people.json`, `people/<slug>.json` |

`prepare()` sorts the films and also rebuilds the keyword index from that
sorted frame. That matters because the app's `keyword_index` is cached on the
database stamp alone (the frame is unhashed), so two different frames under
one stamp would share an index. The new `build_keyword_index()` in
`app/data.py` is the uncached body, and the cached loader calls it.

**Addresses for keywords and people** come from `views.name_slugs()`:
`writer's block` → `writers-block`, `Chris Ryan` → `chris-ryan`. A name has no
TMDB id to break a tie with, so a collision gets `-2`, then `-3`, in sorted
order. There are none today.

### The app's calculations are named functions now

The pattern is the same as for the Overview in 010: the calculation comes out
of `render()`, `render()` calls it, and step 15 calls it too.

- **`sections/keywords.py`:** `vocabulary()`, `search_vocabulary()`,
  `reach_bands()`, `signature_by_decade()`.
- **`overlays/keyword.py`:** `keyword_profile()`, which returns every number
  the overlay prints.
  - One deliberate change: "Travels with" partners tied on count now sort
    alphabetically. They used to come out in database insertion order, which
    changes on a rebuild, so the app's chips could reorder between runs and
    the export would not have been deterministic.
- **`sections/hosts.py`:** `the_room()`, `regular_leans()`, `sits_with()`,
  `verdict_tally()`.

### Site pages

- **Movie Explorer** (`films.md`, renamed from "All films"):
  - Filters: title search, director, genre (any of), decade, minimum RT,
    minimum TMDB.
  - The app's nine sort orders, with its tie-break on first airing.
  - The card caption swaps between RT score and air date as the app's does.
  - The data table, collapsed under the grid.
  - The filters live in the address: `/films?genre=Crime&rt=90&sort=rt` can be
    shared, and Back from a film returns to the same view.
- **The trail:** a film page opened from a list shows "Back to …", ‹ › arrows
  and "Film 4 of 9", as the app's dossier does. Three lists set it: the
  Explorer, a keyword's films, and a person's episodes. The list is kept in
  session storage, so a film reached any other way has a plain back link, as
  before.
- **Film pages:**
  - Keyword chips link to their pages; a keyword on one film stays inert.
  - Everyone in the room, Bill aside, links to their person page.
- **Keywords** (`keywords.md`): tiles, search over all 3,676 keywords, the
  five reach bands, and each decade's signature with linked keywords.
- **Keyword pages** (`keyword/[id].md`): the overlay's tiles, region line,
  decade bars, "Travels with" chips and film grid.
- **Person pages** (`person/[id].md`):
  - The lookup's tiles and the person's episodes, newest first.
  - "Who they sit with", linked.
  - Their permutation-tested leans, or the app's note when they are below
    the 15-episode floor.
  - Their Cruise vs. Hanks record.
  - The "Look someone up" picker moves between person pages.
- **Overview:** the regulars' names link to their pages.

## Size and time

| What a visitor downloads (data only) | Raw | Gzipped |
| --- | ---: | ---: |
| Movie Explorer: `films.json` | 294 KB | 96 KB |
| Keywords: `keywords.json` (whole vocabulary) | 341 KB | 34 KB |
| Keyword page, e.g. heist (median page 2.2 KB) | 4.3 KB | 1.4 KB |
| Person page, largest (Chris Ryan, 287 episodes) | 55 KB | 16 KB |

- **Export:** 22 s, writing 8.1 MB of JSON.
- **Build:** 274 s locally, mostly writing files into OneDrive. 32 MB in
  `dist/` (11 MB of it keyword pages), well inside Pages' 1 GB limit.
- **`publish`'s quick checks** now take about 2.5 minutes instead of about one,
  because `test_export_site.py` runs the export three times: once, then again
  to check it is deterministic, and once over a simulated rebuild.

## Checked

- **Tests:** 881 pass. The 8 new ones in `test_export_site.py` check:
  - a keyword has a page exactly when its chip links;
  - keyword pages match `keyword_profile()`;
  - everyone but the anchor has a person page;
  - person pages match the lookup;
  - every link in the data lands on a page that exists;
  - `films.json` carries the Explorer's RT and director;
  - `name_slugs()` collisions, and `write_pages()` removing stale pages.
  - The existing rebuild test (every `movie_id` reissued, films shuffled)
    still produces byte-identical output, keyword and person pages included.
- **Headless Chrome, against the dev server and against the production build
  under `/rewatchables/`**, clicking through:
  - Explorer (filtered) → film page ("Film 4 of 9") → next film.
  - Film page → Back, which returns to the same filters.
  - Film page → keyword chip → keyword page.
  - Film page → person → a companion's page.
  - Overview regular → person page.
  - Keywords signature → keyword page.
  - The Claude browser pane was hidden for this session, which stalls
    Framework's runtime, so these checks ran in a separate headless Chrome.

## Not done, and why

- **The rating filters are minimums, not the app's two-ended ranges.**
  Framework's built-in slider takes one value. A maximum RT or TMDB filter is
  rarely what anyone wants, and two sliders per score crowded the row. This
  can be revisited with a custom range input.
- **Several directors at once.** The director filter is a text box with
  suggestions that matches part of a name ("mann" finds Michael Mann), rather
  than the app's multiselect. A native multiselect needs Ctrl-click, which
  most visitors won't know to do.
- **A shelf film on a film page** opens without arrows unless it happens to be
  on the list the visitor came from. This matches the app, where a shelf click
  starts a fresh dossier.
- **The bench table, heatmaps and lean panel of Hosts & Guests** are phase 3.
  For now the person pages are reached from film pages, the Overview's
  regulars and each other.
