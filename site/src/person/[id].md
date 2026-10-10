---
title: Person
---

```js
// One page per person in the room, at /person/<slug>: the Hosts & Guests
// section's "Look someone up" panel. Step 15 writes data/people/<slug>.json
// with the section's own functions, the permutation-tested leans included.
import {badge, filmCard, fmt, grid, masthead, personHref, personLink, rankedList,
        statRail, statTile, tape, trail} from "../components/ui.js";

const me = FileAttachment(`../data/people/${observable.params.id}.json`).json();
const people = FileAttachment("../data/people.json").json();
```

```js
document.title = `${me.name} | Rewatchables Explorer`;

// The app's picker: everyone, most episodes first. Picking a name goes there.
const picker = Inputs.select(people, {
  label: "Look someone up", value: people.find((p) => p.id === me.id),
  format: (p) => `${p.name} (${p.episodes})`
});
picker.addEventListener("input", () => { location.href = personHref(picker.value.id, "../"); });

display(masthead(me.name, "Everyone who sits in with Bill Simmons has a page like this one: when they were on, who they sit with, and which films they get booked on."));
display(html`<div class="rw-filters">${picker}</div>`);
display(statRail([
  statTile("Episodes", me.episodes),
  statTile("Of all episodes", me.share >= 0.005 ? `${Math.round(100 * me.share)}%` : "<1%"),
  statTile("In the host chair", me.hosted),
  statTile("First on", fmt.monYear(me.first)),
  statTile("Latest", fmt.monYear(me.last))
]));
```

```js
display(tape(`On the show — ${me.shelf.length} episode${me.shelf.length !== 1 ? "s" : ""}`));
// Newest first, as the app's lookup orders it. A revisit can put one film on
// the shelf twice, so the trail walks films, each once.
display(trail(
  grid(me.shelf.map((f) => filmCard(f, `Ep ${f.episode} · ${fmt.monYear(f.aired)}`, "../"))),
  me.name, [...new Set(me.shelf.map((f) => f.id))]));
```

```js
const v = me.verdicts;
const record = v.n >= me.verdict_floor
  ? html`<p class="ch-note"><b>Cruise ${v.cruise} – Hanks ${v.hanks}</b>${v.ties ? `, ${v.ties} tie${v.ties !== 1 ? "s" : ""}` : ""}, across ${v.n} verdict episodes.</p>`
  : html`<p class="ch-note">${v.n} verdict episode${v.n !== 1 ? "s" : ""}; a record is read from ${me.verdict_floor}.</p>`;

// Mint marks a measure above the rest of the show and grey one below; the
// words carry the direction too, so colour is never the only cue.
const leans = !me.regular
  ? html`<p class="ch-note">Fewer than ${me.lean_floor} episodes: too few to compare with the rest of the show.</p>`
  : me.leans.length
    ? html`<div class="chip-row">${me.leans.map((l) => badge(l.text, l.up ? "mint" : ""))}</div>`
    : html`<div class="chip-row"><span class="rw-lean-none">No detectable lean</span></div>`;

display(html`<div class="rw-split even">
  <div>
    <h4 class="rw-dt-loose">Who they sit with</h4>
    ${rankedList(me.company.map((c) => ({...c, n: c.episodes})), (c) => personLink(c, "../"),
                 `${me.name} has only ever been on with Bill.`)}
    ${me.company.length ? html`<p class="ch-note">Episodes shared, Bill aside.</p>` : ""}
  </div>
  <div>
    <h4 class="rw-dt-loose">What they get booked on</h4>
    ${leans}
    <h4 class="rw-dt-loose">Cruise vs. Hanks</h4>
    ${record}
  </div>
</div>`);
```
