---
title: Genres
---

```js
// The app's Genres section. The charts are sections/genres.figures(), run by
// pipeline step 15; the "Browse by genre" shelf filters films.json here, as
// the app's selectbox filters its frame.
import {filmCard, gridNote, grid, masthead, tape, trail} from "./components/ui.js";
import {plot} from "./components/plot.js";

const g = FileAttachment("data/sections/genres.json").json();
const films = FileAttachment("data/films.json").json();
```

```js
const chart = (name) => resize((width) => plot(g.figures[name], width));

display(masthead("Genres", "How the mix shifts across the decades they cover."));
display(html`<div class="rw-cols c32">
  <div>${tape("Genre frequency")}${chart("frequency")}</div>
  <div>${tape("Share of films with each genre")}${chart("share")}</div>
</div>`);
```

```js
display(tape("Genre popularity by decade"));
display(chart("by_decade"));
```

```js
display(tape("Genre co-occurrence (films with both genres)"));
if (g.figures.co_occurrence) display(chart("co_occurrence"));
```

```js
display(tape("Browse by genre"));
const genres = [...new Set(films.flatMap((f) => f.genres))].sort();
const pick = view(Inputs.select(genres, {label: "Pick a genre"}));
```

```js
// Best rated first, as the app sorts its shelf; films with no rating last.
const tagged = films.filter((f) => f.genres.includes(pick))
  .sort((a, b) => (b.tmdb ?? -1) - (a.tmdb ?? -1) || a.id.localeCompare(b.id));
const shelf = tagged.slice(0, g.shelf);
display(gridNote(`${tagged.length} films tagged ${pick}`, tagged.length > g.shelf ? `the top ${g.shelf} by TMDB rating` : "by TMDB rating"));
display(trail(grid(shelf.map((f) => filmCard(f, String(f.year), "./"))), pick, shelf.map((f) => f.id)));
```
