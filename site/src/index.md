---
title: Overview
---

```js
// The front page. Its numbers are the Streamlit overview's, computed by the
// same Python functions in pipeline step 15; this page only lays them out.
import {filmHref, personHref, fmt, filmCard, grid, gridNote, masthead, note, posterUrl, rings,
        statRail, statTile, tape} from "./components/ui.js";
import {plot} from "./components/plot.js";

import {films as allFilms, section} from "./components/db.js";

const ov = await section("overview");
const films = await allFilms();
const episodesPerYear = ov.figures["episodes-per-year"];
```

```js
display(masthead(
  "Every film they’ve rewatched",
  `${ov.tiles.episodes.toLocaleString()} film episodes of The Rewatchables, joined to TMDB metadata, Rotten Tomatoes scores and Ebert stars. Where the show is now, who is in the room, and every film they have covered.`
));
const t = ov.tiles;
display(statRail([
  statTile("Episodes", t.episodes.toLocaleString()),
  statTile("Films", t.films.toLocaleString()),
  statTile("Last 12 months", t.last_12_months),
  statTile("Median film age", t.median_film_age, " yrs"),
  statTile("From the 1990s", t.share_90s, "%"),
  statTile("Between episodes", t.median_gap, " days")
]));
```

```js
display(tape("Latest episodes"));
display(gridNote(`as of ${fmt.longDate(ov.as_of)}`, "click a poster for its episodes"));
display(grid(ov.latest.map((f) =>
  filmCard(f, `Ep ${f.episode} · ${fmt.monDay(f.aired)}`, "./"))));
```

```js
display(tape("The regulars"));
const nEps = ov.tiles.episodes;
display(html`<div class="rw-reg-row">${ov.regulars.map((r) => html`
  <div class="rw-reg">
    <span class="d">${r.name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}</span>
    <div class="b">
      <span class="n">${r.id ? html`<a href=${personHref(r.id)}>${r.name}</a>` : r.name}</span>
      <span class="m"><b>${r.episodes}</b> of ${nEps}${r.hosted ? ` · hosted ${r.hosted}` : ""}</span>
      <div class="bar"><i style=${`width:${(100 * r.episodes / nEps).toFixed(0)}%`}></i></div>
    </div>
  </div>`)}</div>`);
display(note(html`<b>${ov.people_besides_anchor}</b> people besides ${ov.anchor} have been in the room. He is on ${ov.anchor_episodes} of ${nEps} episodes, so he is left out of the ranking. The bar is the share of episodes each was in.`));
```

```js
display(tape("The ones they came back to"));
display(note(html`<b>${ov.came_back_to.length}</b> films have more than one episode. The source sheet marks <b>${ov.flagged_revisits}</b> films as revisits by hand; the episode count is derived from the feed, and the two are deliberately not reconciled — a second episode is not always a revisit.`));
display(grid(ov.came_back_to.map((f) =>
  filmCard(f, `${f.episodes}× · ${fmt.year(f.last)}`, "./"))));
```

```js
display(tape("Episodes per year"));
// The figure is the app's own: built by overview.episodes_per_year in Python
// and exported as Plotly JSON, so only the width is decided here.
const chart = resize((width) => plot(episodesPerYear, width));
const r = ov.reading;
display(html`<div class="rw-split">
  <div>${chart}</div>
  <div class="rw-dt-panel" style="margin-top:8px">
    <p class="rw-dt-loose">Reading the chart</p>
    <ul class="rw-ov-read">
      <li><b>${fmt.monYear(r.first_air)}</b>first film episode</li>
      <li><b>${r.first_full_year ?? "—"}</b>first year at fifty or more</li>
      <li><b>${r.median_gap} days</b>median gap between episodes</li>
      <li><b>${r.so_far}</b>so far in ${r.so_far_year}</li>
    </ul>
  </div>
</div>`);
```

```js
// One door per section, in the rail's order and numbering, each with the one
// number that says what is behind it: overview.doors() in the app.
display(tape("Go deeper"));
display(html`<div class="rw-grid rw-doors">${ov.doors.map((d) => html`
  <a class="rw-door-link" href=${`./${d.path}`}><div class="rw-door"><span class="rw-doormark"></span>
    <span class="k">${d.group} · ${String(d.number_in_rail).padStart(2, "0")}</span>
    <span class="v">${d.value}${d.unit ? html`<small>${d.unit}</small>` : ""}</span>
    <span class="t">${d.label}</span>
    <p>${d.blurb}</p>
  </div></a>`)}</div>`);
```

```js
display(tape("Random spotlight"));
```

```js
// Rerolled by the button below: each click is a new value of `reroll`, which
// reruns this cell.
reroll;
const spot = films[Math.floor(Math.random() * films.length)];
const art = posterUrl(spot.poster, "w342");
const meta = [spot.directors.join(" · "), spot.genres.join(" · "),
              spot.runtime ? `${spot.runtime} min` : ""].filter(Boolean);
display(html`<div class="rw-dt-panel"><div class="rw-spot">
  ${art ? html`<img src=${art} alt="">`
        : html`<div class="poster-plate" style="height:225px;width:150px">${rings("")}<b>${spot.title}</b></div>`}
  <div>
    <p class="h">${spot.title}<small>${spot.year}</small></p>
    <span class="m">${meta.join(" · ")}</span>
    <span class="m">${spot.tmdb != null ? html`TMDB <b>${spot.tmdb.toFixed(1)}</b>/10 · ` : ""}featured <b>${spot.episodes}×</b></span>
    <p>${spot.blurb || "No plot summary on file."}</p>
    <p><a class="rw-back" href=${filmHref(spot.id)}>Open the film →</a></p>
  </div>
</div></div>`);
```

```js
const reroll = view(Inputs.button("🎲 Surprise me"));
```
