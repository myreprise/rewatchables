---
title: Ratings
---

```js
// The app's Ratings section. The charts are its own figures, built by
// sections/ratings.figures() in pipeline step 15; the divergence tables are
// its divergence(). This page lays them out.
import {filmLink, masthead, table, tape} from "./components/ui.js";
import {plot} from "./components/plot.js";

const r = FileAttachment("data/sections/ratings.json").json();
```

```js
display(masthead("Ratings", "Rotten Tomatoes, Ebert stars and TMDB audience scores, side by side."));
const f = r.figures;
const chart = (name) => resize((width) => plot(f[name], width));

display(html`<div class="rw-cols c3">
  <div>${tape("Rotten Tomatoes scores")}${chart("rt")}</div>
  <div>${tape("Ebert star ratings")}${chart("ebert")}</div>
  <div>${tape("TMDB audience rating")}${chart("tmdb")}</div>
</div>`);
```

```js
display(tape("Rotten Tomatoes vs TMDB rating"));
display(chart("rt_vs_tmdb"));
```

```js
display(tape("RT score distribution by genre"));
display(chart("rt_by_genre"));
```

```js
// RT against TMDB scaled to 100: the films the critics and the audience
// disagree on most, each way.
display(tape("Ratings divergence — critics vs audience"));
const columns = [
  ["Film", (x) => filmLink(x, "./")],
  ["Year", (x) => x.year, true],
  ["RT %", (x) => x.rt.toFixed(0), true],
  ["TMDB", (x) => x.tmdb.toFixed(1), true],
  ["Δ", (x) => `${x.diff > 0 ? "+" : ""}${x.diff.toFixed(1)}`, true]
];
display(html`<div class="rw-cols c2">
  <div><p class="rw-sub">Critics love, audiences cooler on</p>${table(r.critics_love, columns)}</div>
  <div><p class="rw-sub">Audiences love, critics cooler on</p>${table(r.audiences_love, columns)}</div>
</div>`);
```
