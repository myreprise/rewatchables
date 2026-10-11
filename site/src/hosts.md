---
title: Hosts & Guests
---

```js
// The app's Hosts & Guests section. Its numbers, heatmaps, leans and the
// "Without Bill" episodes come from sections/hosts.py, run by pipeline step
// 15. "Look someone up" is the person pages, one per name, at /person/<slug>.
import {badge, filmCard, fmt, grid, gridNote, masthead, personHref, personLink,
        rankedList, statRail, statTile, table, tape, trail} from "./components/ui.js";
import {plot} from "./components/plot.js";

const h = FileAttachment("data/sections/hosts.json").json();
const people = FileAttachment("data/people.json").json();
```

```js
const chart = (name) => resize((width) => plot(h.figures[name], width));
const pct = (x) => `${Math.round(100 * x)}%`;

display(masthead("Hosts & Guests", "Everyone who sits in with Bill Simmons: look anyone up, see when they were on, who they sit with, and which films they get booked on."));
display(statRail([
  statTile("Film episodes", h.episodes),
  statTile("With Bill Simmons", pct(h.with_anchor / h.episodes)),
  statTile("Without him", h.without_anchor),
  statTile("Everyone else", h.everyone_else),
  statTile("On five or more", h.five_or_more)
]));
display(html`<p class="ch-note">Bill Simmons is on <b>${h.with_anchor} of ${h.episodes}</b> film episodes and hosts ${h.anchor_hosted} of them, so a chart that counts him is mostly a chart of him. Every panel below leaves him out. The host chair only tells you something on the ${h.without_anchor} episodes he is not on, which close the page.</p>`);
```

```js
// The app's lookup: each name opens that person's page.
display(tape("Look someone up"));
const picker = Inputs.select([null, ...people], {
  label: "Person", format: (p) => (p ? `${p.name} (${p.episodes})` : "Pick someone…")
});
picker.addEventListener("input", () => { if (picker.value) location.href = personHref(picker.value.id, "./"); });
display(html`<div class="rw-filters">${picker}</div>`);
```

```js
display(tape("The bench"));
display(Inputs.table(h.bench, {
  columns: ["name", "episodes", "share", "hosted", "first", "last"],
  header: {name: "Person", episodes: "Episodes", share: "Share", hosted: "Hosted", first: "First on", last: "Latest"},
  format: {
    name: (n, i) => personLink(h.bench[i], "./"),
    episodes: (v) => html`<span class="rw-bench-bar"><i style=${`width:${100 * v / h.most_episodes}%`}></i></span>${v}`,
    share: (v) => `${v.toFixed(1)}%`,
    first: (v) => fmt.monYear(v), last: (v) => fmt.monYear(v)
  },
  rows: 16, layout: "auto", select: false
}));
display(html`<p class="ch-note">Everyone on ${h.bench_floor} or more episodes. The other ${h.off_bench} have been on once or twice — ${h.once} of them just once — and every one is in the lookup above.</p>`);
```

```js
display(tape("Who’s on when"));
display(chart("who_is_on_when"));
display(html`<p class="ch-note">The ${h.when_top} people on the most episodes, in the order they first appeared. A cell is the share of that year’s film episodes they were on, so a light year and a busy one read on the same scale; the count under each year is how many aired. The colour tops out at 80%.</p>`);
```

```js
display(tape("Who sits together"));
display(html`<div class="rw-cols c32">
  <div>${chart("who_sits_together")}</div>
  <div><p class="rw-sub">Most common lineups</p>
    ${rankedList(h.lineups.map((l) => ({name: l.lineup, n: l.episodes})), (l) => l.name, "No lineup has repeated.")}
  </div>
</div>`);
display(html`<p class="ch-note">The ${h.ring_top} people on the most episodes. A cell is the number of episodes a pair shared; an empty one is a pair who have never been in the room together. A lineup is everyone in the room except Bill, so a single name is that person with Bill.</p>`);
```

```js
// Mint is above the rest of the show, grey below; the words carry the
// direction too.
display(tape("What each regular gets booked on"));
display(html`<div>${h.regulars.map((r) => html`<div class="rw-lean">
  <div class="n">${personLink(r, "./")}<span>${r.episodes} episodes</span></div>
  <div class="l">${r.leans.length
    ? r.leans.map((l) => badge(l.text, l.up ? "mint" : ""))
    : html`<span class="rw-lean-none">No detectable lean</span>`}</div>
</div>`)}</div>`);
const q = h.quiet;
const quiet = q.length > 1 ? `${q.slice(0, -1).join(", ")} and ${q.at(-1)} show none. ` : q.length ? `${q[0]} shows none. ` : "";
display(html`<p class="ch-note">The sheet doesn’t record who picked a film, so this is what each person gets <b>booked on</b>, not what they like: a guest brought in for a month of rom-coms shows a romance lean whether or not they chose the films. Each of the ${h.regulars.length} people on ${h.lean_floor}+ episodes is compared with every episode they were not on — on Rotten Tomatoes score, the film’s age when it aired, and the share of episodes in each of the ${h.genres_tested} genres on ${h.genre_floor}+ episodes. That is ${h.comparisons} comparisons, each a ${h.n_perm.toLocaleString()}-shuffle permutation test, and a lean is shown only if it survives a Benjamini–Hochberg correction at q &lt; ${h.lean_q}: <b>${h.held} of ${h.comparisons}</b> do. ${quiet}Films carry several genres, so the genre comparisons overlap. Mint is above the rest of the show, grey below.</p>`);
display(html`<details class="rw-more"><summary>All ${h.comparisons} comparisons</summary>
  ${Inputs.table(h.all_comparisons, {
    columns: ["name", "measure", "episodes", "theirs", "others", "gap", "p", "q", "shown"],
    header: {name: "Person", measure: "Measure", episodes: "Episodes", theirs: "Their episodes",
             others: "Everyone else", gap: "Gap", p: "p", q: "q", shown: "Shown"},
    format: {name: (n, i) => personLink(h.all_comparisons[i], "./"),
             p: (v) => v.toFixed(4), q: (v) => v.toFixed(4), shown: (v) => (v ? "✓" : "")},
    rows: 16, layout: "auto", select: false
  })}
</details>`);
```

```js
display(tape(`Without Bill — ${h.without.reduce((n, g) => n + g.episodes.length, 0)} episodes`));
display(html`<p class="ch-note">The only episodes where the host chair says something. Grouped by who hosted, busiest first; oldest episode first within each.</p>`);
for (const g of h.without) {
  const n = g.episodes.length;
  display(gridNote(html`${personLink({name: g.host, id: g.id}, "./")} hosting · ${n} episode${n === 1 ? "" : "s"}`));
  display(trail(grid(g.episodes.map((f) => filmCard(f, `Ep ${f.episode} · ${fmt.monYear(f.aired)}`, "./"))),
                `${g.host} hosting`, [...new Set(g.episodes.map((f) => f.id))]));
}
```
