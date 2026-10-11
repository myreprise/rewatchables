---
title: Film
---

```js
// Phase 0 of the SQLite plan: one page for every film, at /movie?id=heat-1995.
// It reads site.db (built from site.sql by the data loader) and queries it
// for the film in the address. Timings are kept on window.__spike for the
// phase 0 measurements.
import {badge, fmt, heroPlate, rings, statRail, statTile, stars, tape} from "./components/ui.js";

const t0 = performance.now();
const db = await FileAttachment("data/site.db").sqlite();
const opened = performance.now();
const id = new URLSearchParams(location.search).get("id");
```

```js
const q0 = performance.now();
const film = await db.queryRow("SELECT * FROM films WHERE slug = ?", [id]);
const directors = (await db.query("SELECT name FROM film_directors WHERE slug = ? ORDER BY ord", [id])).map((d) => d.name);
const genres = (await db.query("SELECT genre FROM film_genres WHERE slug = ? ORDER BY ord", [id])).map((g) => g.genre);
const episodes = await db.query(`
  SELECT e.*, group_concat(CASE WHEN r.chair = 'host' THEN 'H:' ELSE 'G:' END || r.person, '|') AS room
  FROM episodes e LEFT JOIN episode_room r ON r.episode = e.id
  WHERE e.slug = ? GROUP BY e.id ORDER BY e.number`, [id]);
const cast = await db.query("SELECT name FROM film_cast WHERE slug = ? ORDER BY billing LIMIT 10", [id]);
const queried = performance.now();
window.__spike = {rendered_at: performance.now(), open_ms: opened - t0, query_ms: queried - q0, episodes: episodes.length};
```

```js
if (!film) {
  display(html`<p class="rw-ov-note">No film at this address.</p>`);
} else {
  document.title = `${film.title} (${film.year}) | Rewatchables Explorer`;
  display(html`<div class="rw-dt-hero">
    ${rings()}
    <div class="rw-dt-poster">${heroPlate({...film, poster: film.poster?.split("/").pop()})}</div>
    <div class="rw-dt-id">
      <h1>${film.title} <span>${film.year}</span></h1>
      <p class="rw-dt-cred">${directors.join(" · ") || "Director unknown"}<i>·</i>${film.runtime ? `${film.runtime} min` : "runtime unknown"}<i>·</i>${genres.join(" · ")}</p>
      ${statRail([
        statTile("TMDB", film.tmdb != null ? film.tmdb.toFixed(1) : null, "/10"),
        statTile("Rotten Tomatoes", film.rt != null ? film.rt.toFixed(0) : null, "%"),
        statTile("Ebert", stars(film.ebert)),
        statTile("Episodes", film.episodes, "", true)
      ])}
    </div>
  </div>`);
  display(tape(`On the show — ${episodes.length} episode${episodes.length === 1 ? "" : "s"}`));
  display(html`<div class="rw-dt-spine">${episodes.map((ep) => html`<div class="rw-dt-ep"><div class="rw-dt-epcard">
    <div class="rw-dt-ephead">
      <span class="rw-dt-epno"><span>EP</span> ${String(ep.number).padStart(3, "0")}</span>
      <span class="rw-dt-epdate">${fmt.dayMonYear(ep.date)}</span>
      <span class="rw-dt-epflags">${ep.is_revisit ? badge("Revisit", "revisit") : badge("First watch", "mint")}${ep.verdict ? badge(ep.verdict) : ""}</span>
    </div>
    <div class="rw-dt-eproom"><span class="lbl">Room</span>${(ep.room ?? "").split("|").filter(Boolean).map((p) =>
      html`<span class=${p.startsWith("H:") ? "rw-dt-person is-host" : "rw-dt-person"}><i>${p[0]}</i>${p.slice(2)}</span>`)}</div>
  </div></div>`)}</div>`);
  display(tape("Cast — top billed"));
  display(html`<div class="rw-dt-cast">${cast.map((c) => html`<span>${c.name}</span>`)}</div>`);
  display(html`<p class="rw-ov-note">Spike: database opened in ${window.__spike.open_ms.toFixed(0)} ms, queried in ${window.__spike.query_ms.toFixed(0)} ms.</p>`);
}
```
