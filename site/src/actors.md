---
title: Actors
---

```js
// The app's Actors section: cast_counts(), gender_credits(), gender_peaks(),
// figures(), the gender-split leaderboards and ranked_actors(), run by
// pipeline step 15. Each name in the spotlight picker has a page at /actor/<slug>.
import {masthead, note, statRail, statTile, tape} from "./components/ui.js";
import {plot} from "./components/plot.js";
import {spotlightPicker} from "./components/spotlight.js";

const a = FileAttachment("data/sections/actors.json").json();
```

```js
const t = a.tiles;
const chart = (fig) => resize((width) => plot(fig, width));
const credits = Object.fromEntries(a.credits.map((c) => [c.gender, c]));
const share = (g) => `${credits[g].credits.toLocaleString()} · ${Math.round(100 * credits[g].credits / a.credits_total)}%`;

display(masthead("Actors", "Who keeps turning up on screen, and the films they turn up in."));
display(statRail([
  statTile("Actors", t.actors.toLocaleString()),
  statTile("Just one film", t.one.toLocaleString()),
  statTile("Three or more", t.three_plus.toLocaleString()),
  statTile("Five or more", t.five_plus.toLocaleString()),
  statTile("Films covered", t.films.toLocaleString())
]));
// Every gender with a credit gets a tile, including the two the split below
// has no column for, as in the app.
if (a.gendered) {
  const tiles = [statTile(credits.M.label, share("M")), statTile(credits.F.label, share("F"))];
  if (credits.NB.credits) tiles.push(statTile(credits.NB.label, credits.NB.credits.toLocaleString()));
  tiles.push(statTile(credits.unknown.label, credits.unknown.credits.toLocaleString()));
  display(html`<div style="height:10px"></div>`);
  display(statRail(tiles));
  display(html`<p class="ch-note">Billed credits, not people: a film contributes ten cast slots, and who gets cast is a question about slots. One actor in five films is five credits.</p>`);
}
```

```js
display(tape("Most-featured actors"));
display(chart(a.figures.leaderboard));
display(html`<p class="ch-note">Every credited name TMDB lists, so a supporting turn counts the same as a lead. That widens the field considerably: ${t.one.toLocaleString()} of these ${t.actors.toLocaleString()} appear in a single film.</p>`);
```

```js
if (a.gendered) {
  display(tape("Most-featured actors, by gender"));
  display(html`<div class=${`rw-cols c${a.by_gender.length}`}>${a.by_gender.map((g) => html`<div>
    <p class="ch-note" style="margin:0 0 2px"><b>${g.label}</b> · ${g.actors.toLocaleString()} actors</p>
    ${chart(g.figure)}
  </div>`)}</div>`);
  display(html`<p class="ch-note">Both columns share one x-axis, so the gap is the finding rather than a rendering accident: the most-featured man has <b>${a.men_top}</b> covered films against <b>${a.women_top}</b> for the most-featured woman. ${a.first_woman ? html`The first woman in the combined ranking above is at <b>#${a.first_woman}</b>. ` : ""}Gender is what TMDB records for the credited performer; ${credits.unknown.credits.toLocaleString()} of ${a.credits_total.toLocaleString()} credits have none recorded and are counted in neither column.</p>`);
}
```

```js
display(tape("Actor spotlight"));
display(note("Pick an actor for their covered films, the shape of the work, and the directors they return to."));
display(spotlightPicker(a.spotlight, "actor", "./"));
```

```js
display(tape("Volume against reception"));
display(chart(a.figures.scatter));
display(html`<p class="ch-note">Actors with three or more covered films; bubble size is average runtime. Only those with eight or more are named — the rest are on hover. For actors the link between being cast often and being in well-rated films is <b>absent — r = ${a.r.toFixed(2)}</b>. Of ${t.actors.toLocaleString()} actors, ${t.named} clear eight films.</p>`);
```

```js
// Gender is a column rather than a filter, as in the app: the table sorts.
display(tape("Every actor with 3+ films"));
display(Inputs.table(a.table, {
  columns: ["name", "gender", "films", "tmdb", "rt", "runtime", "first", "last"],
  header: {name: "Actor", gender: "Gender", films: "Films", tmdb: "Avg TMDB", rt: "Avg RT", runtime: "Avg runtime", first: "First", last: "Last"},
  format: {
    name: (n, i) => a.table[i].id ? html`<a href=${`./actor/${a.table[i].id}`}>${n}</a>` : n,
    tmdb: (v) => v?.toFixed(2) ?? "", rt: (v) => (v == null ? "" : `${v}%`),
    first: String, last: String
  },
  rows: 16, layout: "auto", select: false
}));
```
