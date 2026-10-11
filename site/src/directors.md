---
title: Directors
---

```js
// The app's Directors section: director_counts(), figures() and
// ranked_directors(), run by pipeline step 15 into site.db. Every director
// in the table has a spotlight at director?id=<slug>.
import {masthead, note, pageHref, statRail, statTile, tape} from "./components/ui.js";
import {plot} from "./components/plot.js";
import {spotlightPicker} from "./components/spotlight.js";

import {query, roundEven, section} from "./components/db.js";

// The section's numbers and charts; the table and the picker from the
// directors table.
const d = {...await section("directors"),
           table: (await query("directors_table")).map((r) => ({
             name: r.name, id: r.slug, films: r.films, tmdb: r.avg_tmdb,
             rt: roundEven(r.avg_rt != null ? r.avg_rt * 100 : null),
             runtime: roundEven(r.avg_runtime),
             first: r.first_year, last: r.last_year})),
           spotlight: await query("spotlight_picker", "director")};
```

```js
const t = d.tiles;
const chart = (name) => resize((width) => plot(d.figures[name], width));

display(masthead("Directors", "Who gets called back to the chair, and what their covered work looks like."));
// Numbers only: the leaderboard below already names who leads.
display(statRail([
  statTile("Directors", t.directors.toLocaleString()),
  statTile("Just one film", t.one.toLocaleString()),
  statTile("Two or more", t.two_plus.toLocaleString()),
  statTile("Four or more", t.four_plus.toLocaleString()),
  statTile("Films covered", t.films.toLocaleString())
]));
```

```js
display(tape("Most-featured directors"));
display(chart("leaderboard"));
display(html`<p class="ch-note">${t.two_plus} directors have more than one film covered, out of ${t.directors.toLocaleString()}. The long tail is most of the catalogue — the show ranges wider than it repeats.</p>`);
```

```js
display(tape("Director spotlight"));
display(note("The twenty most-featured. Every director in the table below has a spotlight too: their covered films, the shape of the work, and the actors they bring back."));
display(spotlightPicker(d.spotlight, "director"));
```

```js
display(tape("Volume against reception"));
display(chart("scatter"));
display(html`<p class="ch-note">Directors with two or more covered films; bubble size is average runtime. Only those with four or more are named — the rest are on hover. Being covered often and being rated well are weakly related for directors — <b>r = ${d.r.toFixed(2)}</b> across these ${d.scatter_people} — so the show does lean slightly toward the better-reviewed, but it explains little of the spread.</p>`);
```

```js
display(tape("Every director, ranked"));
display(Inputs.table(d.table, {
  columns: ["name", "films", "tmdb", "rt", "runtime", "first", "last"],
  header: {name: "Director", films: "Films", tmdb: "Avg TMDB", rt: "Avg RT", runtime: "Avg runtime", first: "First", last: "Last"},
  format: {
    name: (n, i) => d.table[i].id ? html`<a href=${pageHref("director", d.table[i].id)}>${n}</a>` : n,
    tmdb: (v) => v?.toFixed(2) ?? "", rt: (v) => (v == null ? "" : `${v}%`),
    first: String, last: String
  },
  rows: 16, layout: "auto", select: false
}));
```
