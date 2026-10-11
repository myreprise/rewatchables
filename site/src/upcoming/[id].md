---
title: Requested film
---

```js
// One page per requested film, at /upcoming/<slug>: the app's prospect
// overlay. Half a dossier by design: the film and why it is on the list, with
// no episodes, because there are none yet.
import {heroPlate, rings, statRail, statTile, whyPanel} from "../components/ui.js";

const r = FileAttachment(`../data/upcoming/${observable.params.id}.json`).json();
```

```js
document.title = `${r.title} | Rewatchables Explorer`;
const cred = [r.directors.join(" · "), r.genres.join(" · ")].filter(Boolean).join(" / ");

display(html`<a class="rw-back" href="../upcoming">← Back to Upcoming Films</a>`);
display(html`<div class="rw-dt-hero">
  ${rings()}
  <div class="rw-dt-poster">${heroPlate(r)}</div>
  <div class="rw-dt-id">
    <p class="rw-dt-loose">Upcoming · not yet an episode</p>
    <h1>${r.title} <span>${r.year_raw ?? ""}</span></h1>
    <div class="rw-dt-cred">${cred}</div>
    ${statRail([
      statTile("Year", r.year_raw),
      statTile("Runtime", r.runtime, " min"),
      statTile("TMDB", r.tmdb != null ? r.tmdb.toFixed(1) : null, "/10"),
      statTile("Status", "Requested", "", true)
    ])}
  </div>
</div>`);
if (!r.resolved) display(html`<div class="rw-up-unres">Unmatched — ${r.unresolved_note}</div>`);
```

```js
display(html`<div class="rw-dt-panel"><h4>Why it is on the list</h4>${whyPanel(r)}</div>`);
// Both a note and tags is rare -- the source columns are alternatives -- but
// when it happens the tags are additional, not a duplicate of the note.
if (r.tags.length && r.note) {
  display(html`<div class="rw-dt-panel"><h4>Pitched as</h4><div class="rw-up-tags">${r.tags.map((t) => html`<span class="rw-up-tag">${t}</span>`)}</div></div>`);
}
if (r.plot) display(html`<div class="rw-dt-panel"><h4>The film</h4><p class="rw-dt-logline">${r.plot}</p></div>`);
if (r.cast.length) {
  display(html`<div class="rw-dt-panel"><h4>Cast</h4><div class="rw-dt-cast">${r.cast.map((n) => html`<span>${n}</span>`)}</div></div>`);
}
display(html`<div class="rw-dt-prov">
  <span>Match <b>${r.method}</b></span>
  <span>${r.tmdb_id ? html`<a href=${`https://www.themoviedb.org/movie/${r.tmdb_id}`} target="_blank" rel="noopener">TMDB</a>` : html`<b>no TMDB match</b>`}</span>
</div>`);
```
