---
title: Keyword
---

```js
// The keyword page, for every keyword on two or more films:
// keyword?id=heist. The site's version of the app's keyword overlay
// (overlays/keyword.py, keyword_profile). Its films, partners and decades are
// queries on site.db; the arithmetic below is the overlay's, line for line.
import {asFilm, pageId, query, row} from "./components/db.js";
import {chipField, decadeBars, filmCard, grid, gridNote, rings, statTile, tape,
        trail} from "./components/ui.js";

const kw = await row("keyword", pageId());
const [films, partners, decadeCounts, catalogue, vocabulary] = kw
  ? await Promise.all([query("keyword_films", kw.word), query("keyword_partners", kw.word),
                       query("decade_counts"), query("catalogue"), query("keywords")])
  : [[], [], [], [], []];
```

```js
if (!kw) {
  display(html`<a class="rw-back" href="./keywords">← Keywords</a>`);
  display(html`<p class="rw-ov-note">No keyword at this address.</p>`);
}
```

```js
// views.region_of: the part after the last comma of a "city, region" keyword.
const regionOf = (word) => (word.includes(",") ? word.slice(word.lastIndexOf(",") + 1).trim() || null : null);
const n = films.length;
const total = catalogue[0]?.films ?? 0;
const thin = n < 3;
// Films by decade, the decades between the first and last filled in with zero.
const spread = films.reduce((m, f) => m.set(Math.floor(f.year / 10) * 10, (m.get(Math.floor(f.year / 10) * 10) ?? 0) + 1), new Map());
const peak = thin ? null : [...spread].reduce((a, b) => (b[1] > a[1] ? b : a))[0];
const decades = [];
if (!thin) {
  const lo = Math.min(...spread.keys()), hi = Math.max(...spread.keys());
  for (let d = lo; d <= hi; d += 10) decades.push({decade: d, n: spread.get(d) ?? 0});
}
const rated = films.filter((f) => f.tmdb != null);
const avg = rated.length ? rated.reduce((s, f) => s + f.tmdb, 0) / rated.length : null;
const region = kw ? regionOf(kw.word) : null;
const siblings = region ? vocabulary.filter((k) => regionOf(k.word) === region).map((k) => k.word) : [];
const regionFilms = siblings.length > 1 ? (await query("region_films", JSON.stringify(siblings)))[0].films : null;
```

```js
if (kw) {
  document.title = `${kw.word} | Rewatchables Explorer`;
  // One or two films have no decade shape and no meaningful average, so the
  // rail says how rare the keyword is instead of inventing precision.
  const rail = [statTile("Films", n), statTile("Of the catalogue", (100 * n / total).toFixed(1), "%")];
  if (thin) {
    rail.push(statTile("Rarity", n, ` of ${total}`, true));
  } else {
    rail.push(statTile("Peak decade", peak, "s"));
    rail.push(statTile("Avg TMDB", avg?.toFixed(1) ?? null, "/10"));
    if (avg != null) {
      const vs = avg - catalogue[0].avg_tmdb;
      rail.push(statTile("vs. catalogue", `${vs >= 0 ? "+" : ""}${vs.toFixed(1)}`, "", true));
    }
  }
  display(html`<a class="rw-back" href="./keywords">← Keywords</a>`);
  display(html`<div class="rw-kw-head">
    ${rings()}
    <p class="rw-kw-eyebrow">Keyword</p>
    <h1>${kw.word}</h1>
    <div class="rw-kw-rail">${rail}</div>
  </div>`);
  if (regionFilms != null) {
    const name = region.replace(/\b\w/g, (c) => c.toUpperCase());
    display(html`<div class="rw-kw-tail">Part of <b>${name}</b>: ${regionFilms} films across ${siblings.length} places.</div>`);
  }

  if (!thin) {
    const house = (decadeCounts.find((d) => d.decade === peak)?.films ?? 0) / total;
    display(tape("When these films were made"));
    display(decadeBars(decades));
    display(html`<p class="rw-kw-caption">The ${peak}s hold <b>${Math.round(100 * spread.get(peak) / n)}%</b> of these films, against <b>${Math.round(100 * house)}%</b> of the catalogue as a whole. Read the gap between those two numbers, not the shape on its own — the show covers some decades far more than others.</p>`);
  } else {
    display(html`<div class="rw-kw-tail">Only ${n} film${n !== 1 ? "s" : ""} carries this keyword, so there is no decade shape and no average worth printing. Below is the film, and the keywords it shares with the rest of the catalogue.</div>`);
  }

  if (partners.length) {
    display(tape(thin ? "Where to go from here" : "Travels with"));
    display(chipField(partners.map((p) => ({...p, id: p.slug}))));
  }

  display(tape(`The ${n} film${n !== 1 ? "s" : ""}`));
  display(gridNote("Ordered by year · oldest first", "Every poster opens that film's dossier"));
  display(trail(
    grid(films.map((f) => filmCard(asFilm(f), `${f.year}${f.tmdb != null ? ` ${f.tmdb.toFixed(1)}` : ""}`))),
    `“${kw.word}”`, films.map((f) => f.slug)));
}
```
