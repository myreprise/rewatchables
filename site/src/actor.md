---
title: Actor
---

```js
// The actor spotlight, for every actor on three or more covered films: actor?id=<slug>. The Actors
// section's spotlight panel, drawn from site.db by components/spotlight.js.
import {pageId, query} from "./components/db.js";
import {masthead, tape} from "./components/ui.js";
import {loadSpotlight, spotlightFilms, spotlightPanels, spotlightPicker, spotlightTiles} from "./components/spotlight.js";

const s = await loadSpotlight("actor", pageId());
const picker = await query("spotlight_picker", "actor");
```

```js
display(html`<a class="rw-back" href="./actors">← Actors</a>`);
if (!s) {
  display(html`<p class="rw-ov-note">No actor spotlight at this address.</p>`);
} else {
  document.title = `${s.name} | Rewatchables Explorer`;
  display(masthead(s.name, "Actor spotlight: their covered films, the shape of the work, and the directors they return to."));
  display(spotlightTiles(s));
  display(tape(`${s.films.length} covered film${s.films.length === 1 ? "" : "s"}`));
  display(spotlightFilms(s));
  display(await spotlightPanels(s, resize));
  display(tape("Another actor"));
  display(spotlightPicker(picker, "actor", s.name));
}
```
