---
title: Cruise vs. Hanks
---

```js
// The app's Cruise vs. Hanks section. Every number, chart and list comes from
// sections/verdicts.py (standing, running_margin, figures, tale_of_the_tape,
// streaks, guest_split), run by pipeline step 15. The ledger filters in the
// browser, as the app's selectbox and search filter its frame.
import {filmCard, gridNote, grid, personLink, posterUrl, table, tape, trail} from "./components/ui.js";
import {plot} from "./components/plot.js";

import {query, section} from "./components/db.js";

// The ledger is the ledger query over the episodes; the rest is the section's.
const v = {...await section("verdicts"),
           ledger: (await query("ledger")).map((e) => ({
             id: e.slug, title: e.title, year: e.year, poster: e.poster,
             episode: e.number, verdict: e.verdict}))};
```

```js
const s = v.standing;
const chart = (name) => resize((width) => plot(v.figures[name], width));

// The poster rails are each actor's covered films, by TMDB popularity.
const rail = (side, fighter) => html`<div class=${`ch-rail ${side}`}>${fighter.rail.map((f) =>
  html`<img src=${posterUrl(f.poster, "w342")} alt="" loading="lazy">`)}</div>`;
const corner = (cls, name, tally, fighter) => html`<div class=${cls === "h" ? "ch-fighter r" : "ch-fighter"}>
  <div class=${`ch-face ${cls}`}><img src=${posterUrl(fighter.portrait, "w342")} alt=${name}></div>
  <div><div class=${`ch-name ${cls}`}>TOM<br>${name.split(" ")[1].toUpperCase()}</div>
    <div class="ch-tally">${tally}</div>
    <div class="ch-sub">${fighter.films} films covered</div></div>
</div>`;

display(html`<div class="ch-hero">
  ${rail("l", v.cruise)}${rail("r", v.hanks)}
  <div class="ch-hero-inner">
    ${corner("c", "Tom Cruise", s.cruise, v.cruise)}
    <div class="ch-vs"><div class="bolt">EP ${s.first_ep} – ${s.last_ep}</div>
      <div class="q">Who ya got?</div><div class="blurb">${s.ties} ties</div></div>
    ${corner("h", "Tom Hanks", s.hanks, v.hanks)}
  </div>
</div>`);
display(html`<p class="ch-note" style="margin-top:14px">At the end of an episode the room picks which of the two would have been better in the film. <b>${s.verdicts} verdicts</b> on the board, and it is very nearly a tie.</p>`);
```

```js
// The header carries the two totals, so this is just the proportion.
display(tape("The standing"));
const pct = (n) => `width:${100 * n / s.verdicts}%`;
display(html`<div class="ch-tug">
  <div class="c" style=${pct(s.cruise)}>${s.cruise}  CRUISE</div>
  <div class="t" style=${pct(s.ties)}>${s.ties}</div>
  <div class="h" style=${pct(s.hanks)}>HANKS  ${s.hanks}</div>
</div>`);
display(html`<p class="ch-note">A ${Math.abs(s.cruise - s.hanks)}-verdict margin across ${s.verdicts} episodes. <b>Nothing here is a landslide</b> — which is why the running margin below is the more interesting picture.</p>`);
```

```js
display(tape(`Running margin, ep ${v.run_start} → ${v.run_end}`));
display(chart("running_margin"));
const excluded = v.early ? ` Excludes ${v.early} earlier verdict${v.early === 1 ? "" : "s"} before ep ${v.run_start}.` : "";
display(html`<p class="ch-note">Cumulative Cruise wins minus Hanks wins. The lead changed hands <b>${v.lead_changes} times</b>; neither man was ever more than <b>${v.widest} verdicts</b> clear.${excluded}</p>`);
```

```js
display(tape("What actually decides it: genre"));
display(chart("genre_lean"));
display(html`<p class="ch-note">Genres with ${v.genre_floor}+ verdicts. <b>The pattern is typecasting:</b> Cruise takes the action and thriller slots, Hanks takes comedy, and everything else is close to even. Films carry multiple genres, so these buckets overlap — read it as one pattern, not one finding per row.</p>`);
```

```js
display(tape("Tale of the tape"));
const heads = Object.keys(v.tape[0]);
display(table(v.tape, heads.map((h, i) => [h, (row) => row[h], i > 0])));
display(html`<div class="ch-null"><b>Reported as a null result.</b> Era, length and quality do not separate the two camps: the largest gap is <b>${v.largest_ratio.toFixed(2)} standard deviations</b>, and the rest are smaller. Differences this size are what you would expect from two random halves of the same pile. Genre is the only dimension that moves the verdict.</div>`);
```

```js
display(tape("Longest runs"));
display(html`<div class="rw-cols c4">${v.streaks.map((k) => html`<div class="ch-streak">
  <div class="n" style=${`color:${k.verdict === "Cruise" ? "#E8A21F" : "#7BB0EE"}`}>${k.length}</div>
  <div class="lbl">${k.verdict.toUpperCase()} · EP ${k.from}–${k.to}</div>
  <div class="films">${k.films.join(" · ")}</div>
</div>`)}</div>`);
```

```js
display(tape("Who’s in the room"));
display(html`<div>${v.guests.map((g) => html`<div class="ch-guest">
  <div class="gn">${personLink(g, "./")}</div>
  <div class="bar">
    <i style=${`width:${100 * g.cruise / g.n}%;background:#C98500`}></i>
    <i style=${`width:${100 * g.ties / g.n}%;background:var(--txt-3)`}></i>
    <i style=${`width:${100 * g.hanks / g.n}%;background:#4A8FE0`}></i>
  </div>
  <div class="num">${g.cruise}–${g.hanks} · n=${g.n}</div>
</div>`)}</div>`);
display(html`<p class="ch-note">Guests in ${v.verdict_floor}+ verdict episodes. The leans are <b>suggestive, not established</b> — at these sample sizes a couple of episodes moves any of these bars noticeably.</p>`);
```

```js
display(tape("The full ledger"));
const verdictInput = Inputs.select(["All", "Cruise", "Hanks", "Tie"], {label: "Verdict"});
const termInput = Inputs.text({label: "Filter by title"});
display(html`<div class="rw-filters">${verdictInput}${termInput}</div>`);
const pick = Generators.input(verdictInput);
const term = Generators.input(termInput);
```

```js
// Newest first. The verdict rides in the caption as well as on the band, so
// it is never left to colour alone.
const q = term.trim().toLowerCase();
const led = v.ledger
  .filter((x) => pick === "All" || x.verdict === pick)
  .filter((x) => !q || x.title.toLowerCase().includes(q));
display(gridNote(`${led.length} of ${s.verdicts} verdicts · newest first`));
display(led.length
  ? trail(grid(led.map((x) => filmCard(x, `ep ${x.episode}${x.year ? ` · ${x.year}` : ""} · ${x.verdict}`, "./", x.verdict.toLowerCase())), "rw-grid six"),
          "the Cruise vs. Hanks ledger", [...new Set(led.map((x) => x.id).filter(Boolean))])
  : html`<p class="rw-ov-note">No verdicts match those filters.</p>`);
```
