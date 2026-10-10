---
title: All films
---

```js
// Every film, filtered in the browser. The rows are step 15's films.json; the
// filters are the first of the Movie Explorer's, as a test of how its widgets
// carry over.
import {filmCard, grid, gridNote, masthead} from "./components/ui.js";

const films = FileAttachment("data/films.json").json();
```

```js
display(masthead("All films", "Every film the show has covered. Click a poster for its episodes, the room and the film."));
```

```js
const decades = [...new Set(films.map((f) => f.decade).filter((d) => d != null))].sort();
const genres = [...new Set(films.flatMap((f) => f.genres))].sort();

const searchInput = Inputs.text({label: "Search title", placeholder: "Heat, Point Break…"});
const decadeInput = Inputs.select([null, ...decades], {label: "Decade", format: (d) => (d == null ? "All" : `${d}s`)});
const genreInput = Inputs.select([null, ...genres], {label: "Genre", format: (g) => g ?? "All"});
const sortInput = Inputs.select(new Map([
  ["Year, oldest first", "year"],
  ["Year, newest first", "-year"],
  ["Title", "title"],
  ["TMDB rating", "tmdb"],
  ["Most episodes", "episodes"]
]), {label: "Sort by"});

display(html`<div class="rw-filters">${searchInput}${decadeInput}${genreInput}${sortInput}</div>`);

const search = Generators.input(searchInput);
const decade = Generators.input(decadeInput);
const genre = Generators.input(genreInput);
const sort = Generators.input(sortInput);
```

```js
const q = search.trim().toLowerCase();
const shown = films
  .filter((f) => !q || f.title.toLowerCase().includes(q))
  .filter((f) => decade == null || f.decade === decade)
  .filter((f) => genre == null || f.genres.includes(genre));

// Missing ratings sort last whichever way, rather than as zero.
const by = {
  "year": (a, b) => a.year - b.year || a.sort.localeCompare(b.sort),
  "-year": (a, b) => b.year - a.year || a.sort.localeCompare(b.sort),
  "title": (a, b) => a.sort.localeCompare(b.sort),
  "tmdb": (a, b) => (b.tmdb ?? -1) - (a.tmdb ?? -1),
  "episodes": (a, b) => b.episodes - a.episodes || a.sort.localeCompare(b.sort)
}[sort];
shown.sort(by);

display(gridNote(`${shown.length} of ${films.length} films`));
display(shown.length
  ? grid(shown.map((f) => filmCard(f, String(f.year), "./")))
  : html`<p class="rw-ov-note">No film matches those filters.</p>`);
```
