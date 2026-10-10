---
title: Keyword
---

```js
// One page per keyword on two or more films, at /keyword/<slug>: the site's
// version of the app's keyword overlay. Step 15 writes data/keywords/<slug>.json
// from the overlay's own keyword_profile(), so this page only lays it out.
import {chipField, decadeBars, filmCard, grid, gridNote, rings, statTile, tape,
        trail} from "../components/ui.js";

const kw = FileAttachment(`../data/keywords/${observable.params.id}.json`).json();
```

```js
document.title = `${kw.word} | Rewatchables Explorer`;
const n = kw.films.length;

// One or two films have no decade shape and no meaningful average, so the
// rail says how rare the keyword is instead of inventing precision.
const rail = [statTile("Films", n), statTile("Of the catalogue", kw.share.toFixed(1), "%")];
if (kw.thin) {
  rail.push(statTile("Rarity", n, ` of ${kw.catalogue}`, true));
} else {
  rail.push(statTile("Peak decade", kw.peak, "s"));
  rail.push(statTile("Avg TMDB", kw.avg_tmdb?.toFixed(1) ?? null, "/10"));
  if (kw.vs_catalogue != null) {
    rail.push(statTile("vs. catalogue", `${kw.vs_catalogue >= 0 ? "+" : ""}${kw.vs_catalogue.toFixed(1)}`, "", true));
  }
}

display(html`<a class="rw-back" href="../keywords">← Keywords</a>`);
display(html`<div class="rw-kw-head">
  ${rings()}
  <p class="rw-kw-eyebrow">Keyword</p>
  <h1>${kw.word}</h1>
  <div class="rw-kw-rail">${rail}</div>
</div>`);
if (kw.region) {
  const region = kw.region.replace(/\b\w/g, (c) => c.toUpperCase());
  display(html`<div class="rw-kw-tail">Part of <b>${region}</b>: ${kw.region_films} films across ${kw.region_places} places.</div>`);
}
```

```js
if (!kw.thin) {
  display(tape("When these films were made"));
  display(decadeBars(kw.decades));
  display(html`<p class="rw-kw-caption">The ${kw.peak}s hold <b>${kw.peak_share}%</b> of these films, against <b>${kw.catalogue_peak_share}%</b> of the catalogue as a whole. Read the gap between those two numbers, not the shape on its own — the show covers some decades far more than others.</p>`);
} else {
  display(html`<div class="rw-kw-tail">Only ${n} film${n !== 1 ? "s" : ""} carries this keyword, so there is no decade shape and no average worth printing. Below is the film, and the keywords it shares with the rest of the catalogue.</div>`);
}
```

```js
if (kw.partners.length) {
  display(tape(kw.thin ? "Where to go from here" : "Travels with"));
  display(chipField(kw.partners, "../"));
}
```

```js
display(tape(`The ${n} film${n !== 1 ? "s" : ""}`));
display(gridNote("Ordered by year · oldest first", "Every poster opens that film's dossier"));
display(trail(
  grid(kw.films.map((f) => filmCard(f, `${f.year}${f.tmdb != null ? ` ${f.tmdb.toFixed(1)}` : ""}`, "../"))),
  `“${kw.word}”`, kw.films.map((f) => f.id)));
```
