# 016 — Site parity, phase 4: Upcoming, the doors, and parity

Date: 2026-10-11. Branch: `master`.
Previous: [015 — phase 3, the people sections](015_site_parity_phase3.md).

## TL;DR

**The public site now has every section of the Streamlit app.** This phase
adds:
- **Upcoming Films**, with one page per requested film (210);
- **the Overview's eleven "Go deeper" doors**, one into each section;
- **computed captions** for the two scatter charts, which were typed into the
  app as fixed text and had gone stale.

| | Phase 0 (2026-10-10) | Now |
| --- | ---: | ---: |
| App sections on the site | 3 of 12 | 12 of 12 |
| Pages | 462 | about 2,060 |
| Charts | 1 | 33, plus 2 on each of 40 spotlights |
| Tests | 873 | 888 (887 pass; see below) |

## What changed

### The captions were stale; now they are computed

Directors said "r = 0.30 across these 97" and Actors "r = 0.08", both typed
into the app. Recomputed on today's database, both are Pearson correlations
of films covered against average TMDB:

| | Caption said | Now |
| --- | --- | --- |
| Directors with 2+ films | r = 0.30 across 97 | r = 0.30 across **99** |
| Actors with 3+ films | r = 0.08 | r = **0.07** |

`directors.volume_reception()` and `actors.volume_reception()` compute them.
The app and the site both print the results, so the captions now update with
the data.

The words around the numbers ("weakly related", "absent") are still fixed
text. They fit both values today. A large shift in the data would need them
rewritten.

### Upcoming

- **The app:**
  - `sections/upcoming.py` gains `queue_summary()`, `tag_counts()`,
    `shared_tags()` and `unmatched()`, which its `render()` now calls.
  - The filters stay in the app's `render()`. On the site they run in the
    browser instead.
- **Step 15:** `site_export/upcoming.py` writes `upcoming.json` (every request
  with its reason, the graduates and the unmatched) and one file per request.
  - **Addresses:** each request's address is its title and year
    (`alien-3-1992`). Where there is no single year, it is the title alone. A
    clash is broken in source order. `upcoming_film_id` is not used, because
    the list is rebuilt on every run.
- **Site:**
  - **`upcoming.md`:** tiles; the four filters (search over title, note, pitch
    and contributor; decade; pitch tag; sort); the grid; "Why these films" for
    the first 12; the top 24 pitch tags; the graduates, linked to their film
    pages; and the unmatched, linked to their request pages.
  - **`upcoming/[id].md`:** the prospect overlay. It has the hero, the
    unmatched note, why the film is on the list and who put it there, the
    pitch, the plot, the cast and the TMDB link.
  - **Sidebar:** gains "On deck".

### The Overview's doors

`overview.doors()` is the list the app draws its "Go deeper" doors from. Each
door gets the section's group, its number in the rail, its label, its one
number and its blurb. The app draws them from it, and step 15 exports them
too. On the site each door links to its page. Before, the site had a single
door, to All films.

One change in the app: the Timeline door's "2015&ndash;2026" is now written
with the character itself, "2015–2026", so the same text works on both. It
looks the same.

### The site's poster card

`posterCard()` is `filmCard()` with any link, so a requested film's card
opens its own page. `whyPanel()` is the app's `why_html`.

## Checked

- **Tests:** 887 pass and 1 fails. The failure is
  `test_the_workbook_renders_to_exactly_the_tracked_csv`, and it is not from
  this change. `data/episodes.xlsx` was saved at 09:21 on 2026-10-11 with
  edits not yet run through the pipeline, and it was open in Excel during the
  run, so the test could not read it. It should pass again once the workbook
  is closed and published. The 3 new tests check:
  - every request has a page, and the Upcoming numbers equal
    `queue_summary()`;
  - every door leads to a page the site has;
  - both captions equal `volume_reception()`.
  - The rebuild test now reissues `movie_id` in `graduated` too. It had been
    left out, which made the graduates' links look broken in the test.
- **Headless Chrome against the dev server:**
  - **Overview:** 11 doors, in the app's order.
  - **Upcoming:** 210 cards. "fincher" finds 3, *Alien 3* among them, and
    opening it shows the request page with the reason and contributor.
  - **"Pitched as: 1980s":** 14 films, the same count the export gives.
  - **Directors:** reads "r = 0.30 across these 99"; Actors reads "r = 0.07".
- **One bug found and fixed:** a variable named `view` on the Upcoming page
  collided with Framework's built-in `view()`. "Why these films" failed until
  it was renamed.

## The parity plan, closed

| Phase | Report | What |
| --- | --- | --- |
| 0 | 012 | Film addresses that survive a rebuild |
| 1 | 013 | Explorer, keyword pages, person pages, linked chips |
| 2 | 014 | Genres, Ratings, Box Office, Timeline, Cruise vs. Hanks |
| 3 | 015 | Hosts & Guests, Directors, Actors, spotlights |
| 4 | 016 | Upcoming, the doors, computed captions |

**How the two front ends stay in step:** a section's calculations live in
named functions, and both its Streamlit `render()` and step 15 call them.
`tests/test_export_site.py` checks the site's numbers against the app's, and
checks that every link lands on a page. A new feature goes into the app's
function first. The site README says so under "Keeping it in step with the
app".

## Not done

- **Spotlights for every director and actor in the tables** (see 015), beyond
  the app's top 20.
- **The site has no "data is stale" banner.** The app's banner compares the
  workbook's save time with the last pipeline run, and the site has neither.
  The Overview's "as of" date does that job.
