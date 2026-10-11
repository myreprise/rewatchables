---
title: Requested film
---

```js
// The page for a film on the Upcoming list: request?id=alien-3-1992. The
// app's prospect overlay: the film and why it is on the list, with no
// episodes, because there are none yet.
import {list, pageId, row} from "./components/db.js";
import {heroPlate, rings, statRail, statTile, whyPanel} from "./components/ui.js";

const r = await row("request", pageId());
```

```js
display(html`<a class="rw-back" href="./upcoming">← Back to Upcoming Films</a>`);
if (!r) {
  // The list is rebuilt every run, so a shared link can outlive its request:
  // most likely the film became an episode.
  display(html`<p class="rw-ov-note">That film is no longer on the upcoming list. It may have become an episode.</p>`);
} else {
  document.title = `${r.title} | Rewatchables Explorer`;
  const tags = list(r.tags);
  const why = {note: r.note, tags, by: r.by_label ? {label: r.by_label, href: r.by_href} : null};
  const cred = [JSON.parse(r.directors).join(" · "), JSON.parse(r.genres).join(" · ")].filter(Boolean).join(" / ");
  const cast = JSON.parse(r.cast);

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
  display(html`<div class="rw-dt-panel"><h4>Why it is on the list</h4>${whyPanel(why)}</div>`);
  // Both a note and tags is rare -- the source columns are alternatives -- but
  // when it happens the tags are additional, not a duplicate of the note.
  if (tags.length && r.note) {
    display(html`<div class="rw-dt-panel"><h4>Pitched as</h4><div class="rw-up-tags">${tags.map((t) => html`<span class="rw-up-tag">${t}</span>`)}</div></div>`);
  }
  if (r.plot) display(html`<div class="rw-dt-panel"><h4>The film</h4><p class="rw-dt-logline">${r.plot}</p></div>`);
  if (cast.length) {
    display(html`<div class="rw-dt-panel"><h4>Cast</h4><div class="rw-dt-cast">${cast.map((n) => html`<span>${n}</span>`)}</div></div>`);
  }
  display(html`<div class="rw-dt-prov">
    <span>Match <b>${r.method}</b></span>
    <span>${r.tmdb_id ? html`<a href=${`https://www.themoviedb.org/movie/${r.tmdb_id}`} target="_blank" rel="noopener">TMDB</a>` : html`<b>no TMDB match</b>`}</span>
  </div>`);
}
```
