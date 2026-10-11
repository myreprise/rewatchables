---
title: Box Office
---

```js
// The app's Box Office section. Every number and chart comes from
// sections/boxoffice.py's summary(), figures(), returns() and money_table(),
// run by pipeline step 15; money is printed by views.money, in Python.
import {filmLink, masthead, note, statRail, statTile, table, tape} from "./components/ui.js";
import {plot} from "./components/plot.js";

import {query, section} from "./components/db.js";

// The data table is the money_table query over the films table; the rest is
// the section's own numbers and charts.
const b = {...await section("boxoffice"),
           table: (await query("money_table")).map((f) => ({
             id: f.slug, title: f.title, year: f.year,
             budget: f.budget_real, budget_txt: f.budget, gross: f.revenue_real, gross_txt: f.box_office,
             return: f.multiple != null ? Math.round(f.multiple * 10) / 10 : null,
             tmdb: f.tmdb != null ? Math.round(f.tmdb * 10) / 10 : null, episodes: f.episodes}))};
```

```js
const s = b.summary;
const y = b.cpi_year;
const chart = (name) => resize((width) => plot(b.figures[name], width));

display(masthead("Box Office", `What these films cost, what they took, and what came back — every figure in ${y} dollars.`));
display(statRail([
  statTile("Films with a gross", `${s.with_gross} / ${s.films}`),
  statTile(`Median gross (${y}$)`, s.median_gross),
  statTile(`Median budget (${y}$)`, s.median_budget),
  statTile("Median return", s.median_return.toFixed(1), "×"),
  statTile("Under break-even", `${s.under_break_even} / ${s.with_return}`)
]));
display(note(`Gross and budget come from TMDB and are worldwide theatrical, converted to ${y} dollars with US CPI-U. Return is gross ÷ budget: it is not profit, since neither figure includes marketing or the exhibitor's share, so the break-even line is drawn at the industry rule of thumb of ${b.break_even}×, not 1×. ${s.no_gross} films have no published gross and ${s.no_budget} no budget; they are absent from these charts rather than counted as zero.`));
```

```js
display(tape(`Gross by release decade (${y} dollars)`));
display(chart("by_decade"));
if (s.thin_decades.length) {
  display(note(`Log scale. Decades carrying fewer than ten films — ${s.thin_decades.map((d) => `${d.decade} (${d.films})`).join(", ")} — are too thin to read as a trend.`));
}
```

```js
display(tape("What it cost against what it took"));
display(chart("cost_vs_gross"));
display(note(`Both axes log. ${s.scatter_films - s.scatter_short} of ${s.scatter_films} films cleared the line; the ${s.scatter_short} below it are the ones the show likes anyway.`));
```

```js
display(tape("The best returns, and the worst"));
const columns = [
  ["Film", (x) => filmLink(x, "./")],
  ["Year", (x) => x.year, true],
  ["Budget", (x) => x.budget, true],
  ["Gross", (x) => x.gross, true],
  ["Return", (x) => x.return, true]
];
display(html`<div class="rw-cols c2">
  <div><p class="rw-sub">Most returned per dollar spent</p>${table(b.best, columns)}</div>
  <div><p class="rw-sub">Lost the most, and got an episode anyway</p>${table(b.worst, columns)}</div>
</div>`);
if (s.provisional.length) {
  display(note(`Excludes ${s.provisional.map((p) => `${p.title} (${p.year})`).join(", ")} — released ${b.provisional_from} or later, so the gross is still moving and the budget is often a placeholder. TMDB has one of them at a $750K budget against a $506M gross.`));
}
```

```js
display(tape("Does the money track the rating?"));
display(chart("money_vs_rating"));
display(note(`Spearman ρ = ${s.rho.toFixed(2)} over ${s.merit_films} films — a weak positive relationship. Money and merit are close to independent here, which is the whole premise of a show that will spend an hour on a film that lost its studio money.`));
```

```js
display(tape(`Median gross by genre (${y} dollars)`));
display(chart("by_genre"));
display(note("Genres carrying fewer than five films are omitted."));
```

```js
// The app's data table: every film with a gross, highest first. It sorts on
// the raw figures and prints them as the app does.
display(tape("Data table"));
display(Inputs.table(b.table, {
  columns: ["title", "year", "budget", "gross", "return", "tmdb", "episodes"],
  header: {title: "Film", year: "Year", budget: `Budget (${y}$)`, gross: `Gross (${y}$)`,
           return: "Return", tmdb: "TMDB", episodes: "Episodes"},
  format: {
    title: (t, i) => filmLink(b.table[i], "./"),
    year: String,
    budget: (v, i) => b.table[i].budget_txt ?? "—",
    gross: (v, i) => b.table[i].gross_txt ?? "—",
    return: (v) => (v == null ? "—" : `${v.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}×`),
    tmdb: (v) => v?.toFixed(1) ?? ""
  },
  rows: 16, layout: "auto", select: false
}));
```
