---
title: Director
---

```js
// One page per director in the app's spotlight picker, at /director/<slug>:
// the Directors section's spotlight. Data from step 15's spotlights module.
import {masthead, tape} from "../components/ui.js";
import {spotlightFilms, spotlightPanels, spotlightPicker, spotlightTiles} from "../components/spotlight.js";

const s = FileAttachment(`../data/directors/${observable.params.id}.json`).json();
const section = FileAttachment("../data/sections/directors.json").json();
```

```js
document.title = `${s.name} | Rewatchables Explorer`;
display(html`<a class="rw-back" href="../directors">← Directors</a>`);
display(masthead(s.name, "Director spotlight: their covered films, the shape of the work, and who they bring back."));
display(spotlightTiles(s));
display(tape(`${s.films.length} covered film${s.films.length === 1 ? "" : "s"}`));
display(spotlightFilms(s, "../"));
display(spotlightPanels(s, "../", resize));
display(tape("Another director"));
display(spotlightPicker(section.spotlight, "director", "../", s.name));
```
