---
title: Movie Explorer
---

```js
// The Movie Explorer: every film, filtered and sorted in the browser. The rows
// are the explorer query on site.db, from the same frame the app's Explorer reads.
// The filters live in the address (?genre=Drama&sort=rt), so a filtered view
// can be shared, and a film opened from here steps through this list.
import {filmCard, fmt, grid, gridNote, masthead, stars, trail} from "./components/ui.js";

import {films as allFilms} from "./components/db.js";

const films = await allFilms();
```

```js
display(masthead("Movie Explorer", "Filter and search every film they have covered. Click a poster for its episodes, the room and the film."));
```

```js
// The app's nine orders. Every key but the date breaks ties on first airing,
// newest first: ties are the rule (Ebert stars take eight values across 370
// films), and without a second key the grid would reshuffle between visits.
const SORTS = new Map([
  ["Episode date (newest)", ["first", false]],
  ["Episode date (oldest)", ["first", true]],
  ["Title", ["sort", true]],
  ["Year (newest)", ["year", false]],
  ["Year (oldest)", ["year", true]],
  ["TMDB Rating", ["tmdb", false]],
  ["RT Score", ["rt", false]],
  ["Ebert Score", ["ebert", false]],
  ["Runtime", ["runtime", false]]
]);
const SORT_KEYS = {first: "date-new", sort: "title", year: "year", tmdb: "tmdb", rt: "rt", ebert: "ebert", runtime: "runtime"};
const sortSlug = (label) => {
  const [key, asc] = SORTS.get(label);
  return key === "first" ? (asc ? "date-old" : "date-new")
    : key === "year" ? (asc ? "year-old" : "year-new") : SORT_KEYS[key];
};
const sortFromSlug = (slug) => [...SORTS.keys()].find((label) => sortSlug(label) === slug) ?? "Episode date (newest)";

// The address is read once, to seed the inputs; from then on the inputs write it.
const params = new URLSearchParams(location.search);
const listParam = (name) => (params.get(name) ?? "").split("|").filter(Boolean);

const genres = [...new Set(films.flatMap((f) => f.genres))].sort();
const decades = [...new Set(films.map((f) => f.decade).filter((d) => d != null))].sort();
const directors = [...new Set(films.map((f) => f.director).filter(Boolean))].sort();

const searchInput = Inputs.text({label: "Search title", placeholder: "Heat, Point Break…", value: params.get("q") ?? ""});
const directorInput = Inputs.text({label: "Director", placeholder: "Michael Mann…", datalist: directors, value: params.get("director") ?? ""});
const sortInput = Inputs.select([...SORTS.keys()], {label: "Sort by", value: sortFromSlug(params.get("sort"))});
const rtInput = Inputs.range([0, 100], {label: "RT score at least", step: 1, value: Number(params.get("rt") ?? 0)});
const tmdbInput = Inputs.range([0, 10], {label: "TMDB at least", step: 0.1, value: Number(params.get("tmdb") ?? 0)});
const decadeInput = Inputs.checkbox(decades, {label: "Decade", format: (d) => `${d}s`, value: listParam("decade").map(Number)});
const genreInput = Inputs.checkbox(genres, {label: "Genre", value: listParam("genre")});

display(html`<div class="rw-filters">${searchInput}${directorInput}${sortInput}</div>`);
display(html`<details class="rw-more rw-filter-more" open=${["genre", "decade", "rt", "tmdb"].some((k) => params.has(k))}>
  <summary>More filters — genre, decade, ratings</summary>
  <div class="rw-filters">${rtInput}${tmdbInput}</div>
  <div class="rw-filters">${decadeInput}</div>
  <div class="rw-filters">${genreInput}</div>
</details>`);

const search = Generators.input(searchInput);
const director = Generators.input(directorInput);
const sortBy = Generators.input(sortInput);
const rtMin = Generators.input(rtInput);
const tmdbMin = Generators.input(tmdbInput);
const pickedDecades = Generators.input(decadeInput);
const pickedGenres = Generators.input(genreInput);
```

```js
// The Explorer's filters. A film with no score passes a score filter, as in
// the app: coverage is partial, and a missing number is not a low one.
const q = search.trim().toLowerCase();
const who = director.trim().toLowerCase();
const shown = films
  .filter((f) => !q || f.title.toLowerCase().includes(q))
  .filter((f) => !pickedGenres.length || pickedGenres.some((g) => f.genres.includes(g)))
  .filter((f) => !pickedDecades.length || pickedDecades.includes(f.decade))
  .filter((f) => !who || (f.director ?? "").toLowerCase().includes(who))
  .filter((f) => f.rt == null || f.rt >= rtMin)
  .filter((f) => f.tmdb == null || f.tmdb >= tmdbMin);

// Missing values sort last whichever way, as pandas' na_position="last".
const [key, asc] = SORTS.get(sortBy);
const compare = (a, b, k, ascending) => {
  const x = a[k], y = b[k];
  if (x == null || y == null) return (x == null) - (y == null);
  const c = typeof x === "string" ? x.localeCompare(y) : x - y;
  return ascending ? c : -c;
};
shown.sort((a, b) => compare(a, b, key, asc)
  || (key === "first" ? 0 : compare(a, b, "first", false))
  || a.id.localeCompare(b.id));

// Keep the address in step, leaving defaults out of it.
const out = new URLSearchParams();
if (q) out.set("q", search.trim());
if (who) out.set("director", director.trim());
if (pickedGenres.length) out.set("genre", pickedGenres.join("|"));
if (pickedDecades.length) out.set("decade", pickedDecades.join("|"));
if (rtMin > 0) out.set("rt", rtMin);
if (tmdbMin > 0) out.set("tmdb", tmdbMin);
if (sortBy !== "Episode date (newest)") out.set("sort", sortSlug(sortBy));
history.replaceState(null, "", out.size ? `?${out}` : location.pathname);

// The card's caption holds two facts: the year, then the airdate when sorting
// by it and the RT score otherwise.
const caption = (f) => key === "first"
  ? `${f.year}${f.first ? ` · ${fmt.monYear(f.first)}` : ""}`
  : `${f.year}${f.rt != null ? ` RT ${Math.round(f.rt)}%` : ""}`;

display(gridNote(`${shown.length} of ${films.length} films match your filters`, "click a poster for its dossier"));
display(shown.length
  ? trail(grid(shown.map((f) => filmCard(f, caption(f), "./"))), "the Explorer", shown.map((f) => f.id))
  : html`<p class="rw-ov-note">No film matches those filters.</p>`);
```

```js
// The app's data table, under the grid, in the same order.
display(html`<details class="rw-more">
  <summary>Data table — ${shown.length} films</summary>
  ${Inputs.table(shown, {
    columns: ["title", "year", "first", "director", "runtime", "tmdb", "rt", "ebert", "episodes"],
    header: {title: "Title", year: "Year", first: "First episode", director: "Director", runtime: "Runtime",
             tmdb: "TMDB", rt: "RT score", ebert: "Ebert", episodes: "Episodes"},
    format: {year: String, tmdb: (v) => v?.toFixed(1) ?? "", rt: (v) => (v == null ? "" : `${Math.round(v)}%`),
             ebert: (v) => stars(v) ?? "", first: (v) => (v ? fmt.dayMonYear(v) : "")},
    rows: 16, layout: "auto", select: false
  })}
</details>`);
```
