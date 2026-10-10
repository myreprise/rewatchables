---
title: Film
---

```js
// One page per film, at /movie/<slug> (heat-1995): the site's version of the
// app's dossier overlay. Everything on it is precomputed by pipeline step 15
// into data/films/<slug>.json, including the related-film shelves, so the page
// only lays it out. The route parameter is still called `id`; it holds the slug.
import {badge, chipField, fmt, filmCard, filmHref, grid, heroPlate, personHref,
        readTrail, rings, statRail, statTile, stars, tape} from "../components/ui.js";

const film = FileAttachment(`../data/films/${observable.params.id}.json`).json();
```

```js
document.title = `${film.title} (${film.year}) | Rewatchables Explorer`;
const s = film.scores;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

const chips = [];
if (film.revisited) chips.push(badge(`Revisited ×${Math.max(film.episodes_featured - 1, 1)}`, "revisit"));
chips.push(badge(plural(film.episodes_featured, "episode"), "mint"));
if (film.first) {
  chips.push(badge(film.last && film.last !== film.first
    ? `${fmt.monYear(film.first)} → ${fmt.monYear(film.last)}`
    : fmt.monYear(film.first)));
}

// Opened from a list (the Explorer's filtered films, a person's episodes, a
// keyword's films), the page steps through that list as the app's dossier
// does. Reached any other way, it has a plain way back to all films.
const here = readTrail(film.id);
display(here
  ? html`<div class="rw-dt-nav">
      <a class="rw-back" href=${here.back}>← Back to ${here.label}</a>
      ${here.at > 0
        ? html`<a class="rw-back rw-step" href=${filmHref(here.ids[here.at - 1], "../")} title="Previous film">‹</a>`
        : html`<span class="rw-back rw-step is-off">‹</span>`}
      ${here.at < here.ids.length - 1
        ? html`<a class="rw-back rw-step" href=${filmHref(here.ids[here.at + 1], "../")} title="Next film">›</a>`
        : html`<span class="rw-back rw-step is-off">›</span>`}
      <span class="rw-dt-count">Film ${here.at + 1} of ${here.ids.length}</span>
    </div>`
  : html`<a class="rw-back" href="../films">← Movie Explorer</a>`);
display(html`<div class="rw-dt-hero">
  ${rings()}
  <div class="rw-dt-poster">${heroPlate(film)}</div>
  <div class="rw-dt-id">
    <h1>${film.title} <span>${film.year}</span></h1>
    <p class="rw-dt-cred">${film.directors.join(" · ") || "Director unknown"}<i>·</i>${film.runtime ? `${film.runtime} min` : "runtime unknown"}<i>·</i>${film.genres.join(" · ") || "Ungenred"}</p>
    <div class="chip-row">${chips}</div>
    ${statRail([
      statTile("TMDB", s.tmdb != null ? s.tmdb.toFixed(1) : null, "/10"),
      statTile("Rotten Tomatoes", s.rt != null ? s.rt.toFixed(0) : null, "%"),
      statTile("Ebert", stars(s.ebert)),
      statTile(`Box office (${s.cpi_year}$)`, s.box_office),
      statTile("Return", s.multiple != null ? s.multiple.toFixed(1) : null, "×"),
      statTile("Episodes", film.episodes_featured, "", true)
    ])}
  </div>
</div>`);
```

```js
display(tape(`On the show — ${plural(film.episodes.length, "episode")}`));
// Everyone in the room but the anchor has a page, the site's version of the
// app's Hosts & Guests lookup.
const seat = (p, chair) => {
  const cls = chair === "H" ? "rw-dt-person is-host" : "rw-dt-person";
  return p.id
    ? html`<a class=${cls} href=${personHref(p.id, "../")}><i>${chair}</i>${p.name}</a>`
    : html`<span class=${cls}><i>${chair}</i>${p.name}</span>`;
};
// html.fragment, not html: a template with two top-level nodes (the gap and
// the card) would otherwise come back wrapped in a <span>.
display(html`<div class="rw-dt-spine">${film.episodes.map((ep) => html.fragment`
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
          ${ep.verdict ? badge(ep.verdict, ep.verdict_tone) : ""}
        </span>
      </div>
      <div class="rw-dt-eproom"><span class="lbl">Room</span>
        ${ep.host ? seat(ep.host, "H") : ""}
        ${ep.guests.map((g) => seat(g, "G"))}
      </div>
      ${ep.note ? html`<div class="rw-dt-epnote"><span class="lbl">Sheet note</span>${ep.note}</div>` : ""}
    </div>
  </div>`)}</div>`);
```

```js
display(tape("The film"));

// Keywords ranked by reach, eight shown first, as in the app. A chip carries
// its reach and leads to that keyword's page; one that reaches no other film
// is drawn inert.
const KW_CAP = 8;

const left = html`<div>
  <div class="rw-dt-panel"><h4>Plot</h4>
    <p class="rw-dt-logline">${film.plot || "No summary on file."}</p>
  </div>
  ${film.synopsis ? html`<details class="rw-more">
    <summary>Full Wikipedia synopsis — ${film.synopsis_words?.toLocaleString()} words</summary>
    ${film.synopsis.split(/\n+/).map((para) => html`<p>${para}</p>`)}
  </details>` : ""}
  ${film.keywords.length ? html.fragment`
    <h4 class="rw-dt-loose">Keywords</h4>
    ${chipField(film.keywords.slice(0, KW_CAP), "../")}
    ${film.keywords.length > KW_CAP ? html`<details class="rw-more" style="margin-top:12px">
      <summary>All ${film.keywords.length} keywords</summary>
      ${chipField(film.keywords, "../")}
    </details>` : ""}` : ""}
</div>`;

const right = html`<div>
  ${film.cast.length ? html`<div class="rw-dt-panel"><h4>Cast — top billed</h4>
    <div class="rw-dt-cast">${film.cast.map((c) =>
      html`<span>${c.name}${c.films > 1 ? html`<b>${c.films}</b>` : ""}</span>`)}</div>
  </div>` : ""}
  ${film.by_director.length ? html.fragment`<p class="rw-shelf-h">Also on the show — ${film.director_primary}</p>
    ${grid(film.by_director.map((f) => filmCard(f, String(f.year), "../")), "rw-grid shelf")}` : ""}
  ${film.shared_cast.length ? html.fragment`<p class="rw-shelf-h">Shared cast</p>
    ${grid(film.shared_cast.map((f) => filmCard(f, String(f.year), "../")), "rw-grid shelf")}` : ""}
</div>`;

display(html`<div class="rw-split film">${left}${right}</div>`);
```

```js
const p = film.provenance;
display(html`<div class="rw-dt-prov">
  <span>Key confidence <span class="conf">${p.confidence}</span></span>
  ${p.enriched ? html`<span>Enriched <b>${p.enriched}</b></span>` : ""}
  ${film.tmdb_id ? html`<span><a href=${`https://www.themoviedb.org/movie/${film.tmdb_id}`} target="_blank">TMDB ${film.tmdb_id}</a></span>` : ""}
  ${p.wikipedia ? html`<span><a href=${p.wikipedia} target="_blank">Wikipedia</a></span>` : ""}
  ${p.wikidata ? html`<span><a href=${`https://www.wikidata.org/wiki/${p.wikidata}`} target="_blank">Wikidata ${p.wikidata}</a></span>` : ""}
</div>`);
```
