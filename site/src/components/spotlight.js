// The Directors and Actors sections' spotlight: one panel for both, as
// panels.person_spotlight is in the app. Step 15 writes its numbers, films,
// two charts and collaborators to data/directors|actors/<slug>.json.

import {html} from "npm:htl";
import {filmCard, grid, rankedList, statRail, statTile, trail} from "./ui.js";
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

export function spotlightTiles(s) {
  return statRail(s.tiles.map((t) => statTile(t.label, t.value)));
}

// The posters, oldest first, captioned with year and RT as in the app. They
// set the trail, so a film page steps through this person's films.
export function spotlightFilms(s, base) {
  return trail(
    grid(s.films.map((f) => filmCard(f, `${f.year}${f.rt != null ? ` RT ${f.rt}%` : ""}`, base))),
    s.name, s.films.map((f) => f.id));
}

// Genre mix, films by decade, and the collaborators. `resize` is Framework's,
// passed in because it exists only inside a page.
export function spotlightPanels(s, base, resize) {
  const k = KINDS[s.kind];
  const who = (c) => c.id ? html`<a href=${`${base}${k.other}/${c.id}`}>${c.name}</a>` : c.name;
  return html`<div class="rw-cols c3">
    <div><p class="rw-sub">Genre mix</p>${resize((width) => plot(s.figures.genres, width))}</div>
    <div><p class="rw-sub">Films by decade</p>${resize((width) => plot(s.figures.decades, width))}</div>
    <div><p class="rw-sub">${k.collab}</p>
      ${rankedList(s.collaborators.map((c) => ({...c, n: c.films})), who, k.empty(s.name))}
      ${s.collaborators.length ? html`<p class="ch-note">${k.note}</p>` : ""}
    </div>
  </div>`;
}

// The spotlight's people as linked chips with their film counts: the site's
// version of the app's picker.
export function spotlightPicker(people, kind, base, current = null) {
  return html`<div class="rw-kw-field">${people.map((p) => p.name === current
    ? html`<span class="rw-kw-chip b2 is-here">${p.name} <b>${p.films}</b></span>`
    : html`<a class="rw-kw-chip b3" href=${`${base}${kind}/${p.id}`}>${p.name} <b>${p.films}</b></a>`)}</div>`;
}
