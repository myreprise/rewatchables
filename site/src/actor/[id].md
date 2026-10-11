---
title: Actor
---

```js
// One page per actor in the app's spotlight picker, at /actor/<slug>: the
// Actors section's spotlight. Data from step 15's spotlights module.
import {masthead, tape} from "../components/ui.js";
import {spotlightFilms, spotlightPanels, spotlightPicker, spotlightTiles} from "../components/spotlight.js";

const s = FileAttachment(`../data/actors/${observable.params.id}.json`).json();
const section = FileAttachment("../data/sections/actors.json").json();
```

```js
document.title = `${s.name} | Rewatchables Explorer`;
display(html`<a class="rw-back" href="../actors">← Actors</a>`);
display(masthead(s.name, "Actor spotlight: their covered films, the shape of the work, and the directors they return to."));
display(spotlightTiles(s));
display(tape(`${s.films.length} covered film${s.films.length === 1 ? "" : "s"}`));
display(spotlightFilms(s, "../"));
display(spotlightPanels(s, "../", resize));
display(tape("Another actor"));
display(spotlightPicker(section.spotlight, "actor", "../", s.name));
```
