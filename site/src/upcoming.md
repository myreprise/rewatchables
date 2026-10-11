---
title: Upcoming Films
---

```js
// The app's Upcoming section: films listeners have put forward, before they
// have an episode. Step 15 writes every request with its reason; the filters
// below run over them here, as the section's widgets filter its frame. Each
// request has a page at request?id=<slug>.
import {filmCard, filmHref, pageHref, fmt, grid, gridNote, masthead, posterUrl, posterCard, statRail,
        statTile, tape, whyPanel} from "./components/ui.js";

import {asFilm, list, query as dbQuery, section} from "./components/db.js";

// The section's numbers, and the requests and graduates from their tables.
const u = await section("upcoming");
const requests = await dbQuery("requests");
u.requests = requests.map((r) => ({
  id: r.slug, title: r.title, year_raw: r.year_raw, year: r.year, decade: r.decade,
  sort: r.sort_title, order: r.ord, poster: r.poster, tmdb: r.tmdb, contributor: r.contributor,
  note: r.note, tags: list(r.tags), by: r.by_label ? {label: r.by_label, href: r.by_href} : null}));
u.graduated = (await dbQuery("graduated")).map((g) => ({...asFilm(g), requested_as: g.requested_as,
  aired: g.aired, episodes: g.episodes}));
u.unmatched = requests.filter((r) => !r.resolved).map((r) => ({
  id: r.slug, title: r.title, year_raw: r.year_raw, note: r.unresolved_note}));
```

```js
display(masthead("Films still in the queue", "Listener-contributed requests for future episodes, with the reason each one is on the list."));
if (u.empty) {
  display(html`<p class="rw-ov-note">No upcoming-films data in this build yet.</p>`);
} else {
  const s = u.summary;
  display(statRail([
    statTile("In contention", s.in_contention.toLocaleString()),
    statTile("Already made", s.already_made, "", true),
    statTile("Span", s.first_year ? `${s.first_year}–${s.last_year}` : null),
    statTile("Contributors", s.contributors),
    statTile("Matched to TMDB", Math.round(100 * s.matched / s.in_contention), "%")
  ]));
}
```

```js
// The app's four filters. A tag on one film only is a caption, not an axis,
// so only tags on two or more are offered.
const decades = [...new Set(u.requests.map((r) => r.decade).filter((d) => d != null))].sort();
const queryInput = Inputs.text({label: "Search title or reason", placeholder: "e.g. Fincher, mailbag, blockbuster"});
const decadeInput = Inputs.select(["All", ...decades.map((d) => `${d}s`)], {label: "Decade"});
const tagInput = Inputs.select(["All", ...u.offered_tags], {label: "Pitched as"});
const sortInput = Inputs.select(["Source order", "Title", "Year (newest)", "Year (oldest)", "TMDB rating"], {label: "Sort by"});
display(html`<div class="rw-filters">${queryInput}${decadeInput}${tagInput}${sortInput}</div>`);
const query = Generators.input(queryInput);
const decadePick = Generators.input(decadeInput);
const tagPick = Generators.input(tagInput);
const sortPick = Generators.input(sortInput);
```

```js
// Search reaches the title, the note, the pitch and who put it forward.
const needle = query.trim().toLowerCase();
const has = (text) => (text ?? "").toLowerCase().includes(needle);
const listed = u.requests
  .filter((r) => !needle || has(r.title) || has(r.note) || has(r.tags.join(", ")) || has(r.contributor))
  .filter((r) => decadePick === "All" || r.decade === Number(decadePick.slice(0, -1)))
  .filter((r) => tagPick === "All" || r.tags.includes(tagPick));
const last = (x, y, ascending) => (x == null || y == null ? (x == null) - (y == null) : ascending ? x - y : y - x);
const by = {
  "Source order": (a, b) => a.order - b.order,
  "Title": (a, b) => a.sort.localeCompare(b.sort),
  "Year (newest)": (a, b) => last(a.year, b.year, false) || a.order - b.order,
  "Year (oldest)": (a, b) => last(a.year, b.year, true) || a.order - b.order,
  "TMDB rating": (a, b) => last(a.tmdb, b.tmdb, false) || a.order - b.order
}[sortPick];
listed.sort(by);

display(gridNote(`${listed.length} of ${u.requests.length} films`, "click a poster for the pitch"));
display(listed.length
  ? grid(listed.map((r) => posterCard(r, r.year_raw ?? "—", pageHref("request", r.id))))
  : html`<p class="rw-ov-note">No requested film matches those filters.</p>`);
```

```js
display(tape("Why these films"));
const s = u.summary;
display(html`<p class="rw-up-note">Every request carries either a note citing where the film came up on air, or a comma-separated pitch. They are alternatives, not both — the source records one or the other. <b>${s.with_note}</b> films have a note, <b>${s.with_tags}</b> have tags.</p>`);
const shown = listed.slice(0, u.why_shown);
display(html`<div class="rw-cols c2">${shown.map((r) => html`<div class="rw-dt-panel" style="padding:13px 15px 15px">
  <h4><a href=${pageHref("request", r.id)}>${r.title}</a> · ${r.year_raw ?? "—"}</h4>${whyPanel(r)}
</div>`)}</div>`);
if (listed.length > shown.length) {
  display(html`<p class="rw-ov-note">Showing the first ${shown.length} of ${listed.length}. Narrow the filters above to reach the rest.</p>`);
}
```

```js
if (u.offered_tags.length) {
  display(tape("The angles people pitch"));
  display(html`<div class="rw-kw-field">${u.top_tags.map((t) =>
    html`<span class="rw-kw-chip b4">${t.tag} <b>${t.n}</b></span>`)}</div>`);
}
```

```js
display(tape("They actually made these"));
display(u.graduated.length
  ? html`<p class="rw-up-note"><b>${u.graduated.length}</b> requested films have since been covered. They are matched on TMDB id rather than on title — the list also holds a different <i>Crash</i>, a different <i>Heat</i> and a different <i>Miami Vice</i> from the ones in the catalogue, and matching on title would have removed all three.</p>`
  : html`<p class="rw-up-note">Nothing on the list has become an episode yet. When one does it moves here automatically, and stops appearing above.</p>`);
display(html`<div>${u.graduated.map((g) => html`<a class="rw-up-grad-link" href=${g.id ? filmHref(g.id) : null}>
  <div class="rw-up-grad">${g.poster ? html`<img src=${posterUrl(g.poster)} alt="">` : ""}
    <div class="b"><span class="t">${g.title} (${g.year})</span>
      <span class="m">Requested as <b>${g.requested_as}</b> · aired ${g.aired ? fmt.monYear(g.aired) : "—"} · ${g.episodes}×</span>
    </div>
  </div></a>`)}</div>`);
```

```js
if (u.unmatched.length) {
  display(tape("Not matched to a film"));
  display(html`<p class="rw-up-note"><b>${u.unmatched.length}</b> requests carry no TMDB match, so they show without a poster. Two are TV series on a list of films, one gives no year, and the rest are titles TMDB spells differently. They are kept rather than hidden — each is a real request — and a film with no id can never be mistaken for one that has already aired.</p>`);
  display(html`<div>${u.unmatched.map((r) => html`<a class="rw-up-grad-link" href=${pageHref("request", r.id)}>
    <div class="rw-up-grad" style="border-left-color:var(--line-2)"><div class="b">
      <span class="t">${r.title}${r.year_raw ? ` (${r.year_raw})` : ""}</span><span class="m">${r.note}</span>
    </div></div></a>`)}</div>`);
}
```
