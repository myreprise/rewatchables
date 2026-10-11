---
title: Director
---

```js
// The director spotlight, for every director: director?id=<slug>. The Directors
// section's spotlight panel, drawn from site.db by components/spotlight.js.
import {pageId, query} from "./components/db.js";
import {masthead, tape} from "./components/ui.js";
import {loadSpotlight, spotlightFilms, spotlightPanels, spotlightPicker, spotlightTiles} from "./components/spotlight.js";

const s = await loadSpotlight("director", pageId());
const picker = await query("spotlight_picker", "director");
```

```js
display(html`<a class="rw-back" href="./directors">← Directors</a>`);
if (!s) {
  display(html`<p class="rw-ov-note">No director spotlight at this address.</p>`);
} else {
  document.title = `${s.name} | Rewatchables Explorer`;
  display(masthead(s.name, "Director spotlight: their covered films, the shape of the work, and who they bring back."));
  display(spotlightTiles(s));
  display(tape(`${s.films.length} covered film${s.films.length === 1 ? "" : "s"}`));
  display(spotlightFilms(s));
  display(await spotlightPanels(s, resize));
  display(tape("Another director"));
  display(spotlightPicker(picker, "director", s.name));
}
```
