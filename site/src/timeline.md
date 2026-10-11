---
title: Timeline & Revisits
---

```js
// The app's Timeline & Revisits section: its figures(), oldest_discussed() and
// revisited_films(), run by pipeline step 15.
import {filmCard, filmLink, grid, masthead, table, tape, trail} from "./components/ui.js";
import {plot} from "./components/plot.js";

const t = FileAttachment("data/sections/timeline.json").json();
```

```js
const chart = (name) => resize((width) => plot(t.figures[name], width));

display(masthead("Timeline & Revisits", "When the episodes landed, how old the films were when they did, and the few they came back to."));
display(tape("Episodes per year"));
display(chart("per_year"));
```

```js
display(tape("Films by release decade and genre"));
display(chart("decade_genre"));
```

```js
display(tape("How old were films when featured? (episode year − release year)"));
display(html`<div class="rw-cols c2">
  <div>${chart("age")}</div>
  <div>${tape("Oldest films discussed")}${table(t.oldest, [
    ["Film", (x) => filmLink(x, "./")],
    ["Year", (x) => x.year, true],
    ["Episode year", (x) => x.aired, true],
    ["Age (yrs)", (x) => x.age, true]
  ])}</div>
</div>`);
```

```js
display(tape("Average TMDB rating by release decade"));
display(chart("rating_by_decade"));
```

```js
display(tape("Episode timeline colored by primary genre"));
display(chart("genre_strip"));
```

```js
// Was its own section in the app; the films the sheet flags as revisited read
// better as the closing movement of the timeline.
display(tape("Films they came back to"));
display(html`<div class="rw-tile"><div class="k">Revisited films</div><div class="v">${t.revisited.length}</div></div>`);
display(tape("The Rewatchables hall of fame (revisited films)"));
display(trail(grid(t.revisited.map((f) => filmCard(f, `${f.year} · ${f.episodes}×`, "./"))),
              "the revisited films", t.revisited.map((f) => f.id)));
```

```js
display(tape("When did revisits happen?"));
display(t.figures.revisits ? chart("revisits") : html`<p class="rw-ov-note">No revisit episode links found.</p>`);
```

```js
display(tape("Time between first and last episode"));
display(chart("revisit_gaps"));
```

```js
display(tape("Genre breakdown of revisited films"));
display(chart("revisit_genres"));
```
