---
title: Keywords
---

```js
// The app's Keywords section. Its headline counts, reach bands and each
// decade's signature come from the section's own functions, via site.db; the
// whole vocabulary is the keywords table, and search runs over it here.
import {chipField, pageHref, masthead, statRail, statTile, tape} from "./components/ui.js";

import {query as dbQuery, section} from "./components/db.js";

// The section's numbers, and the whole vocabulary from the keywords table.
const kw = {...await section("keywords"),
            vocabulary: (await dbQuery("keywords")).map((k) => ({...k, id: k.slug}))};
```

```js
display(masthead("Keywords", "What the films are about, in the words TMDB uses. Pick one to see every film that carries it."));
const t = kw.tiles;
display(statRail([
  statTile("Browsable here", t.browsable.toLocaleString()),
  statTile("Searchable", t.searchable.toLocaleString()),
  statTile("Median per film", t.median_per_film),
  statTile("On one film only", t.single_share, "%")
]));
```

```js
display(tape("Find a keyword"));
const searchInput = Inputs.text({label: "Search the whole vocabulary", placeholder: "heist, brooklyn, writer's block…"});
display(searchInput);
const query = Generators.input(searchInput);
```

```js
// Search reaches the entire vocabulary, tail included: the rare terms are
// meant to be found, not browsed. The vocabulary is commonest first, so the
// first sixty hits are the app's. A one-film keyword shows as an inert chip.
const q = query.trim().toLowerCase();
if (q) {
  const hits = kw.vocabulary.filter((k) => k.word.toLowerCase().includes(q)).slice(0, 60);
  display(hits.length
    ? html`<p class="rw-ov-note">${hits.length} of the ${kw.vocabulary.length.toLocaleString()} keywords match</p>${chipField(hits, "./")}`
    : html`<p class="rw-ov-note">Nothing in the vocabulary matches that.</p>`);
}
```

```js
// Grouped into reach bands rather than shaded by frequency: the band heading
// states the range outright, which a colour ramp can only imply.
const byWord = new Map(kw.vocabulary.map((k) => [k.word, k]));
display(tape("The common vocabulary"));
display(html`<p class="rw-ov-note">The ${t.browsable} keywords carried by ${kw.browse_floor} films or more. Every one leads somewhere.</p>`);
for (const band of kw.bands) {
  display(html`<div class="rw-kw-legend"><span>${band.label}</span><span style="color:var(--mint-deep);">${band.words.length} keywords</span></div>`);
  display(chipField(band.words.map((w) => byWord.get(w)), "./"));
}
display(html`<div class="rw-kw-tail">The other <b>${kw.tail.toLocaleString()}</b> keywords — including the <b>${kw.singles.toLocaleString()}</b> that belong to a single film — are reachable through the search above. They are genuine concepts rather than untidy duplicates, so nothing is gained by merging them away; they are simply found rather than browsed.</div>`);
```

```js
display(tape("Signature by decade"));
display(html`<div class="rw-kw-decades">${kw.signature.map((d) => html`
  <div class="rw-kw-dec"><h5>${d.decade}s</h5><span class="n">${d.films} films</span>
    <ol>${d.top.map((k) => {
      const chip = byWord.get(k.word);
      return html`<li><span>${chip?.id ? html`<a href=${pageHref("keyword", chip.id)}>${k.word}</a>` : k.word}</span><b>${k.n}</b></li>`;
    })}</ol>
  </div>`)}</div>`);
```
