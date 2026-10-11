// The Directors and Actors sections' spotlight: one panel for both, as
// panels.person_spotlight is in the app. Everything comes from site.db:
//
//   * the tiles from the directors / actors tables (analysis.PERSON_AGG,
//     computed in Python), plus the episode count summed over the films;
//   * the films from the spotlight_films query;
//   * the collaborators from the collaborators table (computed in Python);
//   * the genre-mix and decade charts, drawn here from those films. The app
//     builds the same two charts in panels.spotlight_figures; storing a pair
//     for each of 627 people is what made the old export so large, so they
//     are drawn in the browser instead, in the same colours.

import {html} from "npm:htl";
import {query, row} from "./db.js";
import {filmCard, grid, pageHref, rankedList, statRail, statTile, trail} from "./ui.js";
import {plot} from "./plot.js";

// What differs between the two: the collaborator panel's wording, and where
// a collaborator's own spotlight lives.
const KINDS = {
  director: {
    collab: "Actors they bring back",
    empty: (name) => `No actor is credited on more than one ${name} film here.`,
    note: "Credited on two or more of their covered films.",
    other: "actor"
  },
  actor: {
    collab: "Directors they return to",
    empty: (name) => `${name} has one film with each of these directors — no repeat pairing in the catalogue.`,
    note: "Directors of two or more of their covered films.",
    other: "director"
  }
};

// The app's palette (app/theme.py): the series hues in order, then "Other".
const SERIES = ["#17A87C", "#C98500", "#4A8FE0", "#E2624F", "#9085E9", "#D55181"];
const OTHER = "#6B736E";
const INK = "#0B0D0C", INK_2 = "#101211", TAPE = "#F2EFE6", LINE = "#262B28", MINT_DEEP = "#17A87C";

// {name, slug, kind, films: [...], stats: {...}, collaborators: [...]}, or
// null for an address with no spotlight.
export async function loadSpotlight(kind, slug) {
  const person = await row("spotlight", kind, slug);
  if (!person) return null;
  const [films, collaborators] = await Promise.all([
    query("spotlight_films", kind, person.name),
    query("collaborators", kind, person.name)
  ]);
  return {...person, kind, films: films.map((f) => ({...f, id: f.slug})), stats: person, collaborators};
}

// analysis.person_stats: first and latest are separate tiles, and a missing
// average reads as a dash.
export function spotlightTiles(s) {
  const t = s.stats;
  const episodes = s.films.reduce((n, f) => n + (f.episodes ?? 0), 0);
  return statRail([
    statTile("Films covered", s.films.length),
    statTile("Episodes", episodes),
    statTile("First film", t.first_year ?? "—"),
    statTile("Latest film", t.last_year ?? "—"),
    statTile("Avg RT", t.avg_rt != null ? `${Math.round(t.avg_rt * 100)}%` : "—"),
    statTile("Avg TMDB", t.avg_tmdb != null ? t.avg_tmdb.toFixed(2) : "—")
  ]);
}

// The posters, oldest first, captioned with year and RT as in the app. They
// set the trail, so a film page steps through this person's films.
export function spotlightFilms(s) {
  return trail(
    grid(s.films.map((f) => filmCard(f, `${f.year}${f.rt != null ? ` RT ${Math.round(f.rt)}%` : ""}`))),
    s.name, s.films.map((f) => f.id));
}

// The genre pie, folded to the palette as charts.fold_counts folds it, and
// the films-by-decade bars, in panels.spotlight_figures' layout.
async function spotlightFigures(s) {
  const slugs = new Set(s.films.map((f) => f.slug));
  const genres = (await Promise.all([...slugs].map((slug) => query("film_genres", slug))))
    .flat().map((g) => g.genre);
  const counts = [...genres.reduce((m, g) => m.set(g, (m.get(g) ?? 0) + 1), new Map())]
    .sort((a, b) => b[1] - a[1]);
  const top = counts.slice(0, SERIES.length);
  const other = counts.slice(SERIES.length).reduce((n, [, c]) => n + c, 0);
  const labels = [...top.map(([g]) => g), ...(other ? ["Other"] : [])];
  const values = [...top.map(([, c]) => c), ...(other ? [other] : [])];
  const pie = {
    data: [{type: "pie", labels, values, hole: 0.45, sort: false, direction: "clockwise",
            marker: {colors: labels.map((l, i) => (l === "Other" ? OTHER : SERIES[i]))},
            textinfo: "label+percent", textfont: {size: 10}}],
    layout: {paper_bgcolor: INK, font: {color: TAPE}, height: 270, showlegend: false,
             margin: {t: 10, b: 10, l: 10, r: 10}}
  };
  const decades = [...s.films.reduce((m, f) => {
    const d = Math.floor(f.year / 10) * 10;
    return f.year == null ? m : m.set(d, (m.get(d) ?? 0) + 1);
  }, new Map())].sort((a, b) => a[0] - b[0]);
  const bars = {
    data: [{type: "bar", x: decades.map(([d]) => `${d}s`), y: decades.map(([, n]) => n),
            text: decades.map(([, n]) => n), textposition: "outside", cliponaxis: false,
            marker: {color: MINT_DEEP}}],
    layout: {paper_bgcolor: INK, plot_bgcolor: INK_2, font: {color: TAPE}, height: 270,
             margin: {t: 10, b: 10, l: 10, r: 10}, showlegend: false,
             xaxis: {gridcolor: LINE, linecolor: LINE}, yaxis: {visible: false}}
  };
  return {genres: pie, decades: bars};
}

// Genre mix, films by decade, and the collaborators. `resize` is Framework's,
// passed in because it exists only inside a page.
export async function spotlightPanels(s, resize) {
  const k = KINDS[s.kind];
  const figures = await spotlightFigures(s);
  const who = (c) => c.slug ? html`<a href=${pageHref(k.other, c.slug)}>${c.name}</a>` : c.name;
  return html`<div class="rw-cols c3">
    <div><p class="rw-sub">Genre mix</p>${resize((width) => plot(figures.genres, width))}</div>
    <div><p class="rw-sub">Films by decade</p>${resize((width) => plot(figures.decades, width))}</div>
    <div><p class="rw-sub">${k.collab}</p>
      ${rankedList(s.collaborators.map((c) => ({...c, n: c.films})), who, k.empty(s.name))}
      ${s.collaborators.length ? html`<p class="ch-note">${k.note}</p>` : ""}
    </div>
  </div>`;
}

// The app's picker: the twenty most-featured, as linked chips.
export function spotlightPicker(people, kind, current = null) {
  return html`<div class="rw-kw-field">${people.map((p) => p.name === current
    ? html`<span class="rw-kw-chip b2 is-here">${p.name} <b>${p.films}</b></span>`
    : html`<a class="rw-kw-chip b3" href=${pageHref(kind, p.slug)}>${p.name} <b>${p.films}</b></a>`)}</div>`;
}
