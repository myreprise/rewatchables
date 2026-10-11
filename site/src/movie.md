---
title: Film
---

```js
// The film page, for every film: movie?id=heat-1995. The site's version of
// the app's dossier overlay. It queries site.db for the film in the address;
// the related-film shelves and the episode labels were worked out by step 15,
// so the page only lays them out.
import {asFilm, pageId, query, row, synopsis} from "./components/db.js";
import {badge, chipField, fmt, filmCard, filmHref, grid, heroPlate, pageHref, personHref,
        readTrail, rings, statRail, statTile, stars, tape} from "./components/ui.js";

const id = pageId();
const film = asFilm(await row("film", id));
// The year the box office is adjusted to (views.CPI_BASE_YEAR), as stored for
// the Box Office section.
const cpiYear = JSON.parse((await query("section_data", "boxoffice")).find((d) => d.key === "cpi_year")?.value ?? "null");
const [episodes, room, directors, genres, keywords, cast, byDirector, sharedCast] = film
  ? await Promise.all([
      query("film_episodes", id), query("film_room", id), query("film_directors", id),
      query("film_genres", id), query("film_keywords", id), query("film_cast", id),
      query("film_shelf", id, "director"), query("film_shelf", id, "cast")])
  : [[], [], [], [], [], [], [], []];
```

```js
if (!film) {
  display(html`<a class="rw-back" href="./films">← Movie Explorer</a>`);
  display(html`<p class="rw-ov-note">No film at this address.</p>`);
}
```

```js
if (film) {
  document.title = `${film.title} (${film.year}) | Rewatchables Explorer`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // The RT score and Ebert stars of the film's earliest airing that has one,
  // as the app shows them.
  const byDate = [...episodes].sort((a, b) => a.date.localeCompare(b.date) || a.number - b.number);
  const firstRt = byDate.find((e) => e.rt != null)?.rt;
  const firstEbert = byDate.find((e) => e.ebert != null)?.ebert ?? null;

  const chips = [];
  if (film.revisited) chips.push(badge(`Revisited ×${Math.max(film.episodes - 1, 1)}`, "revisit"));
  chips.push(badge(plural(film.episodes, "episode"), "mint"));
  if (film.first_episode) {
    chips.push(badge(film.last_episode && film.last_episode !== film.first_episode
      ? `${fmt.monYear(film.first_episode)} → ${fmt.monYear(film.last_episode)}`
      : fmt.monYear(film.first_episode)));
  }

  // Opened from a list (the Explorer's filtered films, a person's episodes, a
  // keyword's films), the page steps through that list as the app's dossier
  // does. Reached any other way, it has a plain way back to all films.
  const here = readTrail(film.id);
  display(here
    ? html`<div class="rw-dt-nav">
        <a class="rw-back" href=${here.back}>← Back to ${here.label}</a>
        ${here.at > 0
          ? html`<a class="rw-back rw-step" href=${filmHref(here.ids[here.at - 1])} title="Previous film">‹</a>`
          : html`<span class="rw-back rw-step is-off">‹</span>`}
        ${here.at < here.ids.length - 1
          ? html`<a class="rw-back rw-step" href=${filmHref(here.ids[here.at + 1])} title="Next film">›</a>`
          : html`<span class="rw-back rw-step is-off">›</span>`}
        <span class="rw-dt-count">Film ${here.at + 1} of ${here.ids.length}</span>
      </div>`
    : html`<a class="rw-back" href="./films">← Movie Explorer</a>`);
  display(html`<div class="rw-dt-hero">
    ${rings()}
    <div class="rw-dt-poster">${heroPlate(film)}</div>
    <div class="rw-dt-id">
      <h1>${film.title} <span>${film.year}</span></h1>
      <p class="rw-dt-cred">${directors.length
        ? directors.map((d, i) => html.fragment`${i ? " · " : ""}${d.director_slug ? html`<a href=${pageHref("director", d.director_slug)}>${d.name}</a>` : d.name}`)
        : "Director unknown"}<i>·</i>${film.runtime ? `${film.runtime} min` : "runtime unknown"}<i>·</i>${genres.map((g) => g.genre).join(" · ") || "Ungenred"}</p>
      <div class="chip-row">${chips}</div>
      ${statRail([
        statTile("TMDB", film.tmdb != null ? film.tmdb.toFixed(1) : null, "/10"),
        statTile("Rotten Tomatoes", firstRt != null ? (firstRt * 100).toFixed(0) : null, "%"),
        statTile("Ebert", stars(firstEbert)),
        statTile(`Box office (${cpiYear}$)`, film.box_office),
        statTile("Return", film.multiple != null ? film.multiple.toFixed(1) : null, "×"),
        statTile("Episodes", film.episodes, "", true)
      ])}
    </div>
  </div>`);
}
```

```js
if (film) {
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  display(tape(`On the show — ${plural(episodes.length, "episode")}`));
  // Everyone in the room but the anchor has a page, the site's version of the
  // app's Hosts & Guests lookup.
  const seat = (p) => {
    const host = p.chair === "host";
    const cls = host ? "rw-dt-person is-host" : "rw-dt-person";
    const mark = host ? "H" : "G";
    return p.person_slug
      ? html`<a class=${cls} href=${personHref(p.person_slug)}><i>${mark}</i>${p.person}</a>`
      : html`<span class=${cls}><i>${mark}</i>${p.person}</span>`;
  };
  const tone = (v) => (v.toLowerCase().startsWith("cruise") ? "cruise" : "hanks");
  // html.fragment, not html: a template with two top-level nodes (the gap and
  // the card) would otherwise come back wrapped in a <span>.
  display(html`<div class="rw-dt-spine">${episodes.map((ep) => html.fragment`
    ${ep.gap_before ? html`<div class="rw-dt-gap">${ep.gap_before}</div>` : ""}
    <div class=${ep.is_revisit ? "rw-dt-ep is-revisit" : "rw-dt-ep"}>
      <div class="rw-dt-epcard">
        <div class="rw-dt-ephead">
          <span class="rw-dt-epno"><span>EP</span> ${String(ep.number).padStart(3, "0")}</span>
          <span class="rw-dt-epdate">${fmt.dayMonYear(ep.date)}</span>
          <span class="rw-dt-epflags">
            ${ep.is_revisit
              ? badge(`Revisit ${ep.revisit_sequence} · ${ep.revisit_kind}`, "revisit")
              : badge("First watch", "mint")}
            ${ep.verdict ? badge(ep.verdict, tone(ep.verdict)) : ""}
          </span>
        </div>
        <div class="rw-dt-eproom"><span class="lbl">Room</span>
          ${room.filter((r) => r.episode === ep.id).map(seat)}
        </div>
        ${ep.note ? html`<div class="rw-dt-epnote"><span class="lbl">Sheet note</span>${ep.note}</div>` : ""}
      </div>
    </div>`)}</div>`);
}
```

```js
if (film) {
  display(tape("The film"));

  // Keywords ranked by reach, eight shown first, as in the app. A chip carries
  // its reach and leads to that keyword's page; one that reaches no other film
  // is drawn inert. The full synopsis is fetched only when it is opened.
  const KW_CAP = 8;
  const chips = keywords.map((k) => ({...k, id: k.slug}));
  const more = html`<details class="rw-more">
    <summary>Full Wikipedia synopsis — ${film.synopsis_words?.toLocaleString()} words</summary>
    <div class="rw-synopsis"></div>
  </details>`;
  more.addEventListener("toggle", async () => {
    const box = more.querySelector(".rw-synopsis");
    if (!more.open || box.childElementCount) return;
    const text = await synopsis(film.slug);
    box.replaceChildren(...(text ?? "").split(/\n+/).map((para) => html`<p>${para}</p>`));
  });

  const left = html`<div>
    <div class="rw-dt-panel"><h4>Plot</h4>
      <p class="rw-dt-logline">${film.plot || "No summary on file."}</p>
    </div>
    ${film.synopsis_words ? more : ""}
    ${chips.length ? html.fragment`
      <h4 class="rw-dt-loose">Keywords</h4>
      ${chipField(chips.slice(0, KW_CAP))}
      ${chips.length > KW_CAP ? html`<details class="rw-more" style="margin-top:12px">
        <summary>All ${chips.length} keywords</summary>
        ${chipField(chips)}
      </details>` : ""}` : ""}
  </div>`;

  const right = html`<div>
    ${cast.length ? html`<div class="rw-dt-panel"><h4>Cast — top billed</h4>
      <div class="rw-dt-cast">${cast.map((c) => {
        // An actor on three or more covered films has a spotlight.
        const inner = html.fragment`${c.name}${c.films > 1 ? html`<b>${c.films}</b>` : ""}`;
        return c.actor_slug ? html`<a href=${pageHref("actor", c.actor_slug)}>${inner}</a>` : html`<span>${inner}</span>`;
      })}</div>
    </div>` : ""}
    ${byDirector.length ? html.fragment`<p class="rw-shelf-h">Also on the show — ${film.director_primary}</p>
      ${grid(byDirector.map((f) => filmCard(asFilm(f), String(f.year))), "rw-grid shelf")}` : ""}
    ${sharedCast.length ? html.fragment`<p class="rw-shelf-h">Shared cast</p>
      ${grid(sharedCast.map((f) => filmCard(asFilm(f), String(f.year))), "rw-grid shelf")}` : ""}
  </div>`;

  display(html`<div class="rw-split film">${left}${right}</div>`);

  display(html`<div class="rw-dt-prov">
    <span>Key confidence <span class="conf">${film.confidence}</span></span>
    ${film.enriched ? html`<span>Enriched <b>${film.enriched}</b></span>` : ""}
    ${film.tmdb_id ? html`<span><a href=${`https://www.themoviedb.org/movie/${film.tmdb_id}`} target="_blank">TMDB ${film.tmdb_id}</a></span>` : ""}
    ${film.wikipedia ? html`<span><a href=${film.wikipedia} target="_blank">Wikipedia</a></span>` : ""}
    ${film.wikidata ? html`<span><a href=${`https://www.wikidata.org/wiki/${film.wikidata}`} target="_blank">Wikidata ${film.wikidata}</a></span>` : ""}
  </div>`);
}
```
