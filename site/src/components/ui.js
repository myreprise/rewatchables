// The pieces every page is drawn from: cards, tiles, tape headings, badges.
//
// The site's counterpart of src/rewatchables/app/components.py and views.py. It
// emits the same rw-* markup, so theme.css (copied from the app by pipeline
// step 15) styles both front ends. Presentation only: what to show is decided
// in Python by step 15, and a page hands these the rows it was given.

import {html, svg} from "npm:htl";

const TMDB = "https://image.tmdb.org/t/p";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                     "August", "September", "October", "November", "December"];

// Posters come from TMDB's image CDN at the widths the app draws: w185 for
// grids, w342 for the film page and the spotlight.
export function posterUrl(poster, size = "w185") {
  return poster ? `${TMDB}/${size}/${poster}` : null;
}

// Step 15 writes dates as YYYY-MM-DD. They are split by hand rather than handed
// to Date, which reads a bare date as UTC midnight and shows the day before
// anywhere west of Greenwich.
function parts(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return {y, m, d};
}
export const fmt = {
  dayMonYear: (iso) => { if (!iso) return "date unknown"; const {y, m, d} = parts(iso); return `${d} ${MONTHS[m - 1]} ${y}`; },
  monDay: (iso) => { const {m, d} = parts(iso); return `${MONTHS[m - 1]} ${d}`; },
  monYear: (iso) => { const {y, m} = parts(iso); return `${MONTHS[m - 1]} ${y}`; },
  longDate: (iso) => { const {y, m, d} = parts(iso); return `${LONG_MONTHS[m - 1]} ${d}, ${y}`; },
  year: (iso) => (iso ? iso.slice(0, 4) : "—")
};

export function rings(cls = "rw-watermark", color = "#2BE8A0") {
  return svg`<svg class=${cls} viewBox="0 0 100 100" aria-hidden="true">
    <g fill="none" stroke=${color} stroke-width="4">
      ${[9, 16, 23, 30, 37, 44].map((r) => svg`<circle cx="50" cy="50" r=${r}></circle>`)}
    </g>
    <path d="M55 3 L46 11 L55 19 M65 3 L56 11 L65 19" fill="none" stroke=${color}
      stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

export function masthead(title, subtitle) {
  return html`<div class="rw-masthead">${rings()}<h1>${title}</h1>${subtitle ? html`<p>${subtitle}</p>` : ""}</div>`;
}

let tapes = 0;
export function tape(text) {
  tapes += 1;
  return html`<div class="rw-tape-row"><span class=${tapes % 2 ? "rw-tape" : "rw-tape alt"}>${text}</span></div>`;
}

// A missing value reads as n/a, never 0: coverage is genuinely partial.
export function statTile(label, value, unit = "", coral = false) {
  return html`<div class=${coral ? "rw-dt-stat is-coral" : "rw-dt-stat"}>
    <span class="k">${label}</span>
    ${value == null
      ? html`<span class="miss">— n/a</span>`
      : html`<span class="v">${value}<span class="u">${unit}</span></span>`}
  </div>`;
}

export function statRail(tiles) {
  return html`<div class="rw-dt-rail">${tiles}</div>`;
}

// Grid posters load lazily: All films draws 458 of them. The film page's hero
// is above the fold, so it loads at once.
function plate(film, size, cls, lazy = true) {
  const src = posterUrl(film.poster, size);
  return src
    ? html`<img class=${cls} src=${src} alt="" loading=${lazy ? "lazy" : "eager"}>`
    : html`<div class=${`poster-plate ${cls}`}>${rings("")}<b>${film.title}</b></div>`;
}

// `base` is the relative path back to the site root from the page drawing the
// card: "./" from a top-level page, "../" from a film page. Relative links keep
// the site working under a GitHub Pages project path (/rewatchables/).
export function filmHref(id, base) {
  return `${base}movie/${id}`;
}

// `tone` ("cruise", "hanks", "tie") adds the app's verdict band under the art.
// The caption is expected to say the same in words.
export function filmCard(film, subtitle, base, tone = "") {
  return html`<a class="rw-cardlink" href=${filmHref(film.id, base)}>
    <div class="poster-card">
      ${plate(film, "w185", "poster-img")}
      ${tone ? html`<div class=${`poster-rule ${tone}`}></div>` : ""}
      <div class="poster-label"><strong>${film.title}</strong><span>${subtitle ?? ""}</span></div>
    </div>
  </a>`;
}

export function grid(cards, cls = "rw-grid") {
  return html`<div class=${cls}>${cards}</div>`;
}

export function heroPlate(film) {
  return plate(film, "w342", "", false);
}

export function stars(value) {
  if (value == null) return null;
  return "★".repeat(Math.floor(value)) + (value % 1 ? "½" : "");
}

export function badge(text, tone = "") {
  return html`<span class=${tone ? `badge badge-${tone}` : "badge"}>${text}</span>`;
}

export function note(content) {
  return html`<p class="rw-ov-note">${content}</p>`;
}

export function gridNote(...spans) {
  return html`<div class="rw-kw-gridnote">${spans.map((s) => html`<span>${s}</span>`)}</div>`;
}

// ── Links between pages ──────────────────────────────────────────────────────
// Every page has an address made by step 15 from its name: movie/heat-1995,
// keyword/heist, person/chris-ryan. A null id means the thing has no page (a
// keyword on one film, the anchor), and it is drawn as plain text.

// A keyword chip carrying its reach. With a page it is a link; `current`
// marks the keyword whose page this is.
export function keywordChip(k, base, current = false) {
  const cls = current ? `rw-kw-chip ${k.band} is-here` : `rw-kw-chip ${k.band}`;
  if (!k.id || current) {
    return html`<span class=${k.id || current ? cls : "rw-kw-chip is-inert"}>${k.word} <b>${k.reach}</b></span>`;
  }
  return html`<a class=${cls} href=${`${base}keyword/${k.id}`}>${k.word} <b>${k.reach}</b></a>`;
}

export function chipField(chips, base, current = null) {
  return html`<div class="rw-kw-field">${chips.map((k) => keywordChip(k, base, k.word === current))}</div>`;
}

export function personHref(id, base) {
  return `${base}person/${id}`;
}

// A name, linked to its page when it has one.
export function personLink(person, base) {
  return person.id ? html`<a href=${personHref(person.id, base)}>${person.name}</a>` : person.name;
}

// views.decade_bars: a decade histogram scaled to its own tallest column.
export function decadeBars(rows) {
  const peak = Math.max(...rows.map((r) => r.n));
  return html`<div class="rw-kw-bars">${rows.map((r) => html`
    <div class=${r.n === peak && r.n ? "rw-kw-bar is-peak" : "rw-kw-bar"}>
      <span class="v">${r.n}</span>
      <span class="track"><i style=${`height:${peak ? Math.round(100 * r.n / peak) : 0}%`}></i></span>
      <span class="d">${r.decade}s</span>
    </div>`)}</div>`;
}

// components.ranked_list: name, bar, count. `label` draws the name, so it can
// be a link.
export function rankedList(rows, label, empty) {
  if (!rows.length) return html`<p class="rw-ov-note">${empty}</p>`;
  const top = Math.max(...rows.map((r) => r.n));
  return html`<div>${rows.map((r) => html`<div class="rw-rank">
    <span class="n">${label(r)}</span>
    <span class="bar"><i style=${`width:${100 * r.n / top}%`}></i></span>
    <span class="c">${r.n}</span>
  </div>`)}</div>`;
}

// ── The trail ────────────────────────────────────────────────────────────────
// The app's dossier steps through the list it was opened from: the Explorer's
// filtered films, a person's episodes. Pages here are separate documents, so a
// list remembers itself when a poster in it is clicked, and the film page
// reads it back. Session storage: per tab, gone when the tab closes. It can be
// missing or throw (a private window, blocked storage), and then a film page
// simply has no arrows.

const TRAIL = "rw-trail";

// Remember `ids` as the list a film was opened from, whenever a poster inside
// `container` is clicked. `back` defaults to this page, filters and all.
export function trail(container, label, ids, back = null) {
  container.addEventListener("click", (event) => {
    if (!event.target.closest("a.rw-cardlink")) return;
    try {
      sessionStorage.setItem(TRAIL, JSON.stringify({
        label, ids, back: back ?? location.pathname + location.search
      }));
    } catch {
      // No storage: the film page falls back to its plain back link.
    }
  });
  return container;
}

// The remembered list, if this film is on it: {label, back, ids, at}.
export function readTrail(id) {
  try {
    const t = JSON.parse(sessionStorage.getItem(TRAIL));
    const at = t?.ids?.indexOf(id) ?? -1;
    return at >= 0 ? {...t, at} : null;
  } catch {
    return null;
  }
}

// A film's title, linked to its page when it has one.
export function filmLink(film, base) {
  return film.id ? html`<a href=${filmHref(film.id, base)}>${film.title}</a>` : film.title;
}

// A plain table, for the app's small st.dataframe tables. `columns` is
// [[header, row => cell, "num"?], ...]; a "num" column is right-aligned.
export function table(rows, columns) {
  return html`<div class="rw-table-wrap"><table class="rw-table">
    <thead><tr>${columns.map(([h, , num]) => html`<th class=${num ? "num" : ""}>${h}</th>`)}</tr></thead>
    <tbody>${rows.map((r) => html`<tr>${columns.map(([, cell, num]) => html`<td class=${num ? "num" : ""}>${cell(r)}</td>`)}</tr>`)}</tbody>
  </table></div>`;
}
