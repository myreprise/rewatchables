---
title: Person
---

```js
// The person page, for everyone in the room but the anchor:
// person?id=chris-ryan. The Hosts & Guests section's "Look someone up"
// panel. The bench, their company and their permutation-tested leans were
// worked out by step 15; their episodes and verdicts are queries on site.db.
import {asFilm, pageId, query, row, sectionValue} from "./components/db.js";
import {badge, filmCard, fmt, grid, masthead, personHref, personLink, rankedList,
        statRail, statTile, tape, trail} from "./components/ui.js";

const me = await row("person", pageId());
const [people, shelf, company, leans, verdicts, catalogue, leanFloor, verdictFloor] = await Promise.all([
  query("people"),
  me ? query("person_shelf", me.name) : [],
  me ? query("person_company", me.name) : [],
  me ? query("person_leans", me.name) : [],
  me ? query("person_verdicts", me.name) : [],
  query("catalogue"),
  sectionValue("hosts", "lean_floor"),
  sectionValue("verdicts", "verdict_floor")
]);
```

```js
if (!me) {
  display(html`<a class="rw-back" href="./hosts">← Hosts & Guests</a>`);
  display(html`<p class="rw-ov-note">No one in the room at this address.</p>`);
}
```

```js
if (me) {
  document.title = `${me.name} | Rewatchables Explorer`;
  const share = me.episodes / catalogue[0].airings;

  // The app's picker: everyone, most episodes first. Picking a name goes there.
  const picker = Inputs.select(people, {
    label: "Look someone up", value: people.find((p) => p.slug === me.slug),
    format: (p) => `${p.name} (${p.episodes})`
  });
  picker.addEventListener("input", () => { location.href = personHref(picker.value.slug); });

  display(masthead(me.name, "Everyone who sits in with Bill Simmons has a page like this one: when they were on, who they sit with, and which films they get booked on."));
  display(html`<div class="rw-filters">${picker}</div>`);
  display(statRail([
    statTile("Episodes", me.episodes),
    statTile("Of all episodes", share >= 0.005 ? `${Math.round(100 * share)}%` : "<1%"),
    statTile("In the host chair", me.hosted),
    statTile("First on", fmt.monYear(me.first)),
    statTile("Latest", fmt.monYear(me.last))
  ]));

  display(tape(`On the show — ${shelf.length} episode${shelf.length !== 1 ? "s" : ""}`));
  // Newest first, as the app's lookup orders it. A revisit can put one film on
  // the shelf twice, so the trail walks films, each once.
  display(trail(
    grid(shelf.map((e) => filmCard(asFilm(e), `Ep ${e.number} · ${fmt.monYear(e.date)}`))),
    me.name, [...new Set(shelf.map((e) => e.slug))]));

  const tally = Object.fromEntries(verdicts.map((v) => [v.verdict, v.n]));
  const v = {cruise: tally.Cruise ?? 0, hanks: tally.Hanks ?? 0, ties: tally.Tie ?? 0};
  v.n = verdicts.reduce((s, x) => s + x.n, 0);
  const record = v.n >= verdictFloor
    ? html`<p class="ch-note"><b>Cruise ${v.cruise} – Hanks ${v.hanks}</b>${v.ties ? `, ${v.ties} tie${v.ties !== 1 ? "s" : ""}` : ""}, across ${v.n} verdict episodes.</p>`
    : html`<p class="ch-note">${v.n} verdict episode${v.n !== 1 ? "s" : ""}; a record is read from ${verdictFloor}.</p>`;

  // Mint marks a measure above the rest of the show and grey one below; the
  // words carry the direction too, so colour is never the only cue.
  const leanChips = !me.regular
    ? html`<p class="ch-note">Fewer than ${leanFloor} episodes: too few to compare with the rest of the show.</p>`
    : leans.length
      ? html`<div class="chip-row">${leans.map((l) => badge(l.phrase, l.up ? "mint" : ""))}</div>`
      : html`<div class="chip-row"><span class="rw-lean-none">No detectable lean</span></div>`;

  display(html`<div class="rw-split even">
    <div>
      <h4 class="rw-dt-loose">Who they sit with</h4>
      ${rankedList(company.map((c) => ({...c, id: c.slug, n: c.episodes})), (c) => personLink(c),
                   `${me.name} has only ever been on with Bill.`)}
      ${company.length ? html`<p class="ch-note">Episodes shared, Bill aside.</p>` : ""}
    </div>
    <div>
      <h4 class="rw-dt-loose">What they get booked on</h4>
      ${leanChips}
      <h4 class="rw-dt-loose">Cruise vs. Hanks</h4>
      ${record}
    </div>
  </div>`);
}
```
